"""Grounded written answers, summaries, intents, clarification and conversation."""

from types import SimpleNamespace

import pytest
from omnirag.db import get_summary, save_summary
from omnirag.generation import (
    GenerationError,
    GroundedAnswerDraft,
    GroundedCitationDraft,
    GroundedClaimDraft,
    validate_grounded,
)
from omnirag.intents import classify_intent
from omnirag.main import create_app
from omnirag.summary import (
    MAX_SECTIONS,
    build_sections,
    coverage_sample,
    generate_overview,
    partial_note,
)

from .conftest import GroundedTestGateway, TestGateway, make_pdf

EVIDENCE = [
    {
        "chunk_id": "doc:1:0",
        "document_id": "doc",
        "document_name": "sample.pdf",
        "page": 1,
        "text": "Orion Supplies has a standard delivery window of 14 calendar days.",
    }
]


def upload_ready(client, settings, pages, name="sample.pdf"):
    response = client.post(
        "/api/v1/documents", files={"file": (name, make_pdf(pages), "application/pdf")}
    )
    assert response.status_code == 202, response.text
    from omnirag.worker import run_once

    assert run_once(settings)
    return response.json()["document"]["id"]


def test_grounded_answer_keeps_quote_and_explanation_distinct():
    draft = GroundedAnswerDraft(
        answerable=True,
        claims=[
            GroundedClaimDraft(
                text="Orion Supplies has a standard delivery window of 14 calendar days.",
                citations=[
                    GroundedCitationDraft(
                        chunk_id="doc:1:0",
                        quote="Orion Supplies has a standard delivery window of 14 calendar days.",
                    )
                ],
            ),
            GroundedClaimDraft(
                text="The delivery window lasts 14 days.",
                citations=[
                    GroundedCitationDraft(
                        chunk_id="doc:1:0", quote="standard delivery window of 14 calendar days"
                    )
                ],
            ),
        ],
    )
    claims, usage = validate_grounded(draft, EVIDENCE)
    assert usage["claims_dropped"] == 0 and usage["claims_kept"] == 2
    assert [claim["kind"] for claim in claims] == ["quote", "explanation"]


def test_unsupported_wording_drops_only_that_claim():
    draft = GroundedAnswerDraft(
        answerable=True,
        claims=[
            GroundedClaimDraft(
                text="The supplier also ships to Alaska every Friday.",
                citations=[
                    GroundedCitationDraft(
                        chunk_id="doc:1:0",
                        quote="Orion Supplies has a standard delivery window of 14 calendar days.",
                    )
                ],
            ),
            GroundedClaimDraft(
                text="The delivery window is 14 calendar days.",
                citations=[
                    GroundedCitationDraft(
                        chunk_id="doc:1:0", quote="standard delivery window of 14 calendar days"
                    )
                ],
            ),
        ],
    )
    claims, usage = validate_grounded(draft, EVIDENCE)
    assert usage["claims_dropped"] == 1 and usage["claims_kept"] == 1
    assert claims[0]["text"] == "The delivery window is 14 calendar days."


def test_invented_numbers_and_unknown_chunks_are_rejected():
    fabricated_number = GroundedAnswerDraft(
        answerable=True,
        claims=[
            GroundedClaimDraft(
                text="The delivery window is 30 calendar days.",
                citations=[
                    GroundedCitationDraft(
                        chunk_id="doc:1:0",
                        quote="Orion Supplies has a standard delivery window of 14 calendar days.",
                    )
                ],
            )
        ],
    )
    claims, usage = validate_grounded(fabricated_number, EVIDENCE)
    assert usage["claims_dropped"] == 1 and claims == []

    # A fabricated citation drops its own claim; other claims survive.
    claims, usage = validate_grounded(
        GroundedAnswerDraft(
            answerable=True,
            claims=[
                GroundedClaimDraft(
                    text="Whatever.",
                    citations=[
                        GroundedCitationDraft(chunk_id="other:9:9", quote="some invented text")
                    ],
                ),
                GroundedClaimDraft(
                    text="Orion Supplies has a standard delivery window of 14 calendar days.",
                    citations=[
                        GroundedCitationDraft(
                            chunk_id="doc:1:0",
                            quote=EVIDENCE[0]["text"],
                        )
                    ],
                ),
            ],
        ),
        EVIDENCE,
    )
    assert usage["claims_dropped"] == 1 and len(claims) == 1


