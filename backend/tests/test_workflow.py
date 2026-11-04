import io
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from omnirag.db import claim_job, connection, finish_job
from omnirag.generation import (
    AnswerDraft,
    CitationDraft,
    ClaimDraft,
    GenerationError,
    OllamaGateway,
)
from omnirag.ingestion import parse_pdf
from omnirag.main import create_app
from omnirag.retrieval import query_expression, retrieve
from omnirag.worker import run_once
from pypdf import PdfWriter

from .conftest import TestGateway, make_pdf


def test_named_subject_mismatch_abstains_through_the_model(settings):
    """The literal scope filter focuses passages; an empty filter relaxes instead of refusing."""

    def grounded(request):
        payload = json.loads(request.content)
        assert payload["format"]["properties"]["answerable"]["type"] == "boolean"
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "answerable": False,
                            "missing_information": (
                                "The passages only cover Oak Rentals, not Elm Rentals."
                            ),
                            "claims": [],
                        }
                    )
                },
                "prompt_eval_count": 120,
                "eval_count": 30,
            },
        )

    gateway = OllamaGateway(settings, httpx.MockTransport(grounded))
    with TestClient(create_app(settings, gateway)) as client:
        uploaded = client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "oak.pdf",
                    make_pdf(["Oak Rentals lends tools for 4 days."]),
                    "application/pdf",
                )
            },
        )
        assert uploaded.status_code == 202
        assert run_once(settings)
        response = client.post(
            "/api/v1/queries",
            json={
                "question": "How long does Elm Rentals lend tools?",
                "document_ids": [uploaded.json()["document"]["id"]],
                "retrieval_mode": "bm25",
            },
        )
        assert response.status_code == 200
        answer = response.json()
        assert answer["status"] == "unsupported_question"
        assert answer["evidence"] and answer["claims"] == []
        assert answer["usage"]["scope_relaxed"] is True
        assert answer["usage"]["scope_excluded_chunks"] == 1
        assert answer["usage"]["model_called"] is True
        assert "Oak Rentals" in answer["reason"]
        saved = client.get("/api/v1/history").json()[0]
        assert saved["id"] == answer["id"] and saved["reason"] == answer["reason"]


def upload(client, content, name="sample.pdf"):
    response = client.post("/api/v1/documents", files={"file": (name, content, "application/pdf")})
    assert response.status_code == 202, response.text
    return response.json()["document"]["id"]


def test_pdf_to_cited_answer_and_restart(client, settings, sample_pdf):
    document_id = upload(client, sample_pdf)
    assert run_once(settings)
    doc = client.get(f"/api/v1/documents/{document_id}").json()
    assert doc["status"] == "ready" and doc["page_count"] == 2
    answer = client.post("/api/v1/queries", json={"question": "What is the acceptance review?"})
    assert answer.status_code == 200
    citation = answer.json()["claims"][0]["citations"][0]
    assert citation["page"] == 2
    assert citation["document_id"] == document_id
    assert "5 business days" in citation["quote"]
    original = client.get(f"/api/v1/documents/{document_id}/file")
    assert original.content == sample_pdf
    with TestClient(create_app(settings, TestGateway())) as restarted:
        assert len(restarted.get("/api/v1/documents").json()) == 1
        assert restarted.get("/api/v1/history").json()[0]["id"] == answer.json()["id"]


def test_duplicate_is_idempotent(client, settings, sample_pdf):
    first = upload(client, sample_pdf)
    assert run_once(settings)
    response = client.post("/api/v1/documents", files={"file": ("again.pdf", sample_pdf)})
    assert response.json()["duplicate"] is True
    assert response.json()["document"]["id"] == first
    assert not run_once(settings)
    assert len(list(settings.uploads.glob("*.pdf"))) == 1
    with connection(settings.database) as con:
        assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] == 2


def test_document_scope_and_not_ready(client, settings, sample_pdf):
    first = upload(client, sample_pdf)
    not_ready = client.post(
        "/api/v1/queries", json={"question": "delivery", "document_ids": [first]}
    )
    assert not_ready.status_code == 409
    run_once(settings)
    second = upload(client, make_pdf(["Zephyr's unique warranty period is 77 months."]))
    run_once(settings)
    results = retrieve(settings.database, "warranty", [first], 4)
    assert results == []
    assert retrieve(settings.database, "warranty", [second], 4)[0]["document_id"] == second


def test_no_evidence_does_not_call_model(client, settings):
    class NeverCall(TestGateway):
        def generate(self, *args):
            raise AssertionError("No evidence must not call the model")

    with TestClient(create_app(settings, NeverCall())) as test:
        answer = test.post("/api/v1/queries", json={"question": "Unknown space mission?"})
        assert answer.json()["status"] == "no_relevant_passage"
        assert answer.json()["claims"] == []


