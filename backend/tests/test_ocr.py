import io
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from omnirag.db import MIGRATION_2, SCHEMA, connection, initialize
from omnirag.ingestion import IngestionError, parse_pdf
from omnirag.ocr import OCRError, engine_info
from omnirag.worker import run_once, run_parser
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from .conftest import make_pdf
from .test_workflow import upload

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
requires_tesseract = pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")


def mixed_content_pdf(
    native="LARCH LABORATORY - INSPECTION POLICY",
    boxes=((0, 0, 560, 720),),
    pages=1,
    rotation=0,
):
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(560, 720), invariant=True)
    with Image.new("RGB", (1400, 1800), "white") as image:
        ImageDraw.Draw(image).text(
            (90, 180), "Larch Laboratory inspects seals every 17 weeks.",
            fill="black", font=ImageFont.load_default(size=36),
        )
        for _ in range(pages):
            pdf.setPageRotation(rotation)
            for x, y, width, height in boxes:
                pdf.drawImage(ImageReader(image), x, y, width=width, height=height)
            pdf.setFont("Helvetica", 12)
            for i, line in enumerate(simpleSplit(native, "Helvetica", 12, 480)):
                pdf.drawString(40, 680 - i * 20, line)
            pdf.showPage()
    pdf.save()
    return stream.getvalue()


@requires_tesseract
def test_native_header_scanned_body_is_transcribed_once(tmp_path):
    path = tmp_path / "header.pdf"
    path.write_bytes(mixed_content_pdf())
    native = PdfReader(path).pages[0].extract_text().strip()
    assert 20 <= len(native) < 200 and "17 weeks" not in native
    result = parse_pdf(path, 100)
    text = result["chunks"][0]["text"]
    assert text.count("LARCH LABORATORY") == 1
    assert "inspects seals every 17 weeks" in text
    metadata = result["pages"][0]
    assert metadata["method"] == "ocr"
    assert metadata["ocr_trigger"] == "sparse_text_large_image"
    assert metadata["largest_image_fraction"] == 1
    assert metadata["native_characters"] == len(native)


@pytest.mark.parametrize("boxes,native", [
    (((20, 20, 80, 80),), "A native page with only a small logo."),
    # Large image mostly outside the visible page; bounding boxes are clipped.
    (((550, 0, 560, 720),), "A native page with an off-page image."),
    # Repeated small images must not be summed to cross the threshold.
    (((0, 0, 200, 300),) * 4, "A native page with overlapping small images."),
    (((0, 0, 560, 720),), "Native text remains the selected source. " * 6),
])
def test_logo_offpage_overlap_and_native_heavy_pages_stay_native(
    tmp_path, monkeypatch, boxes, native,
):
    def unexpected(*args):
        pytest.fail("These pages must not invoke OCR")

    monkeypatch.setattr("omnirag.ingestion.recognize_page", unexpected)
    path = tmp_path / "native.pdf"
    path.write_bytes(mixed_content_pdf(native=native, boxes=boxes))
    result = parse_pdf(path, 100)
    assert result["pages"][0]["method"] == "native"
    assert result["chunks"][0]["text"] == native.strip()


@pytest.mark.parametrize("rotation", [0, 90])
def test_large_image_detection_counts_toward_ocr_page_limit(tmp_path, monkeypatch, rotation):
    monkeypatch.setattr("omnirag.ingestion.recognize_page", lambda *args: {"text": "x" * 30})
    path = tmp_path / "two.pdf"
    path.write_bytes(mixed_content_pdf(pages=2, rotation=rotation))
    with pytest.raises(IngestionError) as error:
        parse_pdf(path, 100, ocr_max_pages=1)
    assert error.value.code == "OCR_PAGE_LIMIT"


def test_mixed_content_requires_ocr_and_does_not_keep_header_after_ocr_failure(
    tmp_path, monkeypatch,
):
    path = tmp_path / "header.pdf"
    path.write_bytes(mixed_content_pdf())
    with pytest.raises(IngestionError) as error:
        parse_pdf(path, 100, ocr_enabled=False)
    assert error.value.code == "OCR_REQUIRED"
    monkeypatch.setattr("omnirag.ingestion.recognize_page", lambda *args: {"text": ""})
    with pytest.raises(IngestionError) as error:
        parse_pdf(path, 100)
    assert error.value.code == "NO_TEXT"


@requires_tesseract
def test_mixed_content_failed_then_retried_with_original_citations(client, settings):
    data = mixed_content_pdf()
    document_id = upload(client, data)
    run_once(settings)
    assert client.get(f"/api/v1/documents/{document_id}").json()["error_code"] == "OCR_REQUIRED"
    settings.ocr_enabled = True
    assert client.post(f"/api/v1/documents/{document_id}/retry").status_code == 202
    run_once(settings)
    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["status"] == "ready"
    assert detail["pages"][0]["ocr_trigger"] == "sparse_text_large_image"
    answer = client.post("/api/v1/queries", json={
        "question": "How often does Larch Laboratory inspect seals?",
        "document_ids": [document_id],
    }).json()
    citation = answer["claims"][0]["citations"][0]
    assert "17 weeks" in citation["quote"]
    assert citation["page"] == 1 and citation["extraction_method"] == "ocr"
    assert client.get(f"/api/v1/documents/{document_id}/file").content == data
    assert client.post(f"/api/v1/documents/{document_id}/retry").status_code == 409