def test_disagreeing_answerability_is_invalid():
    draft = GroundedAnswerDraft(answerable=True, claims=[])
    with pytest.raises(GenerationError) as error:
        validate_grounded(draft, EVIDENCE)
    assert error.value.code == "MODEL_INVALID_OUTPUT"


def test_grounding_overview_question_uses_coverage_and_single_document(grounded_client, settings):
    document_id = upload_ready(
        grounded_client,
        settings,
        ["Zephyr Optics lens guide. The Polaris 90 uses a 90 millimetre lens."],
    )
    GroundedTestGateway.calls = []
    answer = grounded_client.post(
        "/api/v1/queries", json={"question": "What is in this PDF?"}
    ).json()
    assert answer["status"] == "answered"
    assert answer["intent"] == "overview"
    assert answer["scope"]["source"] == "single_document"
    assert answer["scope"]["document_ids"] == [document_id]
    assert answer["coverage"]["complete"] is True
    assert answer["retrieval_mode"] == "coverage"
    assert GroundedTestGateway.calls[0]["intent"] == "overview"
    claim = answer["claims"][0]
    assert claim["citations"][0]["page"] == 1


def test_overview_with_several_documents_asks_which_one(grounded_client, settings):
    upload_ready(
        grounded_client,
        settings,
        ["Alpha policy: tools are lent for 4 days with a charger."],
        "alpha.pdf",
    )
    upload_ready(
        grounded_client,
        settings,
        ["Beta policy: returns are accepted within 21 days of purchase."],
        "beta.pdf",
    )
    answer = grounded_client.post(
        "/api/v1/queries", json={"question": "Tell me about this document."}
    ).json()
    assert answer["status"] == "clarification_needed"
    names = {candidate["name"] for candidate in answer["candidates"]}
    assert names == {"alpha.pdf", "beta.pdf"}
    assert answer["claims"] == [] and answer["model"] is None


def test_list_intent_is_reported_and_widens_retrieval(grounded_client, settings):
    document_id = upload_ready(
        grounded_client,
        settings,
        ["The tools in the kit are a wrench, a hammer, a drill, a sander, a plane and a clamp."],
    )
    answer = grounded_client.post(
        "/api/v1/queries",
        json={"question": "Which tools are listed?", "document_ids": [document_id]},
    ).json()
    assert answer["intent"] == "list"
    assert answer["status"] == "answered"


def test_conversation_scope_and_turns_reach_the_gateway(grounded_client, settings):
    document_id = upload_ready(
        grounded_client, settings, ["Orion Supplies delivers in 14 calendar days."]
    )
    GroundedTestGateway.calls = []
    answer = grounded_client.post(
        "/api/v1/queries",
        json={
            "question": "How does it work?",
            "conversation": [
                {
                    "question": "Which delivery policy applies?",
                    "answer": "Orion Supplies delivers in 14 calendar days.",
                    "document_ids": [document_id],
                }
            ],
        },
    ).json()
    assert answer["scope"]["source"] == "conversation"
    assert answer["scope"]["document_ids"] == [document_id]
    assert GroundedTestGateway.calls[0]["conversation"][0]["question"] == (
        "Which delivery policy applies?"
    )