def test_invented_citation_withholds_answer(client, settings, sample_pdf):
    upload(client, sample_pdf)
    run_once(settings)

    class BadCitation(TestGateway):
        def generate(self, question, evidence):
            return AnswerDraft(
                answerable=True,
                claims=[
                    ClaimDraft(
                        text="This invented answer must not be shown.",
                        citations=[
                            CitationDraft(chunk_id="invented-id", quote="an invented quotation")
                        ],
                    )
                ],
            ), {}

    with TestClient(create_app(settings, BadCitation())) as test:
        answer = test.post("/api/v1/queries", json={"question": "delivery window"})
        assert answer.json()["status"] == "unsupported_question"
        assert answer.json()["claims"] == []
        assert "validation" in answer.json()["reason"]


def test_selected_excerpt_is_bound_and_saved_without_rewriting_old_history(
    client,
    settings,
    sample_pdf,
):
    settings.answer_mode = "extractive"
    upload(client, sample_pdf)
    run_once(settings)
    old = client.post("/api/v1/queries", json={"question": "delivery"}).json()

    def select(request):
        payload = json.loads(request.content)
        sources = json.loads(payload["messages"][1]["content"])["excerpts"]
        chosen = next(source for source in sources if "14 calendar days" in source["text"])
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "requires_individual_record": False,
                            "individual_record_present": False,
                            "evidence_assessment": "PRIVATE ASSESSMENT NOT AN ANSWER",
                            "answerable": True,
                            "source_ids": [chosen["id"]],
                        }
                    )
                }
            },
        )

    gateway = OllamaGateway(settings, httpx.MockTransport(select))
    with TestClient(create_app(settings, gateway)) as updated:
        answer = updated.post("/api/v1/queries", json={"question": "delivery"}).json()
        assert answer["verification"] == "extractive_source_binding"
        assert answer["usage"]["selection_policy"] == "subject_scoped_policy_v3"
        assert "PRIVATE ASSESSMENT" not in json.dumps(answer)
        assert answer["claims"][0]["text"] == answer["claims"][0]["citations"][0]["quote"]
        assert answer["claims"][0]["citations"][0]["page"] == 1
        history = updated.get("/api/v1/history").json()
        assert history == [answer, old]
        assert old["verification"] == "extractive_source_binding"


def test_guarded_retry_saves_one_answer_and_aggregate_usage(client, settings, sample_pdf):
    settings.answer_mode = "extractive"
    document_id = upload(client, sample_pdf)
    run_once(settings)
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        sources = json.loads(payload["messages"][1]["content"])["excerpts"]
        chosen = next(source for source in sources if "14 calendar days" in source["text"])
        supported = len(calls) == 2
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "evidence_assessment": "PRIVATE assessment",
                            "requires_individual_record": False,
                            "individual_record_present": False,
                            "answerable": supported,
                            "source_ids": [chosen["id"]] if supported else [],
                        }
                    )
                },
                "prompt_eval_count": 200,
                "eval_count": 100,
            },
        )

    with TestClient(
        create_app(settings, OllamaGateway(settings, httpx.MockTransport(respond)))
    ) as app:
        response = app.post(
            "/api/v1/queries",
            json={
                "question": "How long is the delivery window?",
                "document_ids": [document_id],
            },
        )
        assert response.status_code == 200
        answer = response.json()
        assert len(calls) == 2 and answer["status"] == "answered"
        assert answer["usage"]["selection_attempts"] == 2
        assert answer["usage"]["retry_status"] == "attempted"
        assert answer["usage"]["input_tokens"] == 400
        assert answer["usage"]["output_tokens"] == 200
        assert answer["claims"][0]["text"] == answer["claims"][0]["citations"][0]["quote"]
        assert app.get("/api/v1/history").json() == [answer]
        assert "PRIVATE" not in json.dumps(answer)
    with TestClient(create_app(settings, TestGateway())) as restarted:
        assert restarted.get("/api/v1/history").json() == [answer]


def test_record_gate_abstention_is_saved_without_assessment(client, settings, sample_pdf):
    settings.answer_mode = "extractive"
    document_id = upload(client, sample_pdf)
    run_once(settings)

    def respond(request):
        payload = json.loads(request.content)
        source = json.loads(payload["messages"][1]["content"])["excerpts"][0]
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "evidence_assessment": "PRIVATE unsupported event assessment",
                            "requires_individual_record": True,
                            "individual_record_present": False,
                            "answerable": True,
                            "source_ids": [source["id"]],
                        }
                    )
                }
            },
        )

    with TestClient(
        create_app(settings, OllamaGateway(settings, httpx.MockTransport(respond)))
    ) as app:
        answer = app.post(
            "/api/v1/queries",
            json={
                "question": "Has my Orion Supplies order arrived?",
                "document_ids": [document_id],
            },
        ).json()
        assert answer["status"] == "unsupported_question" and answer["claims"] == []
        assert (
            answer["reason"] == "The evidence check did not find the requested individual record."
        )
        assert answer["usage"]["record_gate_withheld"]
        assert answer["usage"]["selected_source_ids"] == []
        history = app.get("/api/v1/history").json()
        assert history == [answer] and "PRIVATE" not in json.dumps(history)


