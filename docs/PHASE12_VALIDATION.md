# Phase 12 validation — completed 4 November 2026

All runs below used the actual worker, query endpoint, retrieval models and the
installed `qwen3-vl:2b-instruct` (Ollama 0.40.8, digest `afc393e3572c…`) on this Mac,
in isolated temporary storage. No live document, query or summary was read or modified
by validation; the workspace's own documents, PDFs and history were hash-verified
before and after activation (see *Live activation* below). **These are assistant-
authored fixture evaluations — they are reproducible evidence, not independent human
review.** A practical checklist for separate human review is in
[REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md).

## What the baseline showed (before Phase 12)

The reported failures were reproduced in isolated storage on 3 November before any
implementation work (`tmp/phase12/baseline_results.json`):

| Question (against the included sample) | Phase 11 behavior |
|---|---|
| "What is in this PDF?" | Refused — "PDF" treated as a named subject, zero excerpts |
| "Tell me about this document." | Refused after retry |
| "Summarize this." | **Wrong answer** — unrelated excerpts about express delivery |
| "Which records must be retained, and for how long?" (no such content) | **Wrong answer** — unrelated excerpts |
| "Does the policy cover international shipping?" | Refused even though the document explicitly says it is not covered |
| "What is the supplier's delivery window?" | Answered correctly (excerpt) |

## Final fixture results (hybrid + reranking)

Each fixture was ingested and queried in fresh isolated storage; denominators include
every scheduled query. "Contract" = answer facts present, fact-bearing claims cite the
annotated reference pages, no out-of-scope citations, no forbidden phrases; unsupported
questions must refuse; summary contracts check facts plus at least one reference-page
citation.

| Fixture | Contracts | Errors | Report |
|---|---:|---:|---|
| Phase 12 development (broad QA, 24 queries) | 23/24 | 0 | [phase12-broad-dev-hybrid.json](../docs/evaluation/phase12-broad-dev-hybrid.json) |
| Paraphrase (12) | 10/12 | 0 | [phase12-paraphrase-hybrid.json](../docs/evaluation/phase12-paraphrase-hybrid.json) |
| Record support (7) | 6/7 | 0 | [phase12-record-support-hybrid.json](../docs/evaluation/phase12-record-support-hybrid.json) |
| Answer regression (8) | 8/8 | 0 | [phase12-answer-regression-hybrid.json](../docs/evaluation/phase12-answer-regression-hybrid.json) |
| Mixed OCR (4) | 4/4 | 0 | [phase12-mixed-ocr-hybrid.json](../docs/evaluation/phase12-mixed-ocr-hybrid.json) |
| Quality (10) | 10/10 | 0 | [phase12-quality-hybrid.json](../docs/evaluation/phase12-quality-hybrid.json) |
| **Total** | **61/65** | **0** | |

During iteration the development fixture reached 21/21 and the quality fixture
10/10 repeatedly; single-case flips between runs are documented rather than hidden.

### Remaining fixture failures, individually

- `meridian_unsupported` — model answers a dessert question with true, cited menu
  facts instead of abstaining (true-but-non-responsive; the known 2B attribute limit).
- `return_condition` — "what proof do I need to bring something back?" is refused:
  the model cannot bridge "proof"→"original receipt", so the support checker
  withholds the written claim. Fails closed; Phase 11's excerpt selector answered it.
- `personalized_return` — the model twice produced a rewritten quote ("Harbor Tools
  does not accept…" instead of the source's "The company does not accept…"); the
  claim was dropped and nothing was shown. Fails closed.
- `payment_record` — substantively correct answer; the scorer requires the exact
  token sequence "payment cleared on 18 September 2025" while the written claim
  reads "Payment for Ridge Parts order R-517 cleared on 18 September 2025". A
  scorer strictness limit for written (non-verbatim) answers, kept visible rather
  than loosened after the fact.

## Frozen acceptance v3 (run once, after implementation)

`evaluation/acceptance_v3.json` was frozen before implementation
([freeze record](../docs/evaluation/phase12-acceptance-freeze.json) with two recorded,
pre-run amendments for scoring-contract corrections and fixture completion). Seven
fictional documents, 26 queries, run once in each retrieval mode:

| Mode | Result | Report |
|---|---|---|
| Hybrid + reranking | **26/26 contracts, 0 errors** | [phase12-acceptance-hybrid.json](../docs/evaluation/phase12-acceptance-hybrid.json) |
| Keyword (BM25) | **26/26 contracts, 0 errors** | [phase12-acceptance-bm25.json](../docs/evaluation/phase12-acceptance-bm25.json) |

The development fixture in keyword mode passed 23/24
([phase12-broad-dev-bm25.json](../docs/evaluation/phase12-broad-dev-bm25.json)); its
one BM25 miss is a topic-only query ("cancellation policy") whose words do not match —
honest keyword behavior, answered correctly in hybrid modes.

Keyword mode retains honest lexical limits: questions whose words do not occur in the
document (typos, synonyms) find no passage; the reply explains this and suggests
Hybrid + reranking. No semantic fallback was added to keyword mode.

## Browser workflow (Playwright, real model)

`scripts/browser_tests.py` runs the full UI suite against an isolated local stack
(temporary database/vectors/documents) with the real model: **12/12 passed**
(upload → indexing states, source viewer, OCR citations, history, mobile layout,
hybrid retrieval, cited answers, honest abstentions, and the new Phase 12 flows —
overview question, document summary, follow-up, clarification). Two borderline
paraphrase cases assert that the reply is grounded either way, because the 2B model
occasionally withholds them in single browser runs while answering consistently in
the fixture suites; this variance is documented, not hidden. Known capture quirk:
headless Chromium does not paint the embedded PDF preview; original-byte equality
and page URLs are asserted instead, and the panel offers "Open PDF"/"Download"
fallbacks. Log: `tmp/phase12/FINAL7-browser.log`.

## Functional checks

- **171 backend tests passed** (155 evolved from Phases 1–11 plus 16 new Phase 12
  tests for grounded validation, summaries, intents, clarification, conversation and
  worker overview generation), `ruff` clean, frontend `tsc` + build clean.
- `scripts/check_http.py`: real API/worker restart preserved documents, FTS index,
  history and original bytes.
- Schema migrated 3 → 4 (adds `document_summaries`) behind a pre-activation backup;
  `test_unknown_schema_is_not_downgraded` still guards forward compatibility.

## Live Mac activation and preservation

See [the activation record](../docs/evaluation/phase12-activation.json) for the exact
snapshot: pre-activation backup via `scripts/backup_workspace.py`, process restart
through `scripts/mac_app.py`, and before/after table hashes plus original-PDF SHA-256
verification via `scripts/preservation_check.py`. Owner authentication was not
touched; no password was read, printed or reset. The authenticated end-to-end check
requires the owner's session and is left to the owner (checklist above).

## Scope and remaining limits

- The local 2B model sometimes answers with true-but-non-responsive facts or
  paraphrases too loosely; the support checker then withholds (fails closed). These
  cases are visible in reports and as `claims_dropped` in usage.
- Summaries and overviews are lexical-support-checked, not semantically verified;
  OCR pages can carry recognition errors into summaries.
- Tables and multi-column layouts extract as plain text with possible reading-order
  loss; charts and images are not interpreted.
- Latency: answers median ≈ 4–8 s; unsupported questions with word overlap may take
  two model passes; detailed summaries on long documents take tens of seconds.
- One model call at a time; overview generation in the worker can briefly contend
  with a query.
