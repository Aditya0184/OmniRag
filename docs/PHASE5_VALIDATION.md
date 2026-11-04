# Phase 5 validation — 23 October 2026

Source-excerpt answers are implemented and active in the local app. Each new answer text is constructed from the same selected excerpt as its citation; the model cannot independently write a claim and attach a different quote. The measured baseline improved, while the original strict quality gate **still fails** on one paraphrased question. The separate additional answer fixture passed all cases. No OCR, retrieval, model-weight, database-schema or dependency changes were made.

## Observed checks

| Check | Result |
|---|---|
| Backend | **71 passed**, zero skips, 11.14 seconds; one existing upstream Starlette/HTTPX deprecation warning |
| Ruff | Passed for backend and scripts |
| Frontend | TypeScript and Vite production build passed |
| Original quality fixture | **20 cases**, 18 actual Ollama calls; completed without operational errors; strict exit **2** |
| Additional answer fixture | **16/16 cases passed**, 16 actual Ollama calls; strict exit **0** |
| Browser | **8 passed in 37.9 seconds**, zero skips, actual Ollama enabled; temporary API/worker/frontend and temporary document/vector storage |
| HTTP/worker regression | Real isolated upload, extraction, download, API/worker restart, saved history and original-byte checks passed |
| Visual inspection | Four new fixture PDF pages rendered and checked; browser screenshot shows the Source excerpts label, matching answer/quote and OCR page-2 citation |
| Live API restart | Verified project command/cwd before replacing API PID 4118 with 15645; worker, frontend and Ollama left running |
| Final readiness | Frontend HTTP 200; model available, worker active, retrieval loaded, **22 ready semantic indexes** |
| Live data preservation | All rows and hashes unchanged for **28 documents, 41 chunks, 31 query records, 22 vector jobs and 41 page-extraction rows**, including after API restart |

The browser suite checks new answer text equals its single citation's quote, displays **Source excerpts**, opens the expected PDF page URL, preserves original PDF bytes, restores citations/history, and still refuses unsupported questions. Backend integration also verifies old history remains unchanged with its legacy verification marker. The screenshot's native PDF frame had not painted at capture time; source URL/bytes passed, but native viewer painting remains a manual limitation.

An initial isolated browser run failed because the temporary frontend used a random port rejected by the application's origin guard. The test-only Vite proxy was configured to supply the permitted local origin, then the entire suite passed. Production origin checks and Vite configuration were not changed; the backend cross-origin rejection test still passed. The initial failed log is preserved and is not counted as success. All temporary browser services were stopped after the suite.

## Comparison on the unchanged Phase 4 fixture

The fixture JSON hash, expected answers and scoring definitions are unchanged. Each mode has five answerable and two unsupported core questions. These small authored development results do not establish general RAG quality.

| Core metric | BM25 Phase 4 | BM25 Phase 5 | Hybrid + reranking Phase 4 | Hybrid + reranking Phase 5 |
|---|---:|---:|---:|---:|
| Answer/citation contract | 5/7 | **6/7** | 3/7 | **6/7** |
| Expected facts matched | 4/5 | 4/5 | 3/5 | **4/5** |
| Correct unsupported abstentions | 2/2 | 2/2 | 2/2 | 2/2 |
| Citation-page precision among answered rows | 87.5% | **100%** | 66.7% | **100%** |
| Answered rows in citation metric | 4 | 4 | 3 | 4 |
| Mean reference-page retrieval recall at 4 | 80% | 80% | 100% | 100% |

Both modes now return only the relevant pressure-code excerpt and the retention-policy excerpt, avoiding the previously observed unrelated extra citations. Hybrid now answers the direct delivery question. The broad paraphrase, “How long until my purchased goods arrive?”, still abstains: BM25 returns no candidates, while hybrid retrieves the correct page but the model declines it. That single core miss per mode keeps the original strict gate at exit 2. No expected answer was relaxed to turn this into a passing run.