@requires_tesseract
@pytest.mark.parametrize("fixture,page", [("scanned_policy.pdf", 1), ("mixed_policy.pdf", 2)])
def test_real_ocr_without_hidden_text_layer(fixture, page):
    path = EXAMPLES / fixture
    assert not PdfReader(path).pages[page - 1].extract_text()
    result = parse_pdf(path, 100)
    ocr = result["pages"][page - 1]
    assert ocr["method"] == "ocr"
    assert len(ocr["language_sha256"]) == 64
    assert ocr["render_dpi"] <= 200
    assert "retained for 7 years" in result["chunks"][page - 1]["text"]
    if page == 2:
        assert result["pages"][0]["method"] == "native"
        assert "3 working days" in result["chunks"][0]["text"]


@requires_tesseract
def test_blank_is_not_indexed(tmp_path):
    path = tmp_path / "blank.pdf"
    path.write_bytes(make_pdf([""]))
    with pytest.raises(IngestionError) as error:
        parse_pdf(path, 100)
    assert error.value.code == "NO_TEXT"


def test_missing_engine_explicit_and_native_still_works(monkeypatch, tmp_path):
    engine_info.cache_clear()
    monkeypatch.setattr("omnirag.ocr.shutil.which", lambda _: None)
    with pytest.raises(IngestionError) as error:
        parse_pdf(EXAMPLES / "scanned_policy.pdf", 100)
    assert error.value.code == "OCR_UNAVAILABLE"
    path = tmp_path / "native.pdf"
    path.write_bytes(make_pdf(["A native text page still works without any OCR installation."]))
    assert parse_pdf(path, 100)["pages"][0]["method"] == "native"


def test_ocr_timeout_is_explicit(monkeypatch):
    def timeout(*args):
        raise OCRError("OCR_TIMEOUT", "OCR exceeded the per-page time limit.")

    monkeypatch.setattr("omnirag.ingestion.recognize_page", timeout)
    with pytest.raises(IngestionError) as error:
        parse_pdf(EXAMPLES / "scanned_policy.pdf", 100)
    assert error.value.code == "OCR_TIMEOUT"


def test_ocr_page_limit_is_atomic(monkeypatch, tmp_path):
    monkeypatch.setattr("omnirag.ingestion.recognize_page", lambda *args: {"text": "x" * 30})
    path = tmp_path / "two.pdf"
    path.write_bytes(make_pdf(["", ""]))
    with pytest.raises(IngestionError) as error:
        parse_pdf(path, 100, ocr_max_pages=1)
    assert error.value.code == "OCR_PAGE_LIMIT"


@requires_tesseract
def test_failed_scan_retry_citations_and_persistence(client, settings):
    data = (EXAMPLES / "mixed_policy.pdf").read_bytes()
    # A fully scanned PDF fails with OCR disabled, then retries the same original/id.
    document_id = upload(client, (EXAMPLES / "scanned_policy.pdf").read_bytes())
    run_once(settings)
    assert client.get(f"/api/v1/documents/{document_id}").json()["error_code"] == "OCR_REQUIRED"
    settings.ocr_enabled = True
    assert client.post(f"/api/v1/documents/{document_id}/retry").status_code == 202
    assert client.post(f"/api/v1/documents/{document_id}/retry").status_code == 409
    run_once(settings)
    assert client.get(f"/api/v1/documents/{document_id}").json()["status"] == "ready"
    document_id = upload(client, data)
    run_once(settings)
    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert [p["method"] for p in detail["pages"]] == ["native", "ocr"]
    answer = client.post(
        "/api/v1/queries",
        json={
            "question": "How long are signed records retained?",
            "document_ids": [document_id],
        },
    ).json()
    citation = answer["claims"][0]["citations"][0]
    assert citation["page"] == 2 and citation["extraction_method"] == "ocr"
    assert client.post(f"/api/v1/documents/{document_id}/retry").status_code == 409
    assert client.get(f"/api/v1/documents/{document_id}/file").content == data
    initialize(settings.database)
    with connection(settings.database) as con:
        saved = json.loads(con.execute("SELECT response FROM query_runs").fetchone()[0])
        assert saved["claims"] == answer["claims"]


def test_schema2_migration_preserves_sources_and_history(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as con:
        con.executescript(SCHEMA + MIGRATION_2)
        con.execute("PRAGMA user_version=2")
        con.execute(
            "INSERT INTO documents(id,name,sha256,size_bytes,created_at,status) "
            "VALUES('old','old.pdf','hash',1,1,'ready')"
        )
        con.execute("INSERT INTO chunks VALUES('old:2:0','old',2,0,'Original text')")
        con.execute("INSERT INTO query_runs VALUES('q',1,'question','{}')")
    initialize(path)
    initialize(path)
    with connection(path) as con:
        assert tuple(con.execute("SELECT * FROM chunks").fetchone()) == (
            "old:2:0",
            "old",
            2,
            0,
            "Original text",
        )
        assert con.execute("SELECT method FROM page_extractions").fetchone()[0] == "native"
        assert con.execute("SELECT response FROM query_runs").fetchone()[0] == "{}"


def test_parser_timeout_kills_descendant(tmp_path):
    marker = tmp_path / "orphan.txt"
    directory_record = tmp_path / "temporary.txt"
    child = f"import time; time.sleep(1); open({str(marker)!r}, 'w').write('orphan')"
    parent = (
        f"import tempfile; open({str(directory_record)!r},'w').write(tempfile.gettempdir()); "
        f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); "
        "time.sleep(30)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run_parser([sys.executable, "-c", parent], timeout=0.4)
    time.sleep(1)
    assert not marker.exists()
    assert not Path(directory_record.read_text()).exists()
