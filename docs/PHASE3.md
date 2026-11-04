# Phase 3 — local OCR

Authorized scope: English scanned PDFs, mixed native/scanned pages, extraction provenance, original source viewing, and local validation. No deployment, graph retrieval, agents, document editing, new cloud services or paid APIs.

## Processing and limits

The existing worker extracts native text with pypdf. If a page has fewer than 20 normalized text characters, PDFium renders that page and Tesseract recognizes it. Rendering targets 200 DPI, scales down to approximately four megapixels, rejects any rendered dimension above 12,000 pixels, and releases each page bitmap before proceeding. Tesseract uses English data, automatic page segmentation (`--psm 3`) and one OpenMP thread. Only one worker should run.

Defaults, applied even to an existing `.env` unless explicitly overridden:

```dotenv
OMNIRAG_OCR_ENABLED=true
OMNIRAG_OCR_MAX_PAGES=20
OMNIRAG_OCR_PAGE_TIMEOUT_SECONDS=20
OMNIRAG_INGEST_TIMEOUT_SECONDS=90
```

The existing 10 MiB upload, 100-page document and one-million-character extracted-text limits remain. A document may hit the 90-second total timeout before reaching 20 OCR pages. These are guardrails, not measured throughput or an OS memory sandbox: PDF decompression and native extraction can still allocate memory before rendering caps apply.

Missing Tesseract/language data, OCR failures, timeouts and OCR-page overflow fail the document explicitly. A blank document yields `NO_TEXT`; blank pages within an otherwise usable document are recorded and warned about. No partial chunks are committed on execution failure. Disabling OCR restores `OCR_REQUIRED` for image-only files. The parser process group includes Tesseract; timeout kills both and the worker removes its temporary directory.

## Installation and use

Tesseract is a system dependency. On this Mac it was already installed:

```bash
brew install tesseract
tesseract --version
tesseract --list-langs
uv sync --frozen
```

English `eng.traineddata` must be available. No automatic downloads occur at ingestion time. The Python renderer is locked in `uv.lock`. Runtime metadata records the actual Tesseract version, English-data SHA-256, PDFium/pypdfium2 versions, segmentation mode, effective DPI and mean word confidence. System OCR artifacts are observed identities, not enforced pins; upgrading Homebrew may change recognition. Confidence is an engine diagnostic, not calibrated answer confidence.

Upload `examples/scanned_policy.pdf` or `examples/mixed_policy.pdf`. The scanned page has no hidden text layer. Ask the retention-policy question in README. OCR text enters the same SQLite FTS and durable vector-index workflow as native text. Returned evidence and saved citations include `extraction_method`; the source viewer labels OCR transcriptions and opens the original PDF at the cited page.

`GET /api/v1/documents/{id}` includes page extraction metadata. Schema 3 adds a separate table and preserves old chunks, IDs, vector jobs and query history. Previously indexed pages are marked native with `legacy: true`; old unindexed blank pages have no retrospective metadata. Existing ready mixed PDFs are not automatically reprocessed, preserving prior citations.

For a previously failed scan, click **Retry document**. `POST /api/v1/documents/{id}/retry` queues the same original/id, clears the failure and resets its attempt counter. Ready/queued/processing documents return 409. Re-uploading identical bytes still deduplicates; it does not silently alter an old ready document.

## Known limits

- English printed text only. Handwriting, skew, rotation, poor contrast, multilingual pages and complex layouts have not been validated. No deskew or orientation correction is applied.
- The fallback is page-based. A page with a native header of 20+ characters and a scanned body will keep only its native text; hidden text layers are trusted. Mixed content within one page requires future region/layout processing.
- No table structure, chart interpretation, image captions or bounding-box highlights. Quotes match OCR transcription, which may differ from the original image.
- Existing ready documents are immutable in this phase. Versioned reprocessing and editing OCR text remain future work.
- Small authored fixtures validate integration only; no CER/WER benchmark, real-world OCR accuracy or large-corpus capacity claim is made.

Run the checks in README, including `OMNIRAG_E2E_MODEL=1 npm run test:e2e` from `frontend`. Actual OCR tests skip if Tesseract is missing; CI now installs English Tesseract. Mac results must be reported separately from unexecuted CI.

Startup commands remain in README. Keep all services on loopback and stop existing instances before restarting. No subsequent phase is included in this change.
