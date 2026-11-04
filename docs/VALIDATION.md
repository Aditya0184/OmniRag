# Phase 1 validation record

Historical Phase 1 record. Phase 2 and then Phase 3 were subsequently authorized on 23 October 2026; see [Phase 2 validation](PHASE2_VALIDATION.md) and [Phase 3 validation](PHASE3_VALIDATION.md). The results below remain the original Phase 1 observations.

Updated 22 October 2026 (Asia/Kolkata). **The Phase 1 local Mac acceptance gate passed.** This is an engineering validation record using authored fixtures, not an IR/LLM benchmark. Phase 2 has not started.

## Observed Mac environment

Project root: `/Users/aditya/Desktop/OmniRAG/omnirag-ai`. The supplied archive was extracted without replacing unrelated files; the original ZIP remains intact. No `.env` existed in the extracted project, so `.env.example` was copied. The new local model setting was subsequently changed to the validated instruct variant.

| Item | Observed value |
|---|---|
| OS / architecture | macOS 26.6.2 (25G83), Darwin 25.6.0, arm64 |
| Hardware | Apple M1, MacBookAir10,1, 8 GiB unified RAM |
| Disk | 228 GiB data volume; about 5.5 GiB free initially, briefly about 659 MiB under swap pressure, 30 GiB free at final inspection after the user freed storage |
| Python / uv | Project Python 3.11.17; uv 0.13.5; system Python 3.13.0 was also present |
| Frontend runtime | Node 24.15.0, npm 11.12.1 |
| Ollama | 0.40.8, native Apple Silicon runtime, cloud disabled |
| Browser automation | Playwright 1.64.1, Chromium 156.0.8078.4 (build 1248), one test worker |
| SQLite | FTS5 available |
| Final memory snapshot | System-wide free-memory percentage 31%; swap used 9,428.31 MiB. Earlier model/browser load reached about 14% free and roughly 10.4 GiB swap. These are whole-machine snapshots, not model peak-RAM measurements. |

Missing uv and Ollama were installed through Homebrew. `uv sync --frozen --python 3.11` and `npm --prefix frontend ci` installed the existing locks. Chromium installation initially timed out and succeeded on retry. No dependency lock was changed:

```text
uv.lock                      sha256 72b0348d3e7454f3f41b5ba6015c92fea2f861c89cb99df36f6af934bb5fa3e0
frontend/package-lock.json   sha256 f3c6ee685f38328f345f1b1ad45599bc13a3c77ba3805e084a8757ebef9a6e8b
```

## Actual model and runtime correction

