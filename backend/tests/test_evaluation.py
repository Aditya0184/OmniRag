import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from omnirag.evaluation import (
    contains_fact,
    contains_phrase,
    edit_distance,
    score_answer,
    summarize_answers,
    transcription_metrics,
)
from omnirag.generation import AnswerDraft, CitationDraft, ClaimDraft
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_quality", ROOT / "scripts/evaluate_quality.py"
)
quality = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quality)


@pytest.mark.parametrize(
    "reference,observed,distance",
    [
        ("kitten", "sitting", 3),
        ("abc", "", 3),
        ("", "abc", 3),
        ("abc", "abc", 0),
    ],
)
def test_edit_distance(reference, observed, distance):
    assert edit_distance(reference, observed) == distance


def test_transcription_normalization_and_denominators():
    assert transcription_metrics("ﬁle\n  ready", "file ready")["cer"] == 0
    result = transcription_metrics("One two", "one too three")
    assert result["word_edits"] == 3 and result["reference_words"] == 2
    assert result["wer"] == 1.5  # Do not cap rates at one.
    assert transcription_metrics("expected words", "")["wer"] == 1
    assert transcription_metrics("", "extra")["cer"] is None


def test_fact_matching_uses_word_boundaries():
    assert contains_phrase("Delivered in 14 calendar days.", "14 calendar days")
    assert not contains_phrase("114 calendar days", "14 calendar days")
    assert not contains_phrase("14 days", "14 calendar days")
    assert not contains_phrase("anything", "")


def case(answerable=True):
    return {
        "answerable": answerable,
        "relevant": [["policy", 2]] if answerable else [],
        "expected_facts": [["14 calendar days", "fourteen calendar days"]] if answerable else [],
        "forbidden": ["galactic banana"],
    }


def response(text="Delivery takes 14 calendar days.", page=2):
    return {
        "status": "answered",
        "claims": [{"text": text, "citations": [{"document_id": "id", "page": page}]}],
    }


def test_answer_contract_requires_facts_and_reference_page():
    assert score_answer(case(), response(), {"id": "policy"})["contract_pass"]
    assert not score_answer(case(), response(page=1), {"id": "policy"})["contract_pass"]
    assert not score_answer(case(), response("114 calendar days"), {"id": "policy"})[
        "contract_pass"
    ]
    assert not score_answer(
        case(), response("14 calendar days. Galactic banana"), {"id": "policy"}
    )["contract_pass"]
    multiple = {**case(), "expected_facts": [["14 calendar days"], ["written authorization"]]}
    assert not score_answer(multiple, response(), {"id": "policy"})["contract_pass"]


def test_withheld_citation_failure_is_not_successful_abstention():
    withheld = {"status": "insufficient_evidence", "claims": []}
    assert score_answer(case(False), withheld, {})["correct_abstention"]
    for error in ("INVALID_CITATION", "MODEL_TIMEOUT", "MODEL_INVALID_OUTPUT"):
        scored = score_answer(case(False), withheld, {}, error=error)
        assert not scored["correct_abstention"] and not scored["contract_pass"]
    assert not score_answer(case(False), response(), {})["correct_abstention"]


def test_fact_matching_accepts_identifiers_and_rejects_order_or_values():
    """Positive and negative examples for the subsequence fact rule."""
    claim = "Payment for Ridge Parts order R-517 cleared on 18 September 2025."
    # Positive: an inserted identifier does not change the fact.
    assert contains_fact(claim, "payment cleared on 18 September 2025")
    assert contains_fact(claim, "order R-517 cleared")
    assert contains_fact(
        "Orders may be cancelled for a full refund within 21 days.", "refund within 21 days"
    )
    # Negative: changed values, changed order, missing tokens.
    assert not contains_fact(claim, "payment cleared on 19 September 2025")
    assert not contains_fact(claim, "18 September 2025 payment cleared on")
    assert not contains_fact(claim, "payment cleared on 18 September 2025 in full")
    assert not contains_fact("The fee is 118 credits.", "14 credits")
    assert not contains_fact("No payment was made.", "payment cleared")
    # Consecutive matching is unchanged for quotes and forbidden phrases.
    assert contains_phrase(claim, "cleared on 18 September")
    assert not contains_phrase(claim, "payment cleared on 18 September 2025")


