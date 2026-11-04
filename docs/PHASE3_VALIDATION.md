# Phase 3 validation — 23 October 2026

Local English OCR integration passed the checks below on the Apple M1 Mac. The user explicitly selected scanned/mixed-PDF support. This is authored-fixture engineering validation, not an OCR accuracy benchmark. No deployment or subsequent phase was performed.

## Environment and identities

macOS 26.6.2 / arm64, 8 GiB unified RAM; existing Python 3.11.17, Node 24.15.0 and Ollama 0.40.8. Free disk was about 46 GiB initially and 43 GiB at final inspection. The initial system-wide free-memory percentage was 51%; no peak-memory measurement or load/capacity test was performed.

- Tesseract **5.5.1** was already installed at `/opt/homebrew/bin/tesseract` with English data. No OCR system package installation was needed.
- English traineddata SHA-256: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
- Added **pypdfium2 5.14.0** to `pyproject.toml` and `uv.lock`; `uv sync --frozen --offline` passed after updating the lock. No frontend dependency changed. Existing `.env` was preserved.
- Ollama `qwen3-vl:2b-instruct` digest was freshly recorded: `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e`. Retrieval model locks and collection remain unchanged.

## Observed checks

| Check | Result |
|---|---|
| Ruff | Passed for backend and scripts |
| Backend | **42 passed**, zero skips, final run 5.71 seconds; one existing Starlette/HTTPX deprecation warning |
| Frontend | TypeScript and Vite production build passed |
| HTTP/worker | Real isolated upload, extraction, original download and API/worker restart passed, including a repeat after parser temporary-directory cleanup changed |
| Browser | **8 passed in 1.0 minute**, zero skips, with `OMNIRAG_E2E_MODEL=1`; actual Ollama used for answers/abstention |
| Default browser command | **5 passed, 3 intentionally skipped in 15.1 seconds** without the model flag. The retrieval-method test now selects the procurement fixture explicitly, so newly accepted scans cannot change its input |
| Real OCR | Scan-only fixture recovered “Signed records must be retained for 7 years.”; mixed fixture preserved native page 1 and recovered scanned page 2; no hidden text layer exists in either scanned page |
| OCR diagnostic | Mixed scanned page: mean Tesseract word confidence 96.17 at 200 DPI. This is not measured transcription accuracy |
| Retrieval | Scan-only evidence retrieved through BM25, dense, hybrid and hybrid-rerank, with page 1 and `extraction_method=ocr` |
| Actual OCR answer | Scan-only API query and mixed-PDF browser query answered “7 years” with original-page citations marked OCR; exact normalized quotation validation remained enabled |
| Unsupported question | Actual hybrid/Ollama query for the Cedar Archives custodian's birthday returned `insufficient_evidence`, no claims |
| Source/history | Original downloads byte-identical; citation opens the correct page URL; OCR label/warning and saved citations survive browser reload |
| Existing live smoke | Original procurement fixture still answers the 14-day policy with page-1 evidence under hybrid-rerank |
| Migration | SQLite backup taken before schema 2→3. All existing **20 documents, 28 chunks, 21 query records and 14 vector jobs** unchanged immediately after migration |
| Restart | **26 documents, 38 chunks, 30 saved query rows, 20 vector jobs and 38 page-extraction rows** unchanged after API/worker restart. All uploaded-file hashes match, OCR ranking and saved answer unchanged, vector timestamps unchanged |
| Readiness after tested restart | Model available, worker active, retrieval loaded, 20 semantic indexes ready, OCR enabled. Six historical failed scans remain preserved and may be explicitly retried. The subsequent default browser run added two more indexed fixtures |

The new backend coverage includes actual Tesseract recognition, blank-document rejection, missing-engine behavior while native extraction works, explicit OCR timeout errors, atomic page-limit rejection, failed-scan retry, rejecting retries of ready/queued documents, OCR citation persistence, schema-2 preservation and actual process-group timeout cleanup. The timeout test verifies a descendant cannot write after cancellation and that its temporary directory is removed. Model unit tests still use an explicit test double; live-model claims above come from separate browser/API runs.

The first extraction attempt exposed that PDFium page/bitmap objects do not implement Python's context-manager protocol. Explicit `contextlib.closing` fixed cleanup; actual OCR then passed. New tests initially pointed one directory above the examples folder; that test-path error was corrected before the passing run. These failed attempts are not counted as successful tests.

Both new fixture PDFs were rendered with Poppler and visually inspected: text is legible with no clipping. The bundled Poppler emitted fontconfig/cache warnings in this environment but produced inspectable page images. The browser screenshot shows the answer, page-2 OCR quote and warning; its native PDF frame had not painted at capture time. Automated checks verify the source URL and original bytes, **not visual rendering inside the native PDF viewer**. A separate desktop-browser inspection was unavailable because local browser use is disabled in Work settings. The original PDFs themselves were visually checked separately. This remains a manual visual verification limitation.

## Remaining limits

English printed-text fixtures only. No handwriting, skew/rotation, noisy scans, multilingual OCR, table reconstruction, image interpretation, region detection or bounding-box highlighting was validated. A page with at least 20 native characters does not get OCR; a native header plus scanned body can therefore omit body content. Old ready mixed PDFs are not rewritten. Quotes validate OCR transcription rather than image truth; confidence is not calibrated. The actual mixed answer included extra supported policy details beyond the question, so answer concision also remains a small-model limitation.

The 20-page OCR ceiling and 90-second whole-document timeout may reject longer scans. Four-megapixel rendering and one OCR thread limit routine work, but do not constitute a hard memory sandbox. No general CER/WER, throughput or quality claim is made. GitHub CI was updated to install English Tesseract but was not executed remotely.

## Evidence and restart

App: <http://127.0.0.1:5173>. API docs: <http://127.0.0.1:8000/docs>. Existing services were restarted locally; startup commands are in [README](../README.md). Do not start duplicate processes. Check commands for PIDs in `data/local/services.json` before stopping them; PIDs can be reused. Stop existing services with Ctrl-C in their terminals, or signal only verified matching processes, then use the README's four terminal commands.

Ignored local evidence: `data/local/phase3-browser.log`, `phase3-http.log`, `phase3-smoke.log`, `phase3-scan-live.json`, `phase3-restart.json`, `model_manifest.json`, `backups/phase2-before-phase3.sqlite3`, and `frontend/test-results/phase3-ocr-citation.png`. Compact artifact/fixture evidence is saved in [the Mac report](evaluation/phase3-mac-2026-10-23.json).

Git remote remains `https://github.com/Aditya0184/OmniRag.git`; existing history is preserved. Changes remain local, uncommitted and unpushed, including the previously untracked implementation. No paid API, cloud deployment or VPS operation was performed.
