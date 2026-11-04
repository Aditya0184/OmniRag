# Phase 6 — sparse mixed-content OCR

The original evaluation exposed a native header above an otherwise scanned page. The header exceeded the old 20-character threshold, so only the header was indexed. This step adds a bounded whole-page OCR heuristic for that case. It retains the local model, answer selection, retrieval, database schema, dependencies and original files.

## Extraction rule

1. Extract and normalize native text as before. Fewer than 20 characters still uses the existing OCR path when enabled.
2. For 20–199 native characters, inspect top-level raster image bounds with PDFium. Clip each bounding box to the visible page box and compare the largest individual area with the page area. Do not decode pixels for this check or add overlapping image areas together.
3. If one image covers at least 50% of that area, run the existing full-page Tesseract OCR once. Use its transcription for the entire page, including the header. Do not concatenate native and OCR text, which would duplicate the header. Mark the page and all its citations as `ocr`.
4. Keep native extraction for other pages. Images nested inside Form XObjects are deliberately excluded because their bounds require composed transforms.

New page metadata includes `extractor_version=pdf_text_ocr_v2`, the normalized `native_characters` count and, when inspected, `largest_image_fraction` rounded to four decimals. The unrounded fraction determines the threshold. OCR pages record `ocr_trigger=low_native_text` or `sparse_text_large_image`, in addition to existing engine, language hash, renderer, DPI and confidence metadata. The schema remains version 3; older metadata remains readable.

The 200-character and 50% bounds are explicit development heuristics, not learned or calibrated confidence thresholds. They are not added as new environment settings.

## Limits and failure behavior

The existing 20-page OCR budget counts both triggers together. The approximately four-megapixel render bound, 12,000-pixel dimension limit, one Tesseract thread, 20-second per-page OCR timeout and 90-second parser timeout remain. PDFium page/document resources are closed and parser descendants are cleaned up on timeout.

A detected mixed-content candidate with OCR disabled now fails with `OCR_REQUIRED`, allowing a retry after enabling OCR. OCR execution errors fail the ingestion atomically. If this mixed-content OCR produces fewer than 20 characters, it fails with `NO_TEXT` instead of silently keeping only the header. Errors do not produce partial chunks or a successful ready document.

This does not solve arbitrary mixed layouts. Pages with 200 or more native characters, smaller raster bodies, tiled scans and images inside Forms may still lose scanned text. Large photographs or decorative backgrounds can trigger OCR unnecessarily. Bounding boxes overestimate rotated or irregular image coverage and do not establish that an image contains text. Full-page OCR can misread native text that was previously exact; the OCR label applies to the header too. English OCR, complex reading order, handwriting and table interpretation remain limitations. A successful OCR call is not evidence that all content was recovered.

## Existing documents and local operation

Ready documents and saved answers are not reprocessed. Upload deduplication still returns the existing document for identical bytes; retry remains restricted to failed documents. Updating an already-ready document's extraction requires a separate versioned reprocessing feature. Do not delete or alter an original file to force a reindex.

The worker launches `python -m omnirag.ingestion` in a fresh subprocess for each job, so a running worker uses the updated parser on its next ingestion without a restart. No API, worker or frontend production code outside the parser/OCR modules changed in this step. Avoid starting duplicate services.

## Reproduce

```bash
uv run --frozen python scripts/make_mixed_content_sample.py
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 uv run --frozen python scripts/evaluate_quality.py --with-model --strict
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 uv run --frozen python scripts/evaluate_quality.py \
  --fixture evaluation/mixed_ocr_fixture.json --with-model --strict
```

The original fixture and scorer are unchanged. The additional authored fixture contains Willow and Aspen policies with native headers, different values, a native control page and an unsupported fee question. It was fixed before its first model run. These small fixtures are regression coverage, not a held-out benchmark. See [observed results](PHASE6_VALIDATION.md).

Upload `examples/mixed_content_policy.pdf` in the local app, wait for the semantic index, select it, and ask **For how many years does Willow Records retain signed agreements?** The source says **13 years**. Review the page-1 OCR citation against the original PDF.
