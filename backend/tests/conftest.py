import io

import pytest
from fastapi.testclient import TestClient
from omnirag.config import Settings
from omnirag.generation import (
    AnswerDraft,
    CitationDraft,
    ClaimDraft,
    GroundedAnswerDraft,
    GroundedCitationDraft,
    GroundedClaimDraft,
)
from omnirag.main import create_app
from reportlab.pdfgen import canvas


def make_pdf(pages: list[str]) -> bytes:
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, invariant=True)
    for text in pages:
        pdf.drawString(50, 740, text)
        pdf.showPage()
    pdf.save()
    return stream.getvalue()


class TestGateway:
    """Explicit test double for the legacy extractive path."""

    __test__ = False

    def ready(self):
        return {"reachable": True, "model_available": True, "model": "test-double"}

    def generate(self, question, evidence):
        quote = evidence[0]["text"][:150]
        return AnswerDraft(
            answerable=True,
            claims=[
                ClaimDraft(
                    text=quote,
                    citations=[CitationDraft(chunk_id=evidence[0]["chunk_id"], quote=quote)],
                )
            ],
        ), {"input_tokens": 100, "output_tokens": 20}


class GroundedTestGateway(TestGateway):
    """Explicit test double for the grounded written-answer path."""

    __test__ = False

    calls: list = []

    def generate_grounded(self, question, evidence, conversation=None, intent=None):
        type(self).calls.append(
            {"question": question, "conversation": conversation, "intent": intent}
        )
        text = evidence[0]["text"][:200]
        return GroundedAnswerDraft(
            answerable=True,
            claims=[
                GroundedClaimDraft(
                    text=text,
                    citations=[
                        GroundedCitationDraft(chunk_id=evidence[0]["chunk_id"], quote=text)
                    ],
                )
            ],
        ), {"model_called": True, "input_tokens": 100, "output_tokens": 20}


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, upload_max_mb=1, ocr_enabled=False)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, TestGateway())) as client:
        yield client


@pytest.fixture
def grounded_client(settings):
    with TestClient(create_app(settings, GroundedTestGateway())) as client:
        yield client


@pytest.fixture
def sample_pdf():
    return make_pdf(
        [
            "Orion Supplies has a standard delivery window of 14 calendar days.",
            "The acceptance review must be completed within 5 business days.",
        ]
    )
