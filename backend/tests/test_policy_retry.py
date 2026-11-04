import json
from types import SimpleNamespace

import httpx
import pytest
from omnirag import generation
from omnirag.config import Settings

EVIDENCE = [
    {
        "chunk_id": "amber:1:0",
        "document_id": "amber",
        "document_name": "amber.pdf",
        "page": 1,
        "text": "Amber Works completes reviews within eight business days.",
    }
]


def selection(answerable=False, **overrides):
    return {
        "evidence_assessment": "PRIVATE diagnostic assessment",
        "requires_individual_record": False,
        "individual_record_present": False,
        "answerable": answerable,
        "source_ids": ["S1"] if answerable else [],
        **overrides,
    }


def harness(results, counts=None):
    calls = []

    def handler(request):
        calls.append((json.loads(request.content), request.extensions["timeout"]))
        result = results[len(calls) - 1]
        if isinstance(result, Exception):
            raise result
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(result)},
                "prompt_eval_count": 50,
                "eval_count": (counts or [100] * len(results))[len(calls) - 1],
            },
        )

    return generation.OllamaGateway(Settings(), httpx.MockTransport(handler)), calls


def test_retry_shares_budget_and_never_exposes_assessment(monkeypatch):
    ticks = iter([0, 0, 20, 20])
    monkeypatch.setattr(generation, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    gateway, calls = harness([selection(), selection(True)], [100, 20])
    draft, usage = gateway.generate("How long does the review take?", EVIDENCE)
    assert len(calls) == 2 and draft.answerable
    assert calls[0][0]["messages"][1] == calls[1][0]["messages"][1]
    assert calls[0][0]["messages"][0] != calls[1][0]["messages"][0]
    assert [x[0]["options"]["num_predict"] for x in calls] == [768, 668]
    assert calls[1][1]["read"] == 100
    assert usage["input_tokens"] == 100 and usage["output_tokens"] == 120
    assert usage["selection_attempts"] == 2 and usage["retry_status"] == "attempted"
    assert "PRIVATE" not in json.dumps([draft.model_dump(), usage])
    assert draft.claims[0].text == draft.claims[0].citations[0].quote == EVIDENCE[0]["text"]


@pytest.mark.parametrize(
    "first,question,count,reason",
    [
        (selection(True), "How long?", 100, "not_needed"),
        (
            selection(requires_individual_record=True),
            "Has my review finished?",
            100,
            "individual_record",
        ),
        (selection(), "Has anyone completed my review?", 100, "event_question"),
        (selection(), "Did my review pass?", 100, "event_question"),
        (selection(), "How long?", 700, "output_budget"),
        (selection(), "How long?", None, "usage_unavailable"),
    ],
)
def test_ineligible_retry_never_makes_second_call(first, question, count, reason):
    gateway, calls = harness([first], [count])
    _, usage = gateway.generate(question, EVIDENCE)
    assert len(calls) == 1 and usage["retry_status"] == reason


def test_missing_subject_now_stops_before_the_first_model_call():
    gateway, calls = harness([])
    draft, usage = gateway.generate("How long does Zircon Works take?", EVIDENCE)
    assert not draft.answerable and not calls
    assert usage["subject_scope_withheld"] and not usage["model_called"]


def test_time_budget_stops_retry(monkeypatch):
    ticks = iter([0, 0, 119.5])
    monkeypatch.setattr(generation, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    gateway, calls = harness([selection()])
    draft, usage = gateway.generate("How long?", EVIDENCE)
    assert not draft.answerable and len(calls) == 1 and usage["retry_status"] == "time_budget"


@pytest.mark.parametrize(
    "second,code",
    [
        (selection(True, source_ids=["unknown"]), "INVALID_CITATION"),
        (selection(True, source_ids=["S1", "S1"]), "INVALID_CITATION"),
        (selection(True, source_ids=[]), "MODEL_INVALID_OUTPUT"),
        (httpx.ReadTimeout("timeout"), "MODEL_TIMEOUT"),
    ],
)
def test_retry_retains_validation_and_error_handling(second, code):
    gateway, calls = harness([selection(), second])
    with pytest.raises(generation.GenerationError) as error:
        gateway.generate("How long?", EVIDENCE)
    assert error.value.code == code and len(calls) == 2


def test_first_pass_invalid_sources_do_not_trigger_retry():
    gateway, calls = harness([selection(True, source_ids=["unknown"])])
    with pytest.raises(generation.GenerationError):
        gateway.generate("How long?", EVIDENCE)
    assert len(calls) == 1


def test_second_pass_abstention_and_record_gate_are_terminal():
    for second in [selection(), selection(True, requires_individual_record=True)]:
        gateway, calls = harness([selection(), second])
        draft, usage = gateway.generate("How long?", EVIDENCE)
        assert not draft.answerable and not draft.claims and len(calls) == 2
        assert usage["selected_source_ids"] == []


def test_capitalization_guard_is_conservative_and_does_not_accept_substrings():
    assert generation.missing_named_term("How long does Zircon Works take?", EVIDENCE)
    assert not generation.missing_named_term("How long does Amber Works take?", EVIDENCE)
    assert generation.missing_named_term("Can I use code AX-70?", EVIDENCE)
    assert not generation.missing_named_term("When am I allowed to extend my review?", EVIDENCE)
    assert generation.missing_named_term(
        "Does Amber Works support AX-70?",
        [{**EVIDENCE[0], "text": EVIDENCE[0]["text"] + " The code AX-700 indicates a fault."}],
    )