The original `qwen3-vl:2b` thinking model exhausted the 768-token output limit. A trial with 1,536 tokens passed one smoke request but still truncated on a fresh browser upload. `think:false` did not disable thinking for these weights. The default and newly created `.env` now explicitly select `qwen3-vl:2b-instruct`, retaining the original 768-token output limit and 4K context. See the [Ollama maintainer explanation of the distinct variants](https://github.com/ollama/ollama/issues/13353).

| Setting | Validated value |
|---|---|
| Model | `qwen3-vl:2b-instruct` |
| Actual installed digest | `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e` |
| Quantization / stored size | Q4_K_M; 1,930,568,531 bytes reported by Ollama |
| Runtime settings | Context 4,096; output 768; temperature 0; seed 42; one generation slot; one loaded model |
| Reported loaded allocation | `ollama ps` reported 2.2 GB, 100% GPU, 4,096 context, llamacpp runner; this is not total system memory use |
| Thinking metadata | Allowed values `[false]`, default `false` |

The actual manifest, including Ollama version and `/api/show` thinking metadata, is saved in ignored `data/local/model_manifest.json`. The earlier thinking-model digest was `0635d9d857d497aeadba3d7d27485746c50554446f9f6ec01ef39788221adbe8` (1,889,519,687 bytes), retained in `data/local/model_manifest-thinking.json`. Both downloaded variants remain installed. Tags may change; reproduce against the recorded digest and re-record it after a pull. No paid inference service was used.

## Mac test results

| Check | Observed result |
|---|---|
| Backend lint | `uv run --frozen ruff check backend scripts` passed. |
| Backend tests | **20 passed**. One upstream Starlette TestClient HTTPX deprecation warning remains. Model calls in this suite use explicit mocks. |
| Frontend build | TypeScript checking and Vite production build passed. |
| HTTP / separate worker | `scripts/check_http.py` passed upload, two-page extraction, indexing and exact original-byte download. The expanded check restarts both processes and verifies documents, FTS retrieval, history and original bytes remain identical. |
| Actual Ollama smoke | `scripts/smoke.py --with-model` passed with the instruct model: 14 calendar days, page-1 citation, validated quotation. Observed total latency 14.760 seconds, 251 output tokens. |
| Full browser suite | `OMNIRAG_E2E_MODEL=1 npm --prefix frontend run test:e2e`: **5 passed in 56.2 seconds**, including the live-model test; no skipped tests in this run. |
| Fresh browser upload | Unique PDF bytes exercised actual ingestion rather than deduplication. Two pages indexed; downloaded bytes matched the uploaded bytes. |
| Answers / citations | Real model answered 14 calendar days on page 1 and 5 business days on page 2. Citation document IDs, quotes, source URLs and page fragments were checked. No JavaScript page errors in the live-model test. |
| Source viewing | Browser assertions passed for quote text, original PDF URLs, page fragments and exact downloaded bytes. Separately opened a persisted answer after restart in desktop Chrome and visually confirmed the embedded original PDF's page 2, including the acceptance-review text. |
| Unsupported question, no lexical match | `Quasizorb nebular xenobiology?` returned `insufficient_evidence`, empty evidence, no model invocation and zero generation time. |
| Unsupported question, matching keyword | `What is the CEO's birthday at Orion Supplies?` retrieved evidence and called the actual model, which returned `insufficient_evidence` with no claims. This one successful abstention does not establish general hallucination resistance. |
| Scanned PDF | Fresh image-only fixture explicitly failed with `OCR_REQUIRED`; the UI displayed the OCR limitation. |
| Mobile layout | Existing mobile overflow check passed. |
| Persistence in active workspace | Restarted API, worker and frontend. All **12 document records**, **11 completed history entries**, FTS results and original-file hashes survived unchanged; saved live-model answers remained accessible in the browser. The 12 records include 8 indexed PDFs and 4 deliberately rejected scan fixtures. |
| Final services | API, Vite and Ollama listened on `127.0.0.1` only. Readiness reported configured model reachable/available and worker active. |

The first browser run with the instruct model had four passes and one fresh-ingestion timeout. Its 30-second test budget was shorter than the documented 90-second parser limit and cold browser startup under memory pressure. Browser startup/ingestion deadlines were aligned with those limits (150-second general test budget; 120-second indexing wait). No application timeout or citation-validation check was relaxed. The complete rerun passed.

The live-workspace restart probe initially requested Vite before it had finished starting; backend persistence assertions had passed. Adding a frontend readiness wait produced a successful complete restart check. The repeatable isolated API/worker restart check is now part of `scripts/check_http.py`.

Observed times from the final browser fixture run:

| Question | Total | Generation | Output tokens |
|---|---:|---:|---:|
| Delivery window | 9.258 s | 9.165 s | 257 |
| Acceptance review | 7.102 s | 7.096 s | 253 |
| Unsupported CEO birthday | 0.692 s | 0.686 s | 12 |
| No lexical match | 9.78 ms | 0 ms | No model call |

These are individual requests under the observed machine load, not averages, percentiles, throughput measurements or quality benchmarks.

Local evidence artifacts (ignored by Git):

- `data/local/browser-final.log`
- `data/local/http-restart-validation.log`
- `data/local/smoke-instruct.log`
- `data/local/restart-validation.json`
- `data/local/final-query-observations.json`
- `data/local/model_manifest.json`
- `frontend/test-results/live-citation-page-1.png` and `live-citation-page-2.png` (captured immediately after opening the source panel; PDF painting was verified separately in desktop Chrome)

## Repository and remaining limitations

The user supplied `https://github.com/Aditya0184/OmniRag`. The archive did not contain Git metadata. The remote's existing initial commit `1d7d221e76c53424d849d9b77c51d4c9d26009a2` was fetched and preserved as the local `main` history, tracking `origin/main`. The supplied implementation was retained over that base. Final status: modified `README.md` plus untracked Phase 1 implementation files; nothing committed, staged or pushed. `.env`, model manifests, uploaded documents, the database, dependencies and test output remain ignored. The original supplied ZIP remains outside this repository.

There are no remaining blockers for this tested local fixture workflow. Limits still apply:

- The 8 GB Mac experienced substantial swap pressure. Keep spare storage, close unused heavy applications and retain one inference slot. Idle weights can be unloaded with `ollama stop qwen3-vl:2b-instruct`; the next query reloads them.
- Only text PDFs and BM25 retrieval are implemented. OCR, dense/hybrid retrieval, reranking, graph retrieval and multimodal processing remain later-phase work.
- Citations verify source IDs and normalized quotations, not semantic entailment, arithmetic or general answer correctness. Only the authored two-page fixture and explicit failure cases were validated here.
- Native PDF page navigation depends on browser support. The quote and Open PDF link remain available; bounding-box highlighting is not implemented.
- There is no authentication or multi-user authorization. The services are for loopback-only development; no VPS inspection, publication or deployment was performed.
- Test fixtures remain in the local workspace. Repeated browser tests add distinct fixture records intentionally. Logical versioning/deletion and a persistent service manager are outside this phase.
- Services are running for this session but are not installed as login services; restart them after a reboot. The upstream TestClient warning remains.

## Restart and reproduce

Application: <http://127.0.0.1:5173>. API documentation: <http://127.0.0.1:8000/docs>.

After a reboot, or after stopping the existing service processes, open four terminals. Do not launch duplicate API/worker processes. The current validation session's process IDs are recorded in `data/local/services.json`; API/worker/frontend logs are in `data/local/logs/`. PIDs are session-specific: inspect the process command before stopping a recorded PID. For processes started interactively with the commands below, use Ctrl-C in each terminal to stop them.

On 23 October 2026, repeated startup commands reported occupied ports because the original API, frontend and Ollama were still running. Health/readiness checks and frontend HTTP 200 confirmed the original stack was healthy. A second worker had started; its executable and working directory were checked and it was gracefully stopped, retaining the original worker. Interactive zsh also treated copied `# Terminal ...` labels as commands; copyable startup blocks now exclude those labels. No application failure or data loss was observed.

Terminal 1 — Ollama:

```bash
cd /Users/aditya/Desktop/OmniRAG/omnirag-ai
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 \
OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 \
OLLAMA_CONTEXT_LENGTH=4096 ollama serve
```

Terminal 2 — API:

```bash
cd /Users/aditya/Desktop/OmniRAG/omnirag-ai
uv run --frozen uvicorn omnirag.main:app --host 127.0.0.1 --port 8000
```

Terminal 3 — worker:

```bash
cd /Users/aditya/Desktop/OmniRAG/omnirag-ai
uv run --frozen python -m omnirag.worker
```

Terminal 4 — frontend:

```bash
cd /Users/aditya/Desktop/OmniRAG/omnirag-ai
npm --prefix frontend run dev -- --host 127.0.0.1
```

The locked dependencies and model are already installed. To rerun validation from the same root with the four services running:

```bash
uv run --frozen ruff check backend scripts
uv run --frozen pytest -q
npm --prefix frontend run build
uv run --frozen python scripts/check_http.py
uv run --frozen python scripts/record_model.py
uv run --frozen python scripts/smoke.py --with-model
OMNIRAG_E2E_MODEL=1 npm --prefix frontend run test:e2e
```

Stop at Phase 1. Phase 2 requires the user's confirmation.

## Earlier supplied Linux record

The following records the supplied code's earlier Linux checks; pending items in this historical table are superseded by the Mac results above. Environment: Linux x86_64, Python 3.12.14, Node 24.19.0.

| Check | Observed result |
|---|---|
| Python lint | Ruff passed for backend and scripts. |
| Backend tests | 20 passed. One upstream Starlette warning concerns future TestClient HTTPX compatibility. |
| Frontend | TypeScript checking and Vite production build passed. |
| Real HTTP/process test | API and separate worker started; PDF upload, two-page extraction, indexing status and original-byte download passed. |
| Model adapter | Structured JSON and timeout/missing-model/error cases checked using explicit HTTP mock transports. |
| Actual Ollama generation | Not executed: Ollama and model weights are not installed in this build environment. Use `scripts/smoke.py --with-model` on the Mac. |
| Browser interaction tests | Written but not executed: Chromium download returned an unavailable-site HTML response rather than a browser archive. No visual/browser success is claimed. |
| Mac compatibility/performance | Pending local doctor, dependency installation, live inference, and browser checks. |
| GitHub integration | GitHub tools are available, but repository listing, OmniRAG search, and installation listing returned no accessible results. No repository was selected or modified. The repository URL and repository access are still needed. |
| Hosted deployment | Not performed; this phase is local-only. |

Passing unit tests does not demonstrate answer correctness, hallucination reduction, calibrated confidence, visual reasoning, or enterprise security. Those require their separately planned modules and evaluations.
