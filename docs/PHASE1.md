# Phase 1 — Environment and first working implementation

Prepared for one advanced developer, one month, M1/8 GB/256 GB Mac, existing Hostinger VPS, and zero additional API budget. This phase runs locally. The observed Mac environment and completed checks are recorded in [VALIDATION.md](VALIDATION.md).

## Objective and scope

Establish a real vertical slice: upload a text PDF, process it in a separate worker, index page-preserving chunks, retrieve passages with SQLite BM25, call local Ollama, validate source IDs/quotes, and open cited PDF pages in React.

This phase deliberately establishes a working lexical baseline before Phase 2 adds dense retrieval, Qdrant, rank fusion, and reranking. It does not claim to implement those components, multimodal analysis, GraphRAG, or enterprise authentication yet.

## Implemented components and files

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | Python package and cross-platform dependency resolution |
| `.env.example` | Documented local settings; no API secrets needed |
| `backend/omnirag/config.py` | Validated settings and data locations |
| `backend/omnirag/db.py` | SQLite schema v1, connections, document/job persistence, atomic index writes |
| `backend/omnirag/ingestion.py` | Text extraction, page references, character chunking, parser errors |
| `backend/omnirag/worker.py` | Single worker, leased jobs, child-process parser timeout, restart recovery |
| `backend/omnirag/retrieval.py` | Safe FTS query construction, BM25 ranking, selected-document filtering |
| `backend/omnirag/generation.py` | Real Ollama HTTP adapter, structured output schema, citation provenance checks |
| `backend/omnirag/security.py` | Local browser-origin checks and bounded request consumption |
| `backend/omnirag/main.py` | API routes, upload storage, readiness, query execution, history |
| `backend/tests/` | API, recovery, source mapping, retrieval scope, parser and model-boundary tests |
| `frontend/src/App.tsx` | Upload/status, questions, history, evidence and original-PDF viewer |
| `frontend/src/api.ts` | Typed API client and error translation |
| `frontend/src/styles.css` | Responsive workspace styling with Tailwind integration |
| `frontend/vite.config.ts` | Local API proxy; browser requests stay same-origin |
| `frontend/tests/` | Real upload/source-view, mobile layout, OCR rejection, history, and optional real-model checks |
| `frontend/package.json`, `frontend/package-lock.json` | Exact frontend dependencies |
| `scripts/doctor.py` | Read-only environment inventory |
| `scripts/make_sample.py` | Reproducible fictional PDF fixture generation |
| `scripts/make_scan_sample.py` | Reproducible image-only PDF for checking explicit OCR rejection |
| `scripts/smoke.py` | Live HTTP checks; optional real model test |
| `scripts/check_http.py` | Isolated real API/worker process test using temporary storage |
| `scripts/record_model.py` | Capture actual Ollama version/model digest/settings |
| `examples/procurement_sample.pdf` | Two-page source fixture |
| `.github/workflows/ci.yml` | Backend lint/tests and frontend build; not a deployment workflow |

The archive contains complete code for every current module. There are no placeholder graph/agent/vector classes that pretend to work.

## Dependencies and environment

Use the README commands with `uv sync --frozen` and `npm ci` to install the lockfiles. The development dependency group includes pytest, Ruff, and ReportLab; runtime code does not need ReportLab. The frontend uses React, TypeScript, Vite, Tailwind, and Lucide icons. Browser testing additionally requires a Playwright browser download.

