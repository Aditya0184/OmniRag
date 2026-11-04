"""Bounded, sequential English OCR. No model downloads or network calls."""

import csv
import hashlib
import io
import math
import os
import shutil
import subprocess
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c


class OCRError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def largest_image_fraction(document, index: int) -> float:
    """Largest top-level raster's visible bounding box as a fraction of the page.

    Deliberately do not sum overlapping images or traverse Form XObjects: their
    child bounds need composed transforms. This is a sparse-page heuristic, not
    a layout or image-content classifier. PDFium does not decode pixels here.
    """
    with closing(document[index]) as page:
        left, bottom, right, top = page.get_bbox()
        area = (right - left) * (top - bottom)
        if not math.isfinite(area) or area <= 0:
            raise OCRError("OCR_RENDER_FAILED", "Invalid PDF page dimensions.")
        largest = 0.0
        for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=1):
            x0, y0, x1, y1 = obj.get_bounds()
            if not all(math.isfinite(n) for n in (x0, y0, x1, y1)):
                continue
            visible = max(0, min(right, x1) - max(left, x0)) * max(
                0, min(top, y1) - max(bottom, y0)
            )
            largest = max(largest, visible / area)
        return largest


@lru_cache(maxsize=1)
def engine_info() -> dict:
    binary = shutil.which("tesseract")
    if not binary:
        raise OCRError("OCR_UNAVAILABLE", "Install local Tesseract with English language data.")
    try:
        version = subprocess.check_output([binary, "--version"], text=True, timeout=5)
        languages = subprocess.check_output([binary, "--list-langs"], text=True, timeout=5)
        # Tesseract reports the effective tessdata directory, including TESSDATA_PREFIX.
        directory = languages.split('"')[1]
        language = Path(directory) / "eng.traineddata"
        digest = hashlib.sha256(language.read_bytes()).hexdigest()
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        raise OCRError(
            "OCR_UNAVAILABLE", "Tesseract English language data is unavailable."
        ) from exc
    return {
        "engine": version.splitlines()[0],
        "language": "eng",
        "language_sha256": digest,
        "renderer": str(pdfium.PYPDFIUM_INFO),
        "pdfium": str(pdfium.PDFIUM_INFO),
        "page_segmentation_mode": 3,
    }


def recognize_page(document, index: int, timeout: int = 20) -> dict:
    info = engine_info()
    with closing(document[index]) as page:
        width, height = page.get_size()
        if not all(math.isfinite(n) and n > 0 for n in (width, height)):
            raise OCRError("OCR_RENDER_FAILED", "Invalid PDF page dimensions.")
        scale = min(200 / 72, math.sqrt(4_000_000 / (width * height)))
        # Include rounding and reject extremely elongated pages before allocating.
        if max(width * scale, height * scale) > 12000:
            raise OCRError("OCR_RENDER_FAILED", "Page dimensions exceed the OCR render limit.")
        with TemporaryDirectory(prefix="omnirag-ocr-") as directory:
            image = Path(directory) / "page.png"
            with closing(page.render(scale=scale, grayscale=True)) as bitmap:
                pil = bitmap.to_pil()
                try:
                    pil.save(image)
                finally:
                    pil.close()
            try:
                proc = subprocess.run(
                    ["tesseract", str(image), "stdout", "-l", "eng", "--psm", "3", "tsv"],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=True,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                )
            except subprocess.TimeoutExpired as exc:
                raise OCRError("OCR_TIMEOUT", "OCR exceeded the per-page time limit.") from exc
            except (OSError, subprocess.CalledProcessError) as exc:
                raise OCRError("OCR_FAILED", "Tesseract could not recognize this page.") from exc
    words, confidence = [], []
    for row in csv.DictReader(io.StringIO(proc.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") == "5" and (row.get("text") or "").strip():
            words.append(row["text"].strip())
            value = float(row["conf"])
            if value >= 0:
                confidence.append(value)
    return {
        **info,
        "text": " ".join(words),
        "render_dpi": round(scale * 72, 2),
        "mean_word_confidence": round(sum(confidence) / len(confidence), 2) if confidence else None,
    }
