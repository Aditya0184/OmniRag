# Phase 4 — answer and OCR evaluation

Authorized scope: a reproducible local quality baseline after Phase 3 OCR. No cloud services, model downloads, graph retrieval, UI change, schema migration or deployment. The application still exposes the Phase 3 runtime version. This phase measures its behavior without changing generation prompts or retrieval settings.

This describes the original Phase 4 scope. Current runs evaluate the checked-out code, now including [Phase 5 excerpt selection](PHASE5.md); the historical Phase 4 report remains unchanged. With Phase 5 the recorded adapter draft is a server-constructed answer, and usage records the model-selected source IDs and whether an actual model call occurred.

## Run

From the project root, using the existing locked environment:

```bash
# Actual OCR and BM25 only: no Ollama or retrieval-model files needed.
uv run --frozen python scripts/evaluate_quality.py --modes bm25

# OCR and BM25 versus hybrid + reranking: prepared local ONNX models needed.
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
uv run --frozen python scripts/evaluate_quality.py

# Full comparison with actual installed Ollama, serial model calls.
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
uv run --frozen python scripts/evaluate_quality.py --with-model

# Quality gate; requires the model so skipped answers cannot pass.
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
uv run --frozen python scripts/evaluate_quality.py --with-model --strict
```

The default modes are `bm25 hybrid_rerank`. `--modes` also accepts `dense` and `hybrid`; `--repeats 1..5` repeats all queries and preserves each observation. The default is one pass. `--fixture path.json` selects a compatible fixture. `--output path.json` selects a new report location; an existing path is rejected rather than overwritten. The default filename includes a UTC timestamp under ignored `data/local/`.

The evaluator does not need a running app API, browser, frontend or persistent worker. It creates a FastAPI TestClient around the real application, runs the actual bounded worker/parser for ingestion, and owns a separate temporary Qdrant index. Existing app services may remain running. The only HTTP requests leaving the evaluator process are to loopback Ollama with `--with-model`; the model identity is checked before and after the run. The normal local settings are recorded, but `data_dir` is always replaced with temporary storage before initialization. Model files are read from the existing configured locations. No fixture enters the user's document library or query history.

Exit codes:

- **0:** completed experiment without operational errors; quality may still be poor.
- **1:** setup, ingestion, retrieval, model, citation-validation or other execution error. Completed query rows are preserved.
- **2:** `--strict` found a core answer/citation contract miss or core transcription CER > 0.05 / WER > 0.10. Challenge cases do not affect this gate. This is a quality failure, not a test-runner crash.

Reports are checkpointed atomically after ingestion and every query. An interrupted run may remain `running`; it must not be treated as complete. Fatal setup failures are recorded as `failed`. A missing engine/model cannot become a successful skip. Without `--with-model`, answer metrics are `null`, `scored` is zero, and retrieval/transcription results remain available.

## Fixture and provenance

`evaluation/quality_fixture.json` contains five fictional documents, seven pages and ten questions. The core has three native pages, one clean raster scan, five answerable questions, an unsupported birthday question, and a question whose document scope excludes the answer. Challenges cover a lightly degraded scan, a native header over a scanned body, and an instruction embedded inside source text. The latter is a small diagnostic case, not a prompt-injection security evaluation.

PDFs are generated deterministically with ReportLab and Pillow from the exact authored text. Raster-only pages are checked with pypdf to ensure they have no hidden text. The degraded scan uses a fixed 2-degree rotation, fixed down/up-sampling and 0.8-pixel blur; it does not approximate the diversity of real scans. The native-header challenge deliberately exposes the Phase 3 page-level OCR threshold. Fixture pages must fit one chunk; the evaluator fails if chunk overlap would bias transcription scoring. PDF hashes are recorded per document. Package versions, fixture/source SHA-256, effective configuration, pinned retrieval manifest, Ollama version/digest, and per-page OCR engine/language/render metadata are retained.

The JSON report includes original reference text, observed extraction, retrieved passages, raw structured drafts returned by the adapter, accepted API answers/citations, usage and wall time. Unparseable/truncated model output is represented by the adapter's error code; its raw text is not exposed by the production adapter. All report content originates from fictional fixtures. Deterministic fixtures and a fixed model seed improve traceability but do not guarantee bit-identical inference across runtime/hardware versions.

## Metrics and limitations

**Transcription:** character error rate (CER) and word error rate (WER) use Levenshtein edits divided by reference characters/words. Normalize Unicode NFKC and repeated whitespace; retain case and punctuation. Insertions can produce rates above 1. Empty references have undefined rates (`null`); supplied pages have nonempty references. Failed extraction is scored against empty output, and retains its error code. Aggregates sum edit counts and reference lengths within each page-kind/stratum group, rather than averaging page rates. `header_scan` measures full-page extraction loss, not Tesseract recognition accuracy: that page is classified as native and its body never reaches OCR. OCR engine confidence remains metadata and is not an accuracy score.

**Retrieval:** page recall at the configured `top_k` measures how many annotated source pages are in the result set, deduplicated by document/page. Answerable retrieval failures contribute zero; unsupported questions have no reference pages and are excluded from that mean. A retrieved page can still lack the expected scanned text. Page recall cannot establish that the question is answerable from the extracted chunks.

**Answers:** each expected fact has accepted phrase alternatives. Matching uses whole case-folded token sequences, so `14` does not match `114`; all fact groups must match claim text. Citation-page precision/recall compare distinct cited pages with the annotated relevant pages. The strict fixture contract requires expected facts in claims citing reference pages, complete reference-page coverage, no citations outside those pages, and absence of any forbidden phrase. This intentionally penalizes extra citations even if they support tangential facts. It does not evaluate whether every additional claim is true. The summary's citation precision is conditional on answered rows with citations; its denominator is printed separately. Fact-match and contract rates include all scheduled rows in their group, including failures.

**Abstention:** an unsupported question passes only when the API returns `insufficient_evidence` with no claims and no recorded generation/validation error. An invalid citation withheld by the API is a failure, not a correct refusal. The report distinguishes actual model abstention from no-candidate responses via `model.called`. False abstention on an answerable question fails the contract.

These are transparent lexical/location checks, not semantic entailment or a calibrated correctness score. Negation, incorrect relationships, unsupported extra claims with valid quotes, and unlisted but valid paraphrases require human review. A claim can quote a real passage that does not support it. Inspect raw claims, quotes and page images before making quality claims.

Core and challenge summaries are separate. This tiny authored development fixture is not held out, not representative of production documents, and not evidence of general OCR or RAG quality. Latency includes both a search probe and the query endpoint (which searches again), is sequential with no warmup, and is descriptive only. No peak-memory, browser, load, multilingual, handwriting, table or chart evaluation is included.

## Regression checks

```bash
uv run --frozen ruff check backend scripts
uv run --frozen pytest -q
```

The evaluation tests cover edit distances/denominators, Unicode and number boundaries, citation-page mismatches, failure-versus-abstention accounting, deterministic scan PDFs, invalid fixture scope, report preservation and an actual OCR/BM25 run that cannot create the configured live data directory. Actual OCR integration tests skip only when Tesseract is absent; the command-line evaluator itself records missing OCR as failure. Existing CI already installs English Tesseract and runs the test suite. Live-model evaluation remains a separate local experiment, never a mocked quality result.