def test_summarize_uses_cached_overview_without_a_model_call(grounded_client, settings):
    document_id = upload_ready(
        grounded_client, settings, ["Orion Supplies delivery policy text."]
    )
    content = {
        "document_type": "delivery policy",
        "summary": "A short policy about delivery windows.",
        "topics": ["delivery"],
        "key_points": [
            {"text": "Deliveries take 14 calendar days.", "pages": [1]},
        ],
        "suggested_questions": ["How long is the delivery window?"],
    }
    save_summary(
        settings.database,
        document_id,
        "overview",
        status="ready",
        content=content,
        coverage={"complete": True, "pages_used": 1, "pages_total": 1},
        model="test-double",
        error=None,
    )

    class ExplodingGateway(GroundedTestGateway):
        def generate_grounded(self, *args, **kwargs):
            raise AssertionError("A cached summary must not call the model")

    from fastapi.testclient import TestClient

    with TestClient(create_app(settings, ExplodingGateway())) as client:
        answer = client.post(
            "/api/v1/queries",
            json={"question": "Summarize this.", "document_ids": [document_id]},
        ).json()
        assert answer["status"] == "answered"
        assert answer["verification"] == "document_summary"
        assert answer["usage"]["summary_kind"] == "cached"
        assert answer["summary"]["summary"].startswith("A short policy")
        claim = answer["claims"][0]
        assert claim["citations"][0]["page"] == 1
        assert "14 calendar days" in claim["text"]


def test_summary_endpoints_generate_cache_and_fail_visibly(grounded_client, settings, monkeypatch):
    from fastapi.testclient import TestClient

    document_id = upload_ready(
        grounded_client, settings, ["Orion Supplies delivers within 14 calendar days."]
    )

    class StubGateway(GroundedTestGateway):
        def generate_json(self, system, request, schema, num_predict, deadline):
            return {
                "document_type": "delivery policy",
                "summary": "Orion Supplies describes a 14 calendar day delivery window.",
                "topics": ["delivery"],
                "key_points": [
                    {"text": "The delivery window is 14 calendar days.", "pages": [1]}
                ],
                "suggested_questions": ["How long is the delivery window?"],
            }, {"input_tokens": 50, "output_tokens": 40}

    StubGateway.settings = SimpleNamespace(model_timeout_seconds=30)
    with TestClient(create_app(settings, StubGateway())) as client:
        created = client.post(
            f"/api/v1/documents/{document_id}/summary", json={"kind": "overview"}
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["status"] == "answered"
        assert body["summary"]["document_type"] == "delivery policy"
        cached = client.get(f"/api/v1/documents/{document_id}/summary")
        assert cached.status_code == 200
        assert cached.json()["content"]["summary"] == body["summary"]["summary"]
        missing = client.get(f"/api/v1/documents/{document_id}/summary?kind=detailed")
        assert missing.status_code == 404

    class BrokenGateway(GroundedTestGateway):
        settings = SimpleNamespace(model_timeout_seconds=30)

        def generate_json(self, system, request, schema, num_predict, deadline):
            raise GenerationError("MODEL_UNAVAILABLE", "Start Ollama.", 503)

    fresh_settings = settings.model_copy(update={"data_dir": settings.data_dir})
    with TestClient(create_app(fresh_settings, BrokenGateway())) as client:
        failed = client.post(
            f"/api/v1/documents/{document_id}/summary", json={"kind": "overview"}
        )
        assert failed.status_code == 503
        row = get_summary(settings.database, document_id, "overview")
        assert row["status"] == "failed" and "MODEL_UNAVAILABLE" in row["error"]
        listing = client.get("/api/v1/documents").json()
        assert listing[0]["summary_status"] == "failed"


def test_worker_generates_overview_after_ingestion(settings, monkeypatch):
    from omnirag.worker import run_once

    recorded = {}

    def fake_overview(gateway, name, chunks):
        recorded["name"] = name
        recorded["chunks"] = len(chunks)
        return (
            {
                "document_type": "policy",
                "summary": "Summary text.",
                "topics": [],
                "key_points": [],
                "suggested_questions": [],
            },
            {"complete": True, "pages_used": 1, "pages_total": 1},
        )

    monkeypatch.setattr("omnirag.summary.generate_overview", fake_overview)
    from fastapi.testclient import TestClient

    with TestClient(create_app(settings, TestGateway())) as client:
        response = client.post(
            "/api/v1/documents",
            files={
                "file": ("overview-me.pdf", make_pdf(["Some policy content."]), "application/pdf")
            },
        )
        document_id = response.json()["document"]["id"]
    assert run_once(settings)
    row = get_summary(settings.database, document_id, "overview")
    assert row and row["status"] == "ready"
    assert recorded["name"] == "overview-me.pdf" and recorded["chunks"] == 1


def test_worker_overview_failure_never_fails_the_document(settings, monkeypatch):
    from omnirag.worker import run_once

    def broken(gateway, name, chunks):
        raise GenerationError("MODEL_TIMEOUT", "Local model timed out.", 504)

    monkeypatch.setattr("omnirag.summary.generate_overview", broken)
    from fastapi.testclient import TestClient

    with TestClient(create_app(settings, TestGateway())) as client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("slow.pdf", make_pdf(["Some policy content."]), "application/pdf")},
        )
        document_id = response.json()["document"]["id"]
    assert run_once(settings)
    assert client.get(f"/api/v1/documents/{document_id}").json()["status"] == "ready"
    row = get_summary(settings.database, document_id, "overview")
    assert row["status"] == "failed" and "MODEL_TIMEOUT" in row["error"]


