# Phase 2 — Local hybrid retrieval

Authorized on 23 October 2026 after the Phase 1 acceptance gate. Scope: dense retrieval, persistent Qdrant, reciprocal rank fusion, a local cross-encoder reranker, and a reproducible retrieval comparison. Text PDFs remain the only input. OCR, image reasoning, graphs, agents, authentication and VPS deployment remain outside this phase.

## Retrieval pipeline

The original parser and SQLite BM25 baseline remain available. The ingestion worker writes page-preserving chunks and a durable `vector_jobs` row in the same SQLite transaction. One API process owns the persistent Qdrant local directory and a background indexer. It indexes existing ready documents automatically and polls for new ones. No additional Qdrant server or Docker installation is required.

| Method | Behavior |
|---|---|
| Keyword search (`bm25`) | Existing SQLite FTS5 ranking; no embedding or reranker required |
| Semantic search (`dense`) | BGE query embedding and cosine retrieval from Qdrant |
| Hybrid search (`hybrid`) | Up to 12 candidates from each retriever, fused using reciprocal rank fusion with k=60 |
| Hybrid + reranking (`hybrid_rerank`) | Top 12 fused candidates rescored by the MiniLM cross-encoder; return up to four passages |

Scores are method-specific: BM25 lower is better, cosine/RRF/reranker higher is better. They are not comparable probabilities or confidence scores. No similarity threshold is claimed to separate answerable from unanswerable questions. Dense retrieval normally produces candidates even for unsupported questions; the generator must still abstain and its quotes must validate. `/api/v1/search` exposes retrieval without calling the generator or writing query history.

The UI allows all four methods and retains the method in saved answers. `hybrid_rerank` is the configured demonstration default, not a claim that it is the best method on every corpus. The authored fixture actually favored dense alone; reranking placed the delivery paraphrase below an irrelevant acceptance-review passage. Compare on your own held-out corpus before selecting a production default.

## Models and memory bounds

| Component | Model / configuration |
|---|---|
| Embeddings | `BAAI/bge-small-en-v1.5`, quantized ONNX export `Qdrant/bge-small-en-v1.5-onnx-Q`, 384 dimensions, MIT |
| Reranker | `Xenova/ms-marco-MiniLM-L-6-v2`, ONNX, Apache-2.0 |
| CPU execution | ONNX CPU provider, two threads per session, batches of eight, no PyTorch |
| Token windows | 256 tokenizer tokens with 32-token overlap, using original source offsets |
| Query limit | 128 tokenizer tokens for semantic methods; over-limit requests return an explicit 422 |
| Generator | Existing Ollama `qwen3-vl:2b-instruct`, 4K context, 768 output tokens, one generation slot |

Exact model revisions and SHA-256 hashes for weights and tokenizer/config files are in `models/retrieval.lock.json`. `scripts/prepare_retrieval.py` downloads those pinned files and verifies checksums. Runtime inference uses the local paths with `local_files_only=True`; it does not download missing models. Checksum/setup failure is visible in readiness, with BM25 still available. Downloads are the only required network step for retrieval setup; no document text is sent to a hosted embedding service.

Phase 1 chunk IDs and quotations are retained. Tokenizer-aware windows are a secondary representation for vectors and reranking, rather than a destructive rechunking of existing sources. A vector points back to its original chunk. Long chunks are embedded in overlapping windows; reranking evaluates all windows and uses their maximum score. Query and document budgets together fit the models' 512-token pair limit. The two pinned tokenizer files are identical. Retrieved vector payloads are checked against the current SQLite text hash, document state and selected scope before becoming evidence.

## Persistence and failure behavior

SQLite migration 1 → 2 runs transactionally and creates `vector_jobs`; existing documents, original files, FTS data and history remain intact. Future unknown schemas are rejected. Before the live migration, a SQLite backup and record/hash snapshot were saved under ignored `data/local/backups/phase1-before-phase2.*`.

Only one API process may own `data/local/qdrant`. The API serializes Qdrant/model operations. A concurrent semantic request during indexing/search receives an explicit busy response. The separate PDF worker never opens Qdrant. Start one API process and one worker; do not use Uvicorn reload/multiple workers with this local index.

