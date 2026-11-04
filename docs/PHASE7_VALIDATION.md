# Phase 7 validation — 24 October 2026

The selected adapter recovers the original delivery paraphrase under hybrid retrieval while retaining all earlier answer and OCR regression passes. The additional policy/status fixture now refuses all unsupported questions, with three remaining hybrid policy abstentions. The original combined strict gate still fails on keyword retrieval's unchanged no-match case. This is a measured local improvement with remaining coverage limits, not a general accuracy claim.

## Full evaluation results

All five selected-adapter runs completed without execution errors, using the actual production worker/query endpoint in isolated storage. They scheduled **82 cases and made 77 actual Ollama calls**. OCR/native transcription scored zero CER and WER on every fixture page. All original fixture/scorer expectations remain unchanged.

| Fixture | Keyword contracts | Hybrid + reranking contracts | Strict exit |
|---|---:|---:|---:|
| Original quality, including challenges | **9/10** | **10/10** | 2 |
| Additional policy/status paraphrases | **8/12** | **9/12** | 2 |
| Explicit individual records | **7/7** | **7/7** | 0 |
| Existing Phase 5 answer regression | **8/8** | **8/8** | 0 |
| Existing Phase 6 mixed OCR regression | **4/4** | **4/4** | 0 |

The original core hybrid contracts improved from **6/7 to 7/7**; both modes retained all three challenge passes and both unsupported refusals. The paraphrase “How long until my purchased goods arrive?” now selects the complete 14-calendar-day policy, including its purchase-approval condition. Keyword search still returns no evidence and makes no model call for this question. No synonym list or hidden semantic fallback was added to BM25.

## New fixture comparison and remaining misses

The new 12-question policy/status fixture was fixed and evaluated against Phase 6 before prompt experiments. Baseline contracts were **6/12 keyword and 8/12 hybrid**; the selected adapter reaches **8/12 and 9/12**. Unsupported abstentions improve from **4/6 to 6/6 in both modes**, removing false answers to personal payment and reservation questions. Citation-page precision among answered rows rises from 50%/66.7% to 100%/100%.

Answerable fact-match rates remain **2/6 keyword** but decline from **4/6 to 3/6 hybrid** compared with Phase 6 on this additional fixture. The final adapter recovers the receipt-requirement paraphrase under hybrid but abstains on the globally scoped Harbor delivery question, Meadow renewal condition, and personalized-equipment prohibition. Correct reference pages were retrieved for all three hybrid misses. Keyword misses are unnamed delivery, renewal, receipt requirements and personalized returns. This is a real tradeoff: better unsupported refusal and the original delivery recovery, with less answer coverage on the additional authored policies. The strict gate and expected answers were retained.

The seven-case record-support fixture was fixed before evaluating the record gate. It verifies explicit payment, delivery, due-date and reservation records can be answered, while similar missing order/loan IDs are refused. All 14 mode/question combinations pass. The delivery-record answer also selects the same page's payment sentence; the lexical/page metrics do not penalize that extra fact. This limitation is retained for manual review.

The adapter's additional server record gate did not override a model answer in these final live evaluations (`record_gate_withheld` was false throughout). The model itself abstained. Unit and API tests separately demonstrate that the server withholds an otherwise selected answer if the model flags a required individual record as absent. This distinction avoids attributing measured improvements to an unobserved enforcement event.

## Candidate selection

The prompt and structured fields were tuned using authored development cases. None of these results is a held-out benchmark. Earlier prompt-only changes retained the original miss and introduced wrong-entity answers. Selecting IDs before answerability recovered the original paraphrase but increased unsupported answers, so that design was rejected. A bounded assessment before selection passed 32/34 replayed hybrid cases but still falsely answered two personal-status questions. Record classification after assessment resolved those false answers.

Candidate 8 passed the full original hybrid fixture but failed the browser's unchanged procurement PDF. Prompt variants and a longer assessment did not resolve this; unrestricted adjacent-sentence pairing passed the sample but regressed two earlier paraphrases (31/34 hybrid replay). Keeping only short linked pairs together passed 32/34 replay cases and the direct sample, but still failed in the browser. The isolated endpoint showed the reranker placed the acceptance page before the delivery policy; reversing the direct probe reproduced the refusal. The final candidate builds its excerpts in document/page order, preserving public retrieval scores and evidence. With linked conditions retained, the exact endpoint input and all ten browser tests pass.