def test_intent_classification_boundaries():
    assert classify_intent("What is in this PDF?")["kind"] == "overview"
    assert classify_intent("tell me about the document")["kind"] == "overview"
    assert classify_intent("Summarize this.")["kind"] == "summarize"
    assert classify_intent("Show key points")["kind"] == "key_points"
    assert classify_intent("Which internships are listed?")["kind"] == "list"
    assert classify_intent("How does the brake system work?")["kind"] == "factual"
    assert classify_intent("What is the delivery window?")["kind"] == "factual"
    assert classify_intent("Was the order approved?")["kind"] == "factual"
    overview = classify_intent("What is in this document?")
    assert overview["demonstrative"] is True
    assert classify_intent("How long is the delivery window?")["demonstrative"] is False


def test_sections_and_coverage_are_bounded():
    chunks = [
        {"page": page, "ordinal": 0, "text": f"Page {page} text. " + "word " * 100}
        for page in range(1, 6)
    ]
    sections = build_sections(chunks)
    assert sections[0]["pages"] == [1, 2, 3]
    sample, complete = coverage_sample(chunks, budget=300)
    assert complete is False
    assert sample[0]["page"] == 1
    assert partial_note({"complete": False, "pages_used": 2, "pages_total": 5})
    assert partial_note({"complete": True, "pages_used": 5, "pages_total": 5}) is None
    full, complete_all = coverage_sample(chunks, budget=100_000)
    assert complete_all is True and len(full) == len(chunks)


def test_overview_validation_drops_unsupported_points_and_bad_pages():
    class StubGateway:
        settings = None

        def generate_json(self, system, request, schema, num_predict, deadline):
            assert "[page 1]" in request["pages"]
            return {
                "document_type": "policy guide",
                "summary": "The document explains delivery windows and review rules.",
                "topics": ["delivery", "review", "invented topic without support"],
                "key_points": [
                    {"text": "Deliveries take 14 calendar days.", "pages": [1]},
                    {"text": "Invented fact about space travel to Mars.", "pages": [1]},
                    {"text": "Point citing a missing page.", "pages": [9]},
                ],
                "suggested_questions": ["How long is the delivery window?"],
            }, {"input_tokens": 50, "output_tokens": 40}

    from types import SimpleNamespace

    gateway = StubGateway()
    gateway.settings = SimpleNamespace(model_timeout_seconds=30)
    chunks = [
        {
            "page": 1,
            "ordinal": 0,
            "text": "Orion Supplies has a standard delivery window of 14 calendar days.",
        }
    ]
    content, coverage = generate_overview(gateway, "sample.pdf", chunks)
    assert coverage == {"complete": True, "pages_used": 1, "pages_total": 1}
    assert len(content["key_points"]) == 1
    assert content["key_points"][0]["pages"] == [1]
    assert content["key_points_dropped"] == 2
    assert content["document_type"] == "policy guide"


def test_sections_cap_is_reported():
    chunks = [
        {"page": page, "ordinal": 0, "text": f"Unique section text {page}. " + "x " * 500}
        for page in range(1, 11)
    ]
    sections = build_sections(chunks)
    assert len(sections) > MAX_SECTIONS