def test_extractive_path_withholds_valid_quote_with_wrong_claim(client, settings, sample_pdf):
    upload(client, sample_pdf)
    run_once(settings)

    class MismatchedGateway(TestGateway):
        answer_strategy = "extractive_source_binding"

        def generate(self, question, evidence):
            return AnswerDraft(
                answerable=True,
                claims=[
                    ClaimDraft(
                        text="The unrelated battery policy lasts 900 years.",
                        citations=[
                            CitationDraft(
                                chunk_id=evidence[0]["chunk_id"], quote=evidence[0]["text"]
                            )
                        ],
                    )
                ],
            ), {}

    with TestClient(create_app(settings, MismatchedGateway())) as updated:
        answer = updated.post("/api/v1/queries", json={"question": "delivery"}).json()
        assert answer["status"] == "unsupported_question" and answer["claims"] == []


def test_model_offline_is_real_error(client, settings, sample_pdf):
    upload(client, sample_pdf)
    run_once(settings)

    class Offline(TestGateway):
        def generate(self, *args):
            raise GenerationError("MODEL_UNAVAILABLE", "Start Ollama.", 503)

    with TestClient(create_app(settings, Offline())) as test:
        response = test.post("/api/v1/queries", json={"question": "delivery window"})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "MODEL_UNAVAILABLE"


def test_stale_worker_cannot_commit(client, settings, sample_pdf):
    document_id = upload(client, sample_pdf)
    first_claim = claim_job(settings.database, 90)
    with connection(settings.database) as con:
        con.execute("UPDATE documents SET lease_until=? WHERE id=?", (time.time() - 1, document_id))
    second_claim = claim_job(settings.database, 90)
    result = parse_pdf(settings.uploads / f"{document_id}.pdf", 100)
    assert not finish_job(settings.database, first_claim, result)
    assert finish_job(settings.database, second_claim, result)
    assert not finish_job(settings.database, second_claim, result)
    assert client.get(f"/api/v1/documents/{document_id}").json()["status"] == "ready"


@pytest.mark.parametrize(
    "kind,expected",
    [("blank", "OCR_REQUIRED"), ("corrupt", "INVALID_PDF"), ("encrypted", "ENCRYPTED_PDF")],
)
def test_unsupported_pdf_content_is_visible(client, settings, kind, expected):
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if kind == "encrypted":
        writer.encrypt("password")
    writer.write(stream)
    content = b"%PDF-1.4\ninvalid" if kind == "corrupt" else stream.getvalue()
    document_id = upload(client, content)
    run_once(settings)
    doc = client.get(f"/api/v1/documents/{document_id}").json()
    assert doc["status"] == "failed"
    assert doc["error_code"] == expected


def test_type_size_origin_and_filename_boundaries(client, settings, sample_pdf):
    bad_type = client.post("/api/v1/documents", files={"file": ("x.exe", b"not a pdf")})
    assert bad_type.status_code == 415
    bad_header = client.post("/api/v1/documents", files={"file": ("x.pdf", b"not a pdf")})
    assert bad_header.status_code == 415
    oversized = client.post(
        "/api/v1/documents", files={"file": ("x.pdf", b"%PDF-" + b"x" * 1_200_000)}
    )
    assert oversized.status_code == 413
    cross_origin = client.post(
        "/api/v1/queries",
        headers={"Origin": "https://untrusted.invalid"},
        json={"question": "anything"},
    )
    assert cross_origin.status_code == 403
    document_id = upload(client, sample_pdf, "../../secret.pdf")
    assert client.get(f"/api/v1/documents/{document_id}").json()["name"] == "secret.pdf"
    assert not list(settings.uploads.glob("*.part"))


def test_fts_query_is_data_not_expression(client, settings, sample_pdf):
    upload(client, sample_pdf)
    run_once(settings)
    assert query_expression('delivery" OR body:secret*') == '"delivery" OR "body" OR "secret"'
    assert retrieve(settings.database, 'delivery" OR body:secret*', [], 4)


def test_page_limit(client, settings, sample_pdf):
    document_id = upload(client, sample_pdf)
    settings.max_pages = 1
    run_once(settings)
    assert client.get(f"/api/v1/documents/{document_id}").json()["error_code"] == "PAGE_LIMIT"