A document becomes semantically ready only after all its vector writes succeed. Interrupted `processing` jobs are reset to pending on API startup; delete-and-upsert replay uses deterministic point UUIDs. Model/window changes select a different collection and queue backfill rather than mixing vector spaces. Previous collections are retained. A fresh missing collection also queues a rebuild. Failed jobs remain visible and can be retried with the UI's **Retry indexing** button or `POST /api/v1/retrieval/retry`.

Semantic queries fail explicitly while any selected ready document lacks a complete index. With all documents selected, this includes every text-ready document; selecting an already indexed document or keyword search remains available. There is no silent fallback. Existing scans remain failed with `OCR_REQUIRED` and are excluded.

Qdrant local mode is a small-corpus development choice, not a scalable multi-process deployment. It loads vectors into process memory. Pilot upload/page/text limits remain; total corpus size is not automatically capped. Moving to a Qdrant server, capacity testing and access control require separate work.

## Setup and commands

Run from `/Users/aditya/Desktop/OmniRAG/omnirag-ai`. For a new checkout:

```bash
uv sync --frozen --python 3.11
npm --prefix frontend ci
cp -n .env.example .env
HF_HUB_DISABLE_TELEMETRY=1 uv run --frozen python scripts/prepare_retrieval.py
```

For an existing `.env`, preserve its other settings and set:

```dotenv
OMNIRAG_RETRIEVAL_ENABLED=true
OMNIRAG_DEFAULT_RETRIEVAL_MODE=hybrid_rerank
OMNIRAG_RETRIEVAL_MODELS_DIR=./data/models
OMNIRAG_RETRIEVAL_MANIFEST=./models/retrieval.lock.json
OMNIRAG_RETRIEVAL_CANDIDATES=12
OMNIRAG_RETRIEVAL_THREADS=2
```

For a BM25-only startup, set retrieval enabled to `false` and the default mode to `bm25`. This uses the schema-2 application; running the old schema-1 application against the migrated database is not supported. The pre-migration backup is a historical checkpoint, not an automatic rollback of documents added since migration.

The four service commands remain the same as Phase 1: Ollama, one API, one ingestion worker, and Vite. Restart only stopped services. Open <http://127.0.0.1:5173>. No fifth service is required. Model files are already prepared on the validated Mac.

```bash
uv run --frozen ruff check backend scripts
uv run --frozen pytest -q
npm --prefix frontend run build
uv run --frozen python scripts/check_http.py
HF_HUB_OFFLINE=1 uv run --frozen python scripts/evaluate_retrieval.py
OMNIRAG_E2E_MODEL=1 npm --prefix frontend run test:e2e
```

`scripts/check_http.py` isolates the BM25 process regression in temporary storage even when the live `.env` enables hybrid search. Backend tests use explicit fake encoders for lifecycle/error cases and real Qdrant local storage; they do not claim model quality. The evaluation script uses actual pinned models, actual generated PDFs and the parser/worker in a separate temporary workspace. It does not modify user documents or invoke Ollama. It measures page-level Recall@4, MRR@4, nDCG@4 and observed latency on 12 answerable authored questions; two unsupported queries are separately reported. Model files, revisions, package versions, corpus hash, settings and per-query rankings are recorded. This is a development fixture, not a held-out research benchmark.

See [Phase 2 validation](PHASE2_VALIDATION.md) for actual observed results and limitations. Stop after this phase for review before expanding to the next phase.

## Primary references

- [Qdrant Python client local mode](https://github.com/qdrant/qdrant-client)
- [FastEmbed with Qdrant](https://qdrant.tech/documentation/fastembed/fastembed-semantic-search/)
- [FastEmbed cross-encoder reranking](https://qdrant.tech/documentation/fastembed/fastembed-rerankers/)
- [BGE model card](https://huggingface.co/BAAI/bge-small-en-v1.5)
- [MiniLM ONNX export](https://huggingface.co/Xenova/ms-marco-MiniLM-L-6-v2)