Both modes passed **2/3 challenge contracts**, up from 1/3: the degraded-scan question and the instruction-bearing source question passed. The model selected the filter-delivery fact without emitting the injected instruction phrase. This is one diagnostic case, not a prompt-injection robustness claim. The native-header/scanned-body question remains an abstention because its body was never extracted. That unchanged page still measures CER **74.82%**, WER **72.73%**; all other fixture pages measured zero transcription error.

The final original-fixture experiment ran at **20:02:36–20:02:49 IST**. The median combined search/query wall time was 698.74 ms for BM25 and 677.35 ms for hybrid, versus the Phase 4 2,865.62/1,060.65 ms. The output is now short ID selection, cache/warmup state differs, and no controlled latency benchmark was run; these numbers are descriptive only.

## Additional answer cases

The additional authored fixture was fixed before its one live run, using different entity names and values. It covered delivery paraphrasing, entities with conflicting deadlines, similar codes, explicit negation, a required return condition, two facts in one answer, a scope that excludes the named entity, and a missing birthday. **All eight questions passed under each mode**, with citation-page precision 100% and both unsupported cases refused. This run occurred at **21:05:56–21:06:16 IST**.

This is development regression coverage, not a held-out benchmark. It adds evidence beyond the original tuned fixture but does not resolve the remaining original paraphrase failure or guarantee entity handling generally. The final structured adapter, prompt and metric code were unchanged between the final original-fixture and additional-fixture runs.

## Iteration and limits

The first ID-only candidate answered the five core hybrid questions but also chose another company's delivery policy for an unsupported scoped question. Prompt-only entity instructions did not correct that case. Requiring an explicit answerability decision restored both unsupported refusals, at the cost of the remaining paraphrase abstention. The first candidate also selected a native header as an answer; later instructions restored abstention there. All candidate reports are retained; only the selected final candidate appears in the comparison table. The local filename `phase5-quality-final-2026-10-23.json` belongs to an earlier rejected candidate despite its name; the actual final evidence is `phase5-quality-accepted-2026-10-23.json`.

Source binding prevents independent claim/quote text mismatches; it does not establish semantic relevance, complete context, source truth or OCR accuracy. Answers are extractive and may include headings joined to a sentence. The punctuation splitter can mishandle abbreviations and chunk boundaries. Sentences longer than 240 characters are skipped, and at most two excerpts are returned. Calculations, synthesis, multi-sentence qualifications and more complex questions remain limitations. See [PHASE5.md](PHASE5.md).

## Identities, evidence and restart

The final runs used macOS 26.6.2 arm64, Python 3.11.17, Ollama 0.40.8 and `qwen3-vl:2b-instruct`, digest `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e`. The digest was unchanged before and after each evaluation. Context 4,096, output budget 768, temperature 0 and seed 42 were retained. OCR and retrieval artifact identities match Phase 4. No new packages or model files were downloaded.

- [Original-fixture comparison report](evaluation/phase5-mac-2026-10-23.json)
- [Additional answer regression report](evaluation/phase5-answer-regression-mac-2026-10-23.json)
- Raw ignored reports: `data/local/phase5-quality-accepted-2026-10-23.json` and `phase5-answer-regression-2026-10-23.json`; compact reports retain their hashes, source hashes, settings, package/model identities, per-query answers/citations and metrics.
- Local execution evidence: `data/local/phase5-browser.log`, `phase5-browser-initial.log`, `phase5-http.log`, `phase5-preservation.json`, `phase5-restart.json`, and `frontend/test-results/phase5-ocr-citation.png`. The temporary browser harness is retained at `tmp/phase5_browser.py` for inspection.

Application: <http://127.0.0.1:5173>. API docs: <http://127.0.0.1:8000/docs>. Existing services are running; do not launch duplicates. For a later restart, follow [README](../README.md) and verify PID commands before signaling processes listed in `data/local/services.json`.

The expanded fixture initially could not run because automatic approval review reached its usage limit. After the user requested continuation, the retry, browser checks and API restart were approved and completed. There is no remaining approval block for this step. Repository history, remote, `.env`, original documents and older saved answers remain preserved. All changes are local, uncommitted and unpushed. No subsequent phase was started.