def test_answer_contract_rejects_wrong_fact_pages_and_reports_precision():
    # A second, supported true fact on another page is tolerated: the fact-bearing
    # claims are what the contract checks.
    result = response()
    result["claims"].append(
        {
            "text": "Express delivery requires written authorization.",
            "citations": [{"document_id": "id", "page": 1}],
        }
    )
    scored = score_answer(case(), result, {"id": "policy"})
    assert scored["citation_page_precision"] == 0.5 and scored["contract_pass"]
    # A fact-bearing claim on the wrong page still fails the contract.
    assert not score_answer(case(), response(page=1), {"id": "policy"})["contract_pass"]
    result = response(page=1)
    result["claims"].append(
        {"text": "Unrelated text", "citations": [{"document_id": "id", "page": 2}]}
    )
    assert not score_answer(case(), result, {"id": "policy"})["facts_cite_reference_pages"]


def test_failed_rows_stay_in_denominator_and_skips_are_null():
    rows = [
        {
            "answerable": True,
            "metrics": {"expected_facts_match": True, "contract_pass": True},
            "error": None,
        },
        {
            "answerable": True,
            "metrics": {"expected_facts_match": False, "contract_pass": False},
            "error": "MODEL_TIMEOUT",
        },
    ]
    summary = summarize_answers(rows)
    assert summary["answer_fact_match_rate"] == 0.5 and summary["errors"] == 1
    assert summary["unsupported_abstention_rate"] is None
    rows[1]["metrics"] = None
    assert summarize_answers(rows)["contract_pass_rate"] is None


def test_fixture_rendering_is_repeatable_and_scans_have_no_text_layer():
    fixture = quality.read_fixture(ROOT / "evaluation/quality_fixture.json")
    for document in fixture["documents"]:
        first = quality.make_pdf(document)
        assert first == quality.make_pdf(document)
        pages = PdfReader(io.BytesIO(first)).pages
        assert len(pages) == len(document["pages"])
        for pdf_page, page in zip(pages, document["pages"], strict=True):
            text = pdf_page.extract_text()
            if page["kind"] in {"scan", "degraded_scan"}:
                assert not text
            elif page["kind"] == "header_scan":
                assert page["header"] in text and "11 years" not in text


def test_fixture_rejects_reference_outside_scope(tmp_path):
    fixture = quality.read_fixture(ROOT / "evaluation/quality_fixture.json")
    fixture["queries"][0]["scope"] = ["scan"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError, match="outside scope"):
        quality.read_fixture(path)


def test_recording_gateway_retains_invalid_citation(settings, monkeypatch):
    draft = AnswerDraft(
        answerable=True,
        claims=[
            ClaimDraft(
                text="14 calendar days",
                citations=[CitationDraft(chunk_id="missing", quote="This source does not exist.")],
            )
        ],
    )
    monkeypatch.setattr(quality.OllamaGateway, "generate", lambda *args: (draft, {}))
    gateway = quality.RecordingGateway(settings)
    returned, _ = gateway.generate("Delivery?", [])
    assert returned == draft
    assert gateway.observation["error"] == "INVALID_CITATION"


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")
def test_offline_evaluation_preserves_workspace_data_and_recovers_scanned_body(tmp_path):
    output = tmp_path / "report.json"
    # The caller's configured data path must never be prepared or opened by the evaluator.
    import os

    sentinel = tmp_path / "real-data"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/evaluate_quality.py"),
            "--modes",
            "bm25",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        env={**os.environ, "OMNIRAG_DATA_DIR": str(sentinel), "OMNIRAG_OCR_ENABLED": "true"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not sentinel.exists()
    report = json.loads(output.read_text())
    assert report["status"] == "completed"
    assert len(report["queries"]) == 10 and len(report["pages"]) == 7
    assert all(row["metrics"] is None for row in report["queries"])
    assert report["summary"]["answers"]["core/bm25"]["answer_fact_match_rate"] is None
    gap = next(row for row in report["pages"] if row["kind"] == "header_scan")
    assert gap["metrics"]["cer"] == 0 and gap["metrics"]["wer"] == 0
    assert gap["metadata"]["method"] == "ocr"
    assert gap["metadata"]["ocr_trigger"] == "sparse_text_large_image"
    assert any(row["metadata"]["method"] == "ocr" for row in report["pages"])
    before = output.read_bytes()
    again = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluate_quality.py"), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        timeout=10,
    )
    assert again.returncode != 0 and output.read_bytes() == before
