# Phase 13 validation — completed 5 November 2026

All runs used the actual worker, query endpoint, retrieval models and the installed
`qwen3-vl:2b-instruct` (Ollama 0.40.8) on this Mac, in isolated temporary storage.
No live document, query or summary was read or modified by validation. **These are
assistant-authored fixture evaluations — reproducible evidence, not independent human
review.** The reviewer-ready checklist remains
[REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md).

## The four carried-over Phase 12 failures

| Case | Phase 12 result | Phase 13 result | Fix that applied |
|---|---|---|---|
| Dessert question answered with unrelated menu facts | answered (true but non-responsive) | **refused, with a specific reason** | `asked_attribute` steering + server-side attribute withholding |
| "What proof do I need…" refused despite the receipt requirement | refused | **answered with the receipt requirement** | requirement-question reconsideration, even without word overlap |
| Valid answer discarded on a rewritten quote | withheld entirely | **partial answer retained** (receipt claim survives; the exclusion claim is still dropped when the model rewrites its quote) | claim-level quote drops + worked prompt example |
| Correct paraphrase rejected by the scorer | contract failed | **contract passes** | justified subsequence fact matching with positive/negative unit tests |

The new record-code quote rule (a claim may not attach an asked identifier to a quote
that never mentions it) closed an additional fabricated-date path (`due_date_record`)
found during repeated runs.

## Fixture results (hybrid + reranking, final code)

| Fixture | Contracts | Errors | Report |
|---|---:|---:|---|
| Phase 13 development (28 queries: broad, follow-ups, conflict, topic-only, typos) | 27/28 | 0 | [phase13-broad-dev-hybrid.json](../docs/evaluation/phase13-broad-dev-hybrid.json) |
| Paraphrase (12) | 11/12 | 0 | [phase13-paraphrase-hybrid.json](../docs/evaluation/phase13-paraphrase-hybrid.json) |
| Record support (7) | 7/7 | 0 | [phase13-record-support-hybrid.json](../docs/evaluation/phase13-record-support-hybrid.json) |
| Answer regression (8) | 8/8 | 0 | [phase13-answer-regression-hybrid.json](../docs/evaluation/phase13-answer-regression-hybrid.json) |
| Mixed OCR (4) | 4/4 | 0 | [phase13-mixed-ocr-hybrid.json](../docs/evaluation/phase13-mixed-ocr-hybrid.json) |
| Quality (10) | 9/10 | 1 | [phase13-quality-hybrid.json](../docs/evaluation/phase13-quality-hybrid.json) |
| **Total** | **66/69** | **1** | |

The three misses, individually:

- `meridian_conflict` / (acceptance twin `harvest_conflict`) — the model reports the
  current price but not the superseded one. Generation-side 2B limitation; the
  conflict instruction is in the prompt and the failure stays visible.
- `personalized_return` — partial answer: the receipt claim survives; the exclusion
  claim is dropped whenever the model rewrites its quote. Honest partial instead of
  a fabricated completion.
- `instruction_in_source` — the model's output exceeded its token limit twice on the
  injection-heavy passage; the answer is **withheld** with that specific reason
  (`MODEL_TRUNCATED` recorded, nothing unverified shown). The evaluator keeps it
  counted as an execution error by design.

## Stability (repeats)

`broad_dev` was run twice back-to-back with `--repeats 2` (2 × 28 queries) to expose
unstable behavior: **zero unstable cases** — every query produced the same contract
outcome in both repeats ([report](../docs/evaluation/phase13-broad-dev-repeat2.json)).
Median end-to-end latency: 5.6 s per answer.

## Frozen acceptance v4 (run once, after implementation)

`evaluation/acceptance_v4.json` — 8 new documents (resume, policy with exceptions,
manual, conflicting report, scanned nursery policy, marina records, 6-page guide,
injection probe), 26 queries — frozen before any Phase 13 tuning run
([freeze record](../docs/evaluation/phase13-acceptance-freeze.json)):

| Mode | Result | Report |
|---|---|---|
| Hybrid + reranking | **25/26 contracts, 0 errors** | [phase13-acceptance-hybrid.json](../docs/evaluation/phase13-acceptance-hybrid.json) |
| Keyword (BM25) | **25/26 contracts, 0 errors** | [phase13-acceptance-bm25.json](../docs/evaluation/phase13-acceptance-bm25.json) |

The single miss in both modes is `harvest_conflict` (above) — a deliberate challenge
case for a documented 2B limitation. All core answer, refusal, record, scope,
follow-up, summary and injection contracts passed in both modes. Keyword misses on
synonyms/typos continue to be reported honestly with the Hybrid suggestion.

Keyword mode remains explicitly lexical; misses are reported with the suggestion to
use Hybrid + reranking.

## Browser workflows (Playwright, real model)

**12/12 passed** with the real model ([log](../docs/evaluation/phase13-browser-final.log)),
now including assertions that the new page preview actually renders pixels
(`naturalWidth > 100`) in the source panel — visual rendering is verified this time,
not just URL or HTTP status. The suite covers upload states, OCR citations, source
links, history, mobile layout, cited answers, honest abstentions, and the Phase 13
flows (overview question, summary, follow-ups, clarification).

## Review-driven flow fixes (activated separately)

A code review found four UI/renderer issues; each is fixed and covered by a
deterministic regression test that runs without inference: background polling no
longer re-renders unchanged data (which had detached buttons mid-interaction),
conversation/summary state resets only when the selection actually changes, a
clarification choice sends the chosen document explicitly, stale summary responses
cannot overwrite a later selection, and page previews are bounded by pixel
dimensions with explicit resource closing. Verified by 173 backend tests and
**14/14 browser tests with the real model** ([log](../docs/evaluation/phase13-browser-final.log)).

## Functional checks

- **173 backend tests passed** (171 from Phase 12 plus new tests for the preview
  endpoint and fact-matching rule), `ruff` clean, `tsc` + frontend build clean.
  Final suite rerun after the last code change; the activated build matches the
  tested source.
- Memory on the 8 GB Mac: model weights ~1.9 GB on disk (single model, one call at a
  time); API and worker processes stay under ~10 MB RSS each; no new model downloads.

## Latency

Median end-to-end answer latency in the fixture runs: ~4–6 s (hybrid); unsupported
questions that trigger the reconsideration pass take ~7–14 s; summary generation on
short documents ~10–30 s. Exact medians are in each archived report.

## Live activation and preservation

See [phase13-activation.json](../docs/evaluation/phase13-activation.json): pre-activation
backup, service restart through the launcher, and before/after verification that all
documents, chunks, history rows, summaries and original PDFs are unchanged.

## Remaining limitations (unchanged or newly measured)

- The 2B model remains the quality bottleneck (see [MODEL_ASSESSMENT.md](MODEL_ASSESSMENT.md)):
  conflict surfacing usually reports only one of two values; the rewritten-quote case
  still yields a partial rather than complete answer; single-run variance exists on
  borderline paraphrases. A model comparison protocol is documented but was **not**
  executed — downloading models requires owner approval.
- Tables and multi-column layouts remain plain text; images/charts are not
  interpreted; keyword mode stays literal.