The full final five-fixture run—not the earlier replay—supplies the results above. In particular, it exposed a personalized-return abstention that the earlier replay did not have. Candidate 8 had scored 10/12 hybrid on the new fixture; the final candidate scores 9/12 while fixing the browser case. Selection remains sensitive to source presentation.

Diagnostic replays use saved retrieved passages; they are not end-to-end retrieval measurements. Raw candidate reports/logs and source snapshots are preserved under `data/local/phase7-*` and `tmp/phase7/`. Candidate 3 stopped after one case with inconsistent model output and is not a completed success. The final runtime retains strict output consistency and unknown/duplicate-ID rejection; it does not use the rejected provisional-ID relaxation.

## Application checks

- **93 backend tests passed**, zero skips, 16.13 seconds; one existing upstream Starlette/HTTPX deprecation warning.
- Ruff, TypeScript/Vite build, and the isolated HTTP/worker persistence check passed. The HTTP check skips model generation; actual generation is covered separately by the evaluations and browser tests.
- **10 browser tests passed**, zero skips, 1.2 minutes, using actual Ollama and isolated API/worker/frontend storage. The new test verifies the original delivery paraphrase, both the duration and approval condition, exact claim/quote equality, source page, history restoration and unsupported personal-shipment refusal.
- The inspected screenshot at `frontend/test-results/phase7-paraphrase.png` shows the complete policy and matching quote. The embedded native PDF frame had not painted at capture time; native viewer painting is not claimed.
- Original quality, earlier answer regression and mixed OCR fixture hashes remain unchanged. Only `generation.py` and `main.py` changed among the recorded runtime/evaluator modules since Phase 6.

## Cost and limits

On the original fixture, median model output increased from **16 to 85 tokens**. Median combined search/query time for core cases rose from approximately **700/673 ms to 2,374/2,627 ms** for keyword/hybrid. These runs had different cache, warmup and host conditions and are not controlled latency benchmarks. The assessment is bounded and discarded, but still consumes generation time under the unchanged 768-token cap and 4K context.

The record flags and assessment remain model judgments. Source binding prevents independently written claims from being paired with unrelated quotes; it does not prove relevance, complete context, source truth or record freshness. English OCR limits and the two-excerpt/240-character quote limits remain. Linked-pair handling is a literal English heuristic and does not establish context completeness. See [the implementation guide](PHASE7.md).

## Runtime identities and evidence

The final runs retain local `qwen3-vl:2b-instruct`, digest `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e`, macOS 26.6.2 arm64, Python 3.11.17 and the previous OCR/retrieval artifacts. No model/dependency installation, database migration or reindex was performed. Only `generation.py` and `main.py` changed among the recorded runtime source modules since Phase 6.

- [Original quality report](evaluation/phase7-quality-mac-2026-10-24.json)
- [Policy/status baseline](evaluation/phase7-paraphrase-baseline-mac-2026-10-24.json) and [selected-adapter report](evaluation/phase7-paraphrase-mac-2026-10-24.json)
- [Explicit record support](evaluation/phase7-record-support-mac-2026-10-24.json)
- [Existing answer regression](evaluation/phase7-answer-regression-mac-2026-10-24.json)
- [Existing mixed OCR regression](evaluation/phase7-mixed-ocr-mac-2026-10-24.json)

Final raw reports use `data/local/phase7-*-ordered-2026-10-24.json`; the policy/status baseline has no `-ordered` suffix. Earlier candidate reports are preserved. They preserve source/fixture hashes, settings, model identities, evidence, answers, citations, usage and per-case metrics. The final original run took place at 15:06:40–15:07:29 IST; all final fixtures ran between 15:05:58 and 15:09:46 IST. The policy/status baseline preceded changes at 00:07:34–00:07:53 IST. No assessments are stored in the API responses or history.


## Local activation and preservation

The verified API process was restarted from PID 15645 to 31463 after validation. Its readiness check confirms the configured model is available, the worker is active, retrieval is loaded and all 22 existing semantic indexes are ready. The frontend returns HTTP 200. The worker, frontend and Ollama were not restarted.

The API's document and history responses match their pre-restart snapshots. Read-only SQLite row hashes also match the Phase 7 baseline: **28 documents, 41 chunks, 31 saved query runs, 22 vector jobs and 41 page-extraction records**. The activation check did not insert a live test answer. Evidence is in `data/local/phase7-restart.json` and `phase7-preservation.json`, and embedded in the compact final reports.

The app remains local at <http://127.0.0.1:5173>. No commit, push, model installation, dependency change, migration or reindex was performed. The combined strict quality and additional policy gates remain failing for the documented misses; activation does not change their thresholds or mark them green.
