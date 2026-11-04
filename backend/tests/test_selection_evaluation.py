import importlib.util
import json
from pathlib import Path

import pytest
from omnirag.generation import AnswerDraft, CitationDraft, ClaimDraft, GenerationError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_selection", ROOT / "scripts/evaluate_selection.py"
)
selection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selection)


def test_selector_fingerprint_tracks_subject_filtered_model_input():
    oak = {"chunk_id": "oak:1", "document_id": "oak", "text": "Oak Rentals lends tools."}
    elm = {"chunk_id": "elm:1", "document_id": "elm", "text": "Elm Rentals lends tools."}
    question = "What does Oak Rentals lend?"
    assert selection.selector_fingerprint([oak, elm], question) == selection.selector_fingerprint(
        [oak], question
    )
    assert selection.selector_fingerprint([oak, elm], question) != selection.selector_fingerprint(
        [oak, elm], "What does Elm Rentals lend?"
    )


def replay_case():
    return {
        "id": "fixture:delivery:hybrid_rerank",
        "definition": {
            "id": "delivery",
            "question": "What is the delivery duration?",
            "answerable": True,
            "relevant": [["policy", 1]],
            "expected_facts": [["twelve days"]],
        },
        "evidence": [
            {
                "chunk_id": "d:1:0",
                "document_id": "d",
                "document_name": "policy.pdf",
                "page": 1,
                "text": "Standard delivery takes twelve days.",
            },
            {
                "chunk_id": "d:2:0",
                "document_id": "d",
                "document_name": "policy.pdf",
                "page": 2,
                "text": "Returns require an original receipt.",
            },
        ],
    }


class Gateway:
    def __init__(self, error=None, answered=True, invalid_quote=False):
        self.error, self.answered, self.invalid_quote = error, answered, invalid_quote
        self.orders = []

    def generate(self, question, evidence):
        self.orders.append([item["chunk_id"] for item in evidence])
        if self.error:
            raise GenerationError(self.error, "Test error")
        text = (
            "Invented delivery duration."
            if self.invalid_quote
            else replay_case()["evidence"][0]["text"]
        )
        claims = [ClaimDraft(text=text, citations=[CitationDraft(chunk_id="d:1:0", quote=text)])]
        return AnswerDraft(answerable=self.answered, claims=claims if self.answered else []), {
            "model_called": True,
        }


def test_replay_preserves_evidence_and_checks_source_provenance():
    case, gateway = replay_case(), Gateway()
    before = json.dumps(case)
    row = selection.evaluate_case(gateway, case, "reversed", 1)
    assert gateway.orders == [["d:2:0", "d:1:0"]]
    assert json.dumps(case) == before
    assert row["metrics"]["contract_pass"]
    invalid = selection.evaluate_case(Gateway(invalid_quote=True), case, "retrieved", 1)
    assert invalid["error"] == "INVALID_CITATION"
    assert not invalid["metrics"]["contract_pass"]


@pytest.mark.parametrize("code", ["MODEL_TIMEOUT", "MODEL_INVALID_OUTPUT", "INVALID_CITATION"])
def test_failed_generation_cannot_count_as_successful_abstention(code):
    case = replay_case()
    case["definition"].update(answerable=False, relevant=[], expected_facts=[])
    row = selection.evaluate_case(Gateway(error=code), case, "retrieved", 1)
    assert row["error"] == code
    assert not row["metrics"]["correct_abstention"]
    assert not selection.summarize([row])["strict_pass"]


def test_stable_wrong_answers_are_not_a_passing_robustness_result():
    rows = [
        selection.evaluate_case(Gateway(answered=False), replay_case(), variant, 1)
        for variant in selection.VARIANTS
    ]
    summary = selection.summarize(rows)
    assert summary["case_stability"][0]["distinct_successful_answers"] == 1
    assert not summary["case_stability"][0]["all_contracts_pass"]
    assert not summary["strict_pass"]


def test_stability_separates_same_input_changes_from_retrieval_order():
    case = replay_case()
    rows = [
        selection.evaluate_case(Gateway(answered=answer), case, variant, 1)
        for answer, variant in [(True, "retrieved"), (False, "reversed")]
    ]
    stability = selection.summarize(rows)["case_stability"][0]
    # Page sorting makes these model excerpt inputs identical despite retrieval reversal.
    assert rows[0]["input_order"] != rows[1]["input_order"]
    assert stability["distinct_selector_inputs"] == 1
    assert stability["same_input_answer_changed"]
    assert stability["any_contract_pass"] and not stability["all_contracts_pass"]


def test_load_reports_rejects_partial_duplicate_and_changed_questions(tmp_path):
    case = replay_case()
    report = {
        "status": "completed",
        "fixture_sha256": "abc",
        "fixture": {"queries": [case["definition"]]},
        "queries": [
            {
                "mode": "hybrid_rerank",
                "repeat": 1,
                "query": "delivery",
                "question": case["definition"]["question"],
                "error": None,
                "search": {"evidence": case["evidence"]},
                "metrics": {},
            }
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    loaded, inputs = selection.load_cases([path], "hybrid_rerank")
    assert len(loaded) == 1 and len(inputs[0]["sha256"]) == 64
    with pytest.raises(ValueError, match="Duplicate replay case"):
        selection.load_cases([path, path], "hybrid_rerank")
    report["queries"][0]["question"] = "Changed question"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="differs from fixture"):
        selection.load_cases([path], "hybrid_rerank")
    report["status"] = "running"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="not completed"):
        selection.load_cases([path], "hybrid_rerank")


def test_missing_cases_cannot_silently_reduce_denominator(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            {
                "status": "completed",
                "fixture_sha256": "abc",
                "fixture": {"queries": [replay_case()["definition"]]},
                "queries": [],
            }
        )
    )
    with pytest.raises(ValueError, match="lacks all"):
        selection.load_cases([path], "hybrid_rerank")


def test_cli_requires_model_opt_in_and_preserves_existing_report(tmp_path, monkeypatch):
    path = tmp_path / "existing.json"
    path.write_text("preserve this report")
    args = ["evaluate_selection.py", "--report", "unused.json", "--output", str(path)]
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit) as missing_opt_in:
        selection.main()
    assert missing_opt_in.value.code == 2
    monkeypatch.setattr("sys.argv", args + ["--with-model"])
    monkeypatch.setattr(selection, "load_cases", lambda *_: ([replay_case()], []))
    with pytest.raises(FileExistsError):
        selection.main()
    assert path.read_text() == "preserve this report"


def test_answer_fingerprint_ignores_claim_order_but_preserves_source_page():
    first = {
        "text": "First fact",
        "citations": [{"document_id": "d", "page": 1, "quote": "First fact"}],
    }
    second = {
        "text": "Second fact",
        "citations": [{"document_id": "d", "page": 2, "quote": "Second fact"}],
    }
    answer = {"status": "answered", "claims": [first, second]}
    reversed_answer = {"status": "answered", "claims": [second, first]}
    assert selection.answer_fingerprint(answer) == selection.answer_fingerprint(reversed_answer)
    changed = json.loads(json.dumps(answer))
    changed["claims"][0]["citations"][0]["page"] = 3
    assert selection.answer_fingerprint(answer) != selection.answer_fingerprint(changed)
