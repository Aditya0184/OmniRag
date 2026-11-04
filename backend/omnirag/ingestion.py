"""Native PDF text with bounded OCR fallback in a disposable child process."""

import json
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader

from omnirag.ocr import OCRError, largest_image_fraction, recognize_page

EXTRACTOR_VERSION = "pdf_text_ocr_v2"
SPARSE_NATIVE_LIMIT = 200
LARGE_IMAGE_FRACTION = 0.5


class IngestionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = normalize(text)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def parse_pdf(
    path: Path,
    max_pages: int,
    ocr_enabled: bool = True,
    ocr_max_pages: int = 20,
    ocr_page_timeout_seconds: int = 20,
) -> dict:
    rendered = None
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise IngestionError("ENCRYPTED_PDF", "Encrypted PDFs are not supported.")
        if len(reader.pages) > max_pages:
            raise IngestionError("PAGE_LIMIT", f"This PDF exceeds the {max_pages}-page limit.")
        chunks, empty_pages, total_chars = [], [], 0
        pages, ocr_pages = [], []
        for page_number, page in enumerate(reader.pages, start=1):
            text = normalize(page.extract_text() or "")
            metadata = {
                "page": page_number,
                "method": "native",
                "extractor_version": EXTRACTOR_VERSION,
                "native_characters": len(text),
            }
            trigger = "low_native_text" if len(text) < 20 else None
            if 20 <= len(text) < SPARSE_NATIVE_LIMIT:
                if rendered is None:
                    rendered = pdfium.PdfDocument(path)
                fraction = largest_image_fraction(rendered, page_number - 1)
                metadata["largest_image_fraction"] = round(fraction, 4)
                if fraction >= LARGE_IMAGE_FRACTION:
                    trigger = "sparse_text_large_image"
                    if not ocr_enabled:
                        raise IngestionError(
                            "OCR_REQUIRED",
                            "A page has sparse text over a large image. Enable local OCR "
                            "to extract its possible scanned content.",
                        )
            if trigger and ocr_enabled:
                if len(ocr_pages) >= ocr_max_pages:
                    raise IngestionError(
                        "OCR_PAGE_LIMIT", f"PDF exceeds the {ocr_max_pages}-page OCR limit."
                    )
                if rendered is None:
                    rendered = pdfium.PdfDocument(path)
                recognized = recognize_page(rendered, page_number - 1, ocr_page_timeout_seconds)
                text = normalize(recognized.pop("text"))
                if trigger == "sparse_text_large_image" and len(text) < 20:
                    raise IngestionError(
                        "NO_TEXT", "No usable OCR text found on a mixed-content page."
                    )
                metadata.update(method="ocr", ocr_trigger=trigger, **recognized)
                ocr_pages.append(page_number)
            metadata["characters"] = len(text)
            pages.append(metadata)
            total_chars += len(text)
            if total_chars > 1_000_000:
                raise IngestionError("TEXT_LIMIT", "Extracted text exceeds the pilot corpus limit.")
            if len(text) < 20:
                empty_pages.append(page_number)
            for ordinal, chunk in enumerate(split_text(text)):
                if len(chunk) >= 20:
                    chunks.append({"page": page_number, "ordinal": ordinal, "text": chunk})
        if not chunks:
            raise IngestionError(
                "NO_TEXT" if ocr_enabled else "OCR_REQUIRED",
                "No usable text found after OCR. Check the original PDF."
                if ocr_enabled
                else "No usable text found. Enable local OCR for scanned PDFs.",
            )
        warnings = []
        if empty_pages:
            warnings.append(
                f"Little or no usable text on pages {empty_pages}; these pages are not indexed."
            )
        if ocr_pages:
            warnings.append(f"OCR transcription on pages {ocr_pages}. Verify against the original.")
        return {
            "page_count": len(reader.pages),
            "chunks": chunks,
            "warnings": warnings,
            "pages": pages,
        }
    except OCRError as exc:
        raise IngestionError(exc.code, exc.message) from exc
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError("INVALID_PDF", "The PDF could not be parsed.") from exc
    finally:
        if rendered is not None:
            rendered.close()


def main() -> None:
    try:
        options = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        result = parse_pdf(Path(sys.argv[1]), int(sys.argv[2]), **options)
    except IngestionError as exc:
        result = {"error_code": exc.code, "error_message": exc.message}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