| Variable | Default | Meaning |
|---|---|---|
| `OMNIRAG_DATA_DIR` | `./data/local` | SQLite database, uploaded originals and local model manifest; run from project root |
| `OMNIRAG_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local model server; requests intentionally ignore ambient proxy variables |
| `OMNIRAG_OLLAMA_MODEL` | `qwen3-vl:2b-instruct` | Model to pull and execute; image capability is unused in Phase 1 |
| `OMNIRAG_MODEL_TIMEOUT_SECONDS` | `120` | Per-network-operation read timeout; not a strict end-to-end wall-clock deadline |
| `OMNIRAG_CONTEXT_TOKENS` | `4096` | Ollama context setting |
| `OMNIRAG_MAX_OUTPUT_TOKENS` | `768` | Output allowance for cited answer JSON |
| `OMNIRAG_TOP_K` | `4` | Maximum retrieved chunks included in a query |
| `OMNIRAG_UPLOAD_MAX_MB` | `10` | Per-PDF byte limit in MiB |
| `OMNIRAG_MAX_PAGES` | `100` | Maximum PDF pages accepted by the parser |
| `OMNIRAG_INGEST_TIMEOUT_SECONDS` | `90` | Hard timeout for the disposable parsing child process |

The 768-token output allowance accommodates citation JSON. The original `qwen3-vl:2b` tag exhausted 768 tokens on the sample and still exhausted a trial 1,536-token budget on a fresh browser upload. Its thinking could not be disabled with `think:false`. Phase 1 therefore selects `qwen3-vl:2b-instruct` explicitly, retaining the original 768-token allowance, 4K context, single generation slot, and 120-second timeout. This is a runtime compatibility fix, not benchmark tuning. Character chunks are 900 characters with 120-character overlap; this is not token-aware semantic chunking. Embedding-tokenizer-aware chunking belongs to Phase 2.

Use a single Uvicorn application process and one worker. The one-generation-at-a-time limit is process-local. Do not start multiple API workers and assume a global inference limit exists.

The worker and API share a local SQLite database, not a network filesystem. The worker claims a document transactionally, creates a lease longer than the parser timeout, and atomically stores its chunks and FTS index. A stale worker cannot commit after another worker has taken over its lease. Expired leases may be recovered up to three attempts. Invalid/encrypted/scanned PDFs fail explicitly rather than being retried indefinitely.

SQLite schema v1 is initialized on startup. Subsequent schema changes must introduce explicit migrations; do not alter `CREATE TABLE` declarations and expect existing databases to migrate automatically.

## Execution sequence and expected outputs

1. Install tools and locked dependencies; copy `.env.example` without replacing an existing `.env`.
2. Run the doctor. On the intended Mac, expect `Darwin` and `arm64`, SQLite FTS5 availability, installed Node/uv, and sufficient disk. Check macOS against current Ollama requirements.
3. Start Ollama and pull the configured model. Record its digest using `scripts/record_model.py`.
4. Start API, worker, and frontend using the README's three terminals.
5. Open `/api/v1/health`. Expected JSON includes `status: ok`, `phase: 1`, `retrieval: bm25`, and `authentication: false`.
6. Open the UI, upload the included PDF, and observe `queued → processing → ready`. Fast processing may skip a visible intermediate state between polls.
7. The sample should report two pages. Ask about the Orion delivery window; the expected supporting text on page 1 says 14 calendar days. Ask about acceptance review; page 2 says 5 business days.
8. Click a citation to open the corresponding original PDF page and view its quoted text. PDF page fragments depend on the browser's PDF viewer; an external PDF link remains available. Bounding-box highlighting is not implemented.
9. Ask an unsupported question. With no lexical matches, the system abstains without calling the model. With irrelevant keyword matches, abstention depends on the model and is imperfect.
10. Restart the API and worker. Documents, indexes, and completed-query history should persist. Restarting a worker during parsing may require waiting for the 120-second default lease before recovery.

No model response is hardcoded. The sample's expected values are test assertions about the fictional source. They do not guarantee that a selected model will answer correctly.

## API contract

| Method and path | Purpose |
|---|---|
| `GET /api/v1/health` | Database/API liveness |
| `GET /api/v1/readiness` | Model reachability, configured model availability, worker heartbeat |
| `POST /api/v1/documents` | Multipart PDF upload; HTTP 202 and document metadata |
| `GET /api/v1/documents` | Document inventory with processing/error states |
| `GET /api/v1/documents/{id}` | Current document state |
| `GET /api/v1/documents/{id}/file` | Original PDF bytes |
| `POST /api/v1/queries` | Question plus optional document UUID list |
| `GET /api/v1/history` | Last 20 completed responses |

An empty document filter means all ready documents in this local workspace. This is query scoping, not authorization. UUIDs do not substitute for access control.

Every returned citation obtains its filename/page from server-side evidence metadata. The model supplies a chunk ID and quotation; invalid or blank quotations are rejected. Source-quote validation is an integrity check, not an entailment model. A plausible but unsupported claim accompanied by a genuine unrelated quote can still pass it. The UI makes this limitation visible.

Identical file bytes are deduplicated by SHA-256. Changed bytes create a separate document; logical document versioning and deletion are not implemented yet. If a failed job requires reprocessing after a code change, use a separate pilot data directory or an explicit future retry mechanism; re-uploading identical bytes preserves the existing state.

## Tests and completion checks

The automated suite verifies real PDF parsing, original-byte preservation, page citations, persistence after API recreation, duplicate handling, selected-document filters, stale-worker protection, parser rejection, upload boundaries, no-evidence abstention, missing-model errors, and the structured Ollama HTTP contract.

Model calls in unit/API tests use explicit test doubles or HTTP mock transports. Production requests always use the real adapter; there is no synthetic-answer fallback. `scripts/check_http.py` launches real processes and performs actual HTTP upload, worker processing and source download, without a model. It then restarts the API and worker and verifies documents, FTS results, history and original bytes.

Run `scripts/smoke.py --with-model` on the Mac to validate actual model inference, expected sample content, and page-1 citation. Run Playwright with API/worker/frontend active to validate the browser flow. `OMNIRAG_E2E_MODEL=1 npm --prefix frontend run test:e2e` also checks live answers on pages 1 and 2 and model abstention on an unsupported question with matching keywords. The other browser checks cover fresh ingestion, original bytes, saved history, scanned-PDF rejection and mobile overflow. Regenerate the image-only fixture with `uv run python scripts/make_scan_sample.py` if needed. Browser tests intentionally add fixture documents/history to the local workspace. Complete the Mac acceptance gate before proceeding to Phase 2.

## Common errors and fixes

| Symptom | Cause and action |
|---|---|
| `uv` or `node` missing | Install prerequisite tools; make sure Homebrew's Node 22 executable is on PATH. |
| Vite refuses the Node version | Use Node 22.12+; the lockfile uses a modern Vite release. |
| `no such module: fts5` | Use uv's supported Python build with SQLite FTS5, then recreate the environment. |
| File stays queued | Start the separate worker from the same repository root with the same `.env`. |
| Worker appears offline during startup | Wait for its heartbeat; inspect its terminal if it remains offline. |
| `OCR_REQUIRED` | The PDF has no usable text. Use a text PDF for Phase 1; OCR arrives later. |
| `PAGE_LIMIT`, `UPLOAD_TOO_LARGE` | Use a smaller document or adjust the documented development limits. |
| `MODEL_UNAVAILABLE` | Start Ollama and check the configured host/port. |
| `MODEL_NOT_FOUND` | Pull exactly the model named in `.env`. |
| `MODEL_TIMEOUT` | Reduce the question/context load, close other heavy apps, then retry; measure before increasing timeouts. |
| `MODEL_TRUNCATED` | Try a shorter question or cautiously increase the output-token allowance. |
| `MODEL_BUSY` | One answer is already running; wait for completion. |
| Invalid citations / withheld answer | The model did not copy a valid source reference/quote. Inspect retrieved evidence; do not disable validation to hide failures. |
| UI cannot reach API | Start FastAPI on port 8000; Vite proxies `/api` there. |
| `Address already in use` | Stop your prior process or align both API port and Vite proxy before changing ports. |
| Browser download fails | Browser tests require downloading Chromium; code/build/API tests remain independently runnable. |

## Phase 1 acceptance checklist

- [x] Verify macOS, architecture, RAM pressure and free storage.
- [x] Install the locked Python and frontend dependencies.
- [x] Start Ollama and record the configured model digest.
- [x] Pass backend lint/tests and frontend build.
- [x] Pass the isolated HTTP/worker smoke test, including process restart.
- [x] Pass the real-model smoke test on the M1.
- [x] Upload a fresh text PDF through the browser and inspect page-1/page-2 citations; visually verify the original PDF viewer.
- [x] Check unanswerable questions with and without lexical overlap, and a scanned-PDF failure.
- [x] Restart API, worker and frontend; verify persistent documents, FTS, originals and completed answers.
- [x] Configure the user-supplied GitHub remote and preserve its existing history locally.

The local acceptance gate passed on 22 October 2026. VPS inspection, deployment and GitHub publication are deferred by the user's local-only scope; they are not blockers for this gate. The implementation remains uncommitted for review. See the validation record for limitations and reproducible commands.

Pause here for review. Phase 2 adds dense retrieval, Qdrant, fusion and reranking only after confirmation.
