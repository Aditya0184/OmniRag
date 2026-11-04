# Phase 2 validation — 23 October 2026

Historical Phase 2 snapshot. Subsequently authorized OCR work is recorded in [Phase 3 validation](PHASE3_VALIDATION.md); the observations below are unchanged.

**The local Phase 2 implementation and fixture acceptance checks passed.** This is a development validation on the user's Apple M1 / 8 GiB Mac, not a general retrieval benchmark or a claim of production readiness. No Phase 3 work or deployment was performed.

## Environment and pinned artifacts

The previously verified macOS 26.6.2 arm64 environment, Python 3.11.17, Node 24.15.0, npm 11.12.1, Ollama 0.40.8 and Playwright 1.64.1 were reused. Added dependencies are locked in `uv.lock`: FastEmbed 0.9.0, qdrant-client 1.20.0, ONNX Runtime 1.31.0 and tokenizers 0.23.3. The frontend dependency lock did not change. The dependency solver selected Pillow 12.3.0 in place of 13.0.0 for compatibility; PDF/browser fixture checks passed with it.

| Artifact | Observed identity |
|---|---|
| Embedding export | `Qdrant/bge-small-en-v1.5-onnx-Q` revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55` |
| Embedding ONNX SHA-256 | `51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431` |
| Reranker export | `Xenova/ms-marco-MiniLM-L-6-v2` revision `a09144355adeed5f58c8ed011d209bf8ee5a1fec` |
| Reranker ONNX SHA-256 | `c623d0bcb99f4622beb413eaef00cfbe5db20df9f1dd982da4b4f26022881870` |
| Collection | `chunks_97afa178af9bdeece42f`, derived from embedding artifacts and window configuration |
| Ollama generator | Existing `qwen3-vl:2b-instruct`, digest `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e` |

All tokenizer/config checksums are recorded in [the model lock](../models/retrieval.lock.json). Actual retrieval weights occupy approximately 152 MiB on disk; the final pilot Qdrant directory occupied 148 KiB. No Docker VM, hosted vector database or paid API was used.

## Checks and observations

| Check | Observed result |
|---|---|
| Ruff | Passed for backend and scripts |
| Backend tests | **33 passed** in the final run (2.12 seconds); one existing upstream Starlette/HTTPX deprecation warning |
| Frontend | TypeScript and Vite production build passed |
| HTTP/process regression | Real upload, parser worker, original-byte download and API/worker restart passed in isolated temporary storage with BM25 |
| Actual models | Real 384-dimensional embedding and local cross-encoder scoring executed; model checksums validated; API restarted with `HF_HUB_OFFLINE=1` successfully |
| Browser suite | **7 passed in 58.3 seconds**, zero skips with `OMNIRAG_E2E_MODEL=1`; includes the five prior checks plus retrieval-method/scoping checks and fresh PDF → semantic index → actual hybrid answer → citation → saved history |
| Migration preservation | Backed up the schema-1 database before migration. All original 12 document rows, 16 chunks, 11 saved query rows and uploaded PDF hashes were identical after migration to schema 2 |
| Automatic backfill | All eight original text-ready PDFs indexed semantically. Previously rejected scans remained failed |
| New uploads | Fresh unique-byte PDFs indexed in SQLite and Qdrant, with visible semantic status; original downloads remained byte-identical |
| Provenance | Real hybrid answer returned the 14-calendar-day delivery policy with a page-1 citation and exact quote. Phase 1 page-1/page-2 citation tests also passed; source URLs and quotes remain unchanged |
| Unsupported hybrid questions | Both `Quasizorb nebular xenobiology?` and `What is the CEO's birthday at Orion Supplies?` produced dense candidates, called actual Ollama, and returned `insufficient_evidence` with no claims. Observed totals: 1.357 and 1.062 seconds respectively |
| Live smoke | `scripts/smoke.py --with-model` passed under the configured hybrid-rerank default |
| Final restart | API and worker restarted. **20 documents, 28 chunks, 21 saved query records and 14 vector jobs** were unchanged; all original hashes and hybrid evidence rankings matched. Vector-job timestamps were unchanged, confirming no reindex was required |
| Ready state | Model reachable/available, worker active, retrieval loaded, 14 semantic indexes ready, no pending/failed vector jobs. Six scan fixtures remain rejected as intended |

Unit tests use explicit fake encoders for lifecycle/error handling and actual Qdrant storage. They cover schema migration, unknown schema rejection, token-window tails, rank fusion, scoped retrieval, incomplete-index rejection, busy errors, interrupted-job replay, failed writes/retry, model-identity reindexing, stale-payload rejection, offline checksum failures and saved answer provenance. They do not measure model quality. The actual-model evaluation and browser tests are separate checks.

Failures encountered and retained in the record:

