# Phase 6 validation — 23 October 2026

Sparse native-header/scanned-body pages now use bounded full-page OCR. The original Maple page improved from **74.82% CER / 72.73% WER to 0% / 0%**, and both retrieval modes answered its 11-year retention question with a page-1 OCR citation. The original strict answer gate still fails on the pre-existing delivery paraphrase. Existing documents, answers and service processes were preserved.

## Observed checks

| Check | Result |
|---|---|
| Backend | **80 passed**, zero skips, 12.08 seconds; one existing upstream Starlette/HTTPX deprecation warning |
| Ruff | Passed for backend and scripts |
| Frontend | TypeScript and Vite production build passed |
| Original quality fixture | **18/20 contracts passed**, 18 actual Ollama calls, no execution errors; strict exit **2** |
| Additional mixed OCR fixture | **8/8 contracts passed**, 8 actual Ollama calls; strict exit **0** |
| Existing additional answer fixture | **16/16 contracts passed**, 16 actual Ollama calls; strict exit **0** |
| Browser | **9 passed**, zero skips, 46.6 seconds; actual Ollama, temporary API/worker/frontend and isolated storage |
| PDF visual inspection | Willow page and both Aspen pages rendered and inspected; native headers and raster policy bodies are readable |
| Live readiness | Frontend HTTP 200, model available, worker active, retrieval loaded, **22 ready semantic indexes** |
| Live data | All rows/hashes unchanged for **28 documents, 41 chunks, 31 queries, 22 vector jobs and 41 extraction records** |

The original fixture hash, evaluator, scorer, generation prompt, retrieval modules and configuration hashes match the accepted Phase 5 run. Only `backend/omnirag/ingestion.py` and `backend/omnirag/ocr.py` changed among the recorded runtime sources. No fixture expectation or answer gate was weakened.

## Original-fixture comparison

| Metric, per retrieval mode | Phase 5 BM25 | Phase 6 BM25 | Phase 5 hybrid + reranking | Phase 6 hybrid + reranking |
|---|---:|---:|---:|---:|
| Core contracts | 6/7 | 6/7 | 6/7 | 6/7 |
| Challenge contracts | 2/3 | **3/3** | 2/3 | **3/3** |
| Unsupported core abstentions | 2/2 | 2/2 | 2/2 | 2/2 |
| Citation-page precision among answered rows | 100% | 100% | 100% | 100% |

All seven original fixture pages now measure zero transcription error. Maple is tagged `ocr`, with `ocr_trigger=sparse_text_large_image`, the native character count and a largest-image fraction of 1.0. Both modes returned the same 11-year source excerpt, with answer text identical to its citation quote. The scanned body was not a hidden text layer in the source PDF.

“How long until my purchased goods arrive?” still abstains in both modes: keyword search returns no passages, while hybrid retrieves the expected page but the unchanged model selection declines it. This keeps strict exit code 2. OCR work did not address that remaining answer-selection issue.

## Additional coverage

The added mixed-content fixture was authored before its first evaluation and used different entities and values: Willow retention for 13 years and reviews every 60 days, Aspen repairs within 9 business days, a native control page, and an unsupported storage-fee question. All eight mode/question combinations passed. Both mixed pages used OCR; the control page stayed native. All three pages had CER/WER zero. The existing Phase 5 answer fixture also retained all 16 passing contracts.

Backend regressions use a separate Larch policy to verify a native header plus scanned body is recovered without duplicating the header. They also check that small logos, mostly off-page images, overlapping small images and native-heavy pages remain native; mixed pages count against the shared OCR-page limit, including a page-rotation case; disabled OCR and unusable OCR output fail explicitly; and failed ingestion can be retried with correct original bytes and OCR provenance. Existing timeout, descendant-cleanup, atomic failure, source persistence and schema tests still pass. The rotation case checks detection and limits with stubbed recognition; it does not establish real OCR accuracy on rotated scans.

The browser suite uploads both the earlier mixed-page example and the new same-page mixed-content example. It checks extraction metadata, actual answers, matching claim/quote text, OCR warnings, page links, original download bytes, saved citations and unsupported refusal. The screenshot shows the Willow 13-year answer and page-1 OCR label. Its embedded native PDF frame had not painted at capture time: URL and byte checks passed, but native viewer painting is not claimed. Temporary browser services were stopped after the suite.

These are small authored development fixtures, not a general OCR or answer-quality benchmark. Full-page OCR can misread previously exact native text. Smaller images, tiled or nested images, and pages with at least 200 native characters can still be missed. Large decorative backgrounds may trigger unnecessary OCR. See [the extraction rule and limits](PHASE6.md).

## Evidence and local operation

- [Original fixture report](evaluation/phase6-quality-mac-2026-10-23.json): 23:56:55–23:57:13 IST.
- [Additional mixed OCR report](evaluation/phase6-mixed-ocr-mac-2026-10-23.json): 23:57:31–23:57:38 IST.
- [Existing answer regression report](evaluation/phase6-answer-regression-mac-2026-10-23.json): 23:59:26–23:59:39 IST.
- Raw ignored reports: `data/local/phase6-quality-2026-10-23.json`, `phase6-mixed-ocr-2026-10-23.json` and `phase6-answer-regression-2026-10-23.json`. Compact reports preserve hashes, runtime/model identities, settings, page metrics and per-question answers/citations.
- Local logs: `data/local/phase6-quality.log`, `phase6-mixed-ocr.log`, `phase6-answer-regression.log`, `phase6-browser.log` and its service logs.
- Data/process evidence: `data/local/phase6-preservation-before.json` and `phase6-preservation.json`; isolated browser harness: `tmp/phase6_browser.py`; screenshot: `frontend/test-results/phase6-mixed_content_policy.pdf-citation.png`.

The model remained local `qwen3-vl:2b-instruct`, digest `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e`, with the existing OCR/retrieval artifacts and limits. No dependencies or models were downloaded. No live documents were uploaded by these checks.

The worker command and cwd were verified against this project. It launches a fresh parser subprocess for each job, so the new extraction path is available for future ingestion without a service restart. Ollama PID 1607, API PID 15645, worker PID 4119 and frontend PID 1610 were unchanged. The local app remains at <http://127.0.0.1:5173>.

Ready documents and historical answers remain unchanged; this step does not reprocess them. Work is local, uncommitted and unpushed. The next separate quality task is the unresolved delivery paraphrase while preserving unsupported-question abstention.
