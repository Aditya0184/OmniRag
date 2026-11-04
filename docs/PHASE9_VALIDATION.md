# Phase 9 validation — 26 October 2026

The guarded policy retry is active in the local API. It repairs the three policy abstentions reproduced in Phase 8 without changing the fixtures or their expected facts. The saved-evidence audit passed **164/164 observations**, and fresh endpoint evaluation passed **41/41 hybrid cases**. All unsupported cases were refused. The three existing BM25 no-match cases remain failures in the strict evaluation reports.

## Observed results

| Evaluation | BM25 | Hybrid + reranking |
|---|---:|---:|
| Original quality | 9/10 | 10/10 |
| Policy paraphrases and unsupported questions | 10/12 | 12/12 |
| Explicit record support | 7/7 | 7/7 |
| Answer regression | 8/8 | 8/8 |
| Mixed OCR | 4/4 | 4/4 |
| Total | 38/41 | 41/41 |

Fresh evaluation used temporary storage, actual PDF ingestion/worker processing, retrieval and the production query endpoint. All five fixture digests match their Phase 7 reports. The 82 cases made 77 logical generation calls and 87 actual model requests, including ten retries. There were no execution errors. Unsupported-question abstention and citation-page precision when answered were 1.0 in each applicable group. All evaluated native/OCR transcription groups had zero CER and WER on these synthetic fixtures.

The remaining failures are `delivery_paraphrase` in the original quality fixture, and `unnamed_delivery` and `return_condition` in the paraphrase fixture, all under BM25. Quality and paraphrase therefore still return strict exit code 2; the other three evaluations return 0. No hidden retrieval fallback was added.

## Saved-evidence selection audit

| Measure | Observed result |
|---|---:|
| Contract passes | 164/164 |
| Answerable observations satisfying expected facts | 112/112 |
| Unsupported observations correctly refused | 52/52 |
| Execution errors | 0 |
| Cases passing all four observations | 41/41 |
| Cases with changed cited-answer fingerprints | 0/41 |
| Cases whose selector input changed under reversal | 4/41 |
| Same-input answer changes | 0 |

Retrieved and reversed variants each passed 82/82. This is 164 logical observations and **186 actual model requests**, because 22 observations retried. Retries occurred among `missing_cost`, `named_delivery`, `personal_due_date`, `personalized_return`, `renewal_condition` and `willow_missing_fee`; retry eligibility does not imply that a question is answerable. Unsupported cases that retried still abstained. The three target policy cases passed in all four observations.

The audit ran from 00:42:24 to 00:50:33 IST on 26 October 2026. Median adapter elapsed time was 2.53 seconds for the 142 one-call observations and 5.14 seconds for the 22 two-call observations. These are different case groups in one development run, not a controlled latency comparison. The model remained `qwen3-vl:2b-instruct`, digest `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e`, with 4K context, temperature 0, seed 42 and a shared 768-output-token allowance. The configured 120-second budget is passed to each request as its remaining time; transport timeout semantics remain unchanged.

## Implementation and regression checks

- **120 backend tests passed**, zero skips, in 39.32 seconds, with one existing upstream Starlette/HTTPX deprecation warning. New tests cover identical retry evidence, source-ID validation, malformed/error handling, record/event/name gates, missing usage, shared token/time limits, aggregation and one saved history result across an application restart.
- **10 browser tests passed** in 1.4 minutes against isolated API/worker/frontend services and the actual local model. Upload, OCR provenance, page citations, saved history, unsupported questions and mobile layout passed. The procurement paraphrase retained both its 14-calendar-day duration and purchase-approval condition.
- Frontend production build, Ruff and whitespace checks passed. The isolated HTTP check verified document/history/original-file persistence across API and worker restarts; that check intentionally skips generation, which the endpoint/browser suites exercise separately.
- The browser screenshot was visually inspected: the answer and source quote contain the duration and condition. The embedded PDF area is dark in the captured image, so PDF page painting is not claimed as visually verified; source links and original-file checks are separate evidence.

The production change is confined to the answer adapter. The existing browser test's policy-version assertion was updated, and backend tests/documentation were added. Retrieval, excerpt construction, OCR, dependencies, model versions and database schema are unchanged. Assessments are discarded from production responses/history. A retry can increase input tokens and latency while preserving the output-token cap and existing generation semaphore.

## Development choices and limits

Candidate prompt replacements and alternate schemas recovered some policy answers but introduced unsupported answers. Source grouping/restriction left other misses; model-generated entity fields were unreliable. An unrestricted policy retry passed 41/42 saved cases but incorrectly answered a missing-reservation question. The final candidate added conservative retry gates and passed 42/42 saved cases, including the browser sample, before the full audit and fresh evaluations above. Candidate sources and authored-fixture diagnostics remain under `tmp/phase9/` and `data/local/phase9-*`.

The name gate uses ASCII-capitalized phrases with literal word-boundary matching. It can miss lowercase/non-ASCII names and aliases or reject unusually capitalized valid questions. The event gate recognizes only a small set of English question openings. Neither establishes entity agreement, semantic support or source truth; both only restrict the second call. The original first-pass record classification can also be wrong. Source binding prevents independent claim/quote text mismatch but does not prove relevance or completeness.

These are authored development cases used during tuning, not a held-out benchmark. Reversal changes the selector input for only four cases because the adapter restores page order within each document. The fingerprint ignores claim order, timing and request-local IDs while retaining status, text, document, page and quote. The results do not establish universal robustness or general OCR accuracy.

## Local activation and preservation

After all gates passed, the helper verified the live API command and working directory, stopped PID 31463 and started PID 45230 with the same loopback command. Retrieval loaded, the model was available, the worker was active and the frontend returned HTTP 200. Other service PIDs remained unchanged.

Document/history endpoint responses matched before and after restart. Read-only SQLite row hashes also matched the retained preservation baseline: **28 documents, 41 chunks, 31 query runs, 22 vector jobs and 41 page-extraction records**. No test question or fixture document was inserted into live storage. No migration, reindex, dependency installation, commit, push or deployment occurred.

## Evidence

- [Complete selection audit](evaluation/phase9-selection-mac-2026-10-26.json), with fixed evidence/expectations, answers, source/input hashes, model identity, activation and preservation checks.
- Fresh reports: [quality](evaluation/phase9-quality-mac-2026-10-26.json), [paraphrase](evaluation/phase9-paraphrase-mac-2026-10-26.json), [records](evaluation/phase9-record-support-mac-2026-10-26.json), [answer regression](evaluation/phase9-answer-regression-mac-2026-10-26.json), [mixed OCR](evaluation/phase9-mixed-ocr-mac-2026-10-26.json). Each links its raw local report by path and digest.
- Local logs: `data/local/phase9-backend-final.log`, `phase9-selection.log`, `phase9-validation-chain.log`, `phase9-frontend.log`, `phase9-http.log`, `phase9-restart.json` and `phase9-preservation.json`.
- [Behavior and reproduction guide](PHASE9.md).

This completes the Phase 9 repair. Further quality work should use independently authored held-out questions to assess these retry gates before broadening their use; no subsequent phase is started here.