- An equal-vector-score test initially changed order after restart. Sorting dense results by score and source ID fixed this; the restart regression then passed.
- The original Ollama process was no longer running when the first live browser suite began, causing a genuine `MODEL_UNAVAILABLE` response. It was restarted with loopback/cloud-disabled/one-model settings.
- The first hybrid browser question, “How long until my purchased goods arrive?”, returned a genuine model abstention despite retrieving the relevant page. The reranker put the acceptance-review page first. This is a model/relevance limitation, not a transport error; no citation checks or model outputs were bypassed. The live answer gate now uses the explicit Orion policy question already used by the baseline. The paraphrase remains in the retrieval fixture, and its reranking error remains in the report below.
- The complete browser suite then passed. The initial log remains at `data/local/phase2-browser-initial.log`; it is not represented as a successful run.

## Authored retrieval comparison

The [fixture](../evaluation/retrieval_fixture.json) contains three generated PDFs, 12 passages/pages, 12 answerable questions and two unsupported questions. It includes exact codes, paraphrases, distractors and a selected-document query. It was written during development and is **not held out**. Each run creates a separate temporary database, ingests real generated PDFs through the parser worker, indexes actual model vectors, compares the four methods and verifies ranking after reopening Qdrant. No LLM is called by this evaluation.

| Method | Recall@4 | MRR@4 | nDCG@4 | Median retrieval time |
|---|---:|---:|---:|---:|
| BM25 | 0.5833 | 0.4306 | 0.4692 | 1.121 ms |
| Dense | 1.0000 | 1.0000 | 1.0000 | 7.348 ms |
| Hybrid RRF | 1.0000 | 0.9167 | 0.9385 | 7.611 ms |
| Hybrid + reranking | 1.0000 | 0.9583 | 0.9692 | 87.840 ms |

These are the actual single-run measurements, with no warmup. They are not percentiles, throughput claims, or evidence of expected behavior on a larger corpus. Model setup took 0.345 seconds and initial indexing 0.148 seconds in that small run. No general peak-memory measurement was performed.

Dense alone ranked every answerable fixture query first. RRF reduced rank-1 accuracy for the safety and reimbursement paraphrases; reranking corrected those but moved the delivery paraphrase to rank 2. This is why methods remain selectable and no universal reranker superiority is claimed. Both unsupported questions still received dense/hybrid candidates; retrieval metrics alone do not establish abstention or answer correctness.

Full per-query results, fixture hash, model hashes, package versions and settings are saved in [the observed Mac report](evaluation/phase2-mac-2026-10-23.json). Reproduce from the project root:

```bash
HF_HUB_OFFLINE=1 uv run --frozen python scripts/evaluate_retrieval.py
```

## Resource and operational limits

At the final inspection, free disk was approximately 28 GiB; system-wide memory free percentage was 15%, with 10,585.94 MiB of swap in use. This includes the user's other applications and is not attributable solely to OmniRAG. ONNX CPU threads and batches are bounded, but the Mac is still under memory pressure. Idle Ollama weights can be unloaded without deleting them; the next answer incurs a cold load. No unattended load test or large-corpus capacity claim was made.

Only one API may own Qdrant local storage. The app explicitly reports incomplete/failed semantic indexes and supports retry; it does not silently substitute BM25. The corpus has no global size cap and local Qdrant is not intended here as a scalable server. The chosen retrieval models are English-focused. No OCR, graph, multimodal or agent capability is enabled, and quotation provenance still does not prove semantic entailment. These remain material limits.

The automated source screenshot captures the answer, quote and source panel immediately; the native PDF viewer may not yet have painted in that image. Source URL/fragment and original-byte checks passed. Phase 1 separately verified native PDF page rendering in desktop Chrome; Phase 2 did not change the viewer implementation.

## Running application and evidence

Application: <http://127.0.0.1:5173>. API docs: <http://127.0.0.1:8000/docs>. Startup commands remain in [README](../README.md); model preparation is already complete on this Mac. Do not start duplicate services. For a restart, first stop the existing verified processes or reboot, then start Ollama, API, worker and frontend in their respective terminals. Current session PIDs are in `data/local/services.json`; inspect their commands before sending a signal because PIDs can be reused. All listeners remain local-only.

Ignored local evidence:

- `data/local/phase2-browser.log` and `phase2-browser-initial.log`
- `data/local/phase2-http.log`, `phase2-smoke.log`, `phase2-unsupported.json`
- `data/local/phase2-restart.json`, `phase2-evaluation.json`
- `data/local/backups/phase1-before-phase2.sqlite3` and `.json`
- `frontend/test-results/phase2-hybrid-answer.png`

The Git remote and existing initial commit remain preserved. Changes are local, uncommitted and unpushed. Test fixture records remain in the workspace intentionally. No VPS or external publication was performed. Phase 3 requires a separate confirmation.
