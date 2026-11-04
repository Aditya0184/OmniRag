# Phase 8 validation — 24 October 2026

The source-selection audit completed **164 actual local model calls**, covering all 41 fixed hybrid cases in retrieved and reversed passage order, twice each. **152/164 contracts passed**, with zero execution errors. Every case produced the same normalized cited answer or abstention across its four observations. The three known Phase 7 policy misses persisted in every observation.

This completes the audit, not the remaining answer-quality fixes. The strict quality gate correctly returned **exit 2**. Production behavior remains Phase 7; no new answer adapter was activated.

## Results

| Measure | Observed result |
|---|---:|
| Scheduled / scored observations | 164 / 164 |
| Contract passes | 152 / 164 |
| Answerable observations satisfying expected facts | 100 / 112 |
| Unsupported observations correctly refused | 52 / 52 |
| Execution / citation validation errors | 0 |
| Cases passing all four observations | 38 / 41 |
| Cases with changed cited-answer fingerprints | 0 / 41 |
| Cases whose selector input changed under reversal | 4 / 41 |
| Same-input answer changes | 0 |

Retrieved and reversed variants each pass **76/82** observations. The unchanged-input cases are expected: the Phase 7 adapter restores page order within each document. Four cases actually changed selector input: `delivery`, `named_delivery`, `different_entity_values`, and `condition`. Their cited-answer fingerprints still did not change.

The fingerprint ignores claim order, elapsed time and request-local excerpt IDs, while retaining answer status, text, document identity, page and quote. “Stable” therefore means equivalent cited answer under that definition, not byte-identical model output or a correct answer. No claim is made about arbitrary permutations, different model versions or longer documents.

## Remaining failures and next implementation target

| Case | Expected evidence | Observed result |
|---|---|---|
| Harbor named delivery paraphrase | 12 working days after payment clears | Abstained in all four observations |
| Meadow loan renewal permission | Only if no other reader has reserved the book | Abstained in all four observations |
| Harbor personalized-equipment return | The company does not accept these returns | Abstained in all four observations |

The fixed evidence already contains the required facts. This audit found no answer changes across the tested repetitions or passage reversal, so it does not support treating these three failures as occasional inference drift. It also does not establish the internal reason for refusal: the production adapter discards its model-generated assessment.

The next implementation candidate should target interpretation of named policy paraphrases, conditional permission and explicit prohibitions. Keep these expected facts, unsupported-status refusals, explicit-record support, original delivery/browser success and OCR regressions as acceptance conditions. Re-run this audit alongside fresh endpoint/browser evaluations before activating a candidate. Do not fix the scores by removing cases, weakening abstention checks or treating a valid quotation as proof of semantic support.

## Validation and preservation

- **103 backend tests passed**, zero skips, 31.20 seconds; one existing upstream Starlette/HTTPX deprecation warning.
- Ruff and Git whitespace checks passed. Ten new audit tests cover provenance validation, error accounting, stable-but-wrong results, selector-input comparison, complete report coverage, duplicate reports, question mismatch, model opt-in, overwrite protection and answer fingerprints.
- All five saved Phase 7 input report digests match. Recorded Phase 7 production and evaluator source hashes are unchanged. Only the new evaluation script, its tests and documentation were added or edited for this step.
- Read-only SQLite row hashes match the preservation baseline: **28 documents, 41 chunks, 31 query runs, 22 vector jobs and 41 page-extraction records**. No API query or document ingestion was performed against live application storage.
- No services were restarted, and no frontend code, dependency, model, migration or index changed. Browser/build/HTTP checks were not repeated because production and frontend sources are unchanged; Phase 7 results remain historical evidence for those checks.

The actual run used the existing `qwen3-vl:2b-instruct` model with digest `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e`, a 4K context, 768-token cap, temperature 0 and seed 42. It ran from **19:48:28 to 19:57:08 IST on 24 October 2026**. These wall-clock observations are not a latency benchmark.

## Evidence and limits

- [Complete audit report](evaluation/phase8-selection-mac-2026-10-24.json), including fixed evidence/expectations, per-observation answers, source/input hashes, model identity, summary and preservation checks.
- [Reproduction guide](PHASE8.md) and [evaluation script](../scripts/evaluate_selection.py).
- Local raw evidence: `data/local/phase8-selection-2026-10-24.json`, `phase8-selection.log`, `phase8-backend-final.log` and `phase8-preservation.json`.

The audit replays saved retrieval evidence; it does not measure new retrieval, ingestion or OCR. These authored cases were already used during development and are not held out. Lexical fact-span matching and citation-page precision do not prove semantic entailment, source truth or complete context. The observed stability is bounded to this model, these inputs and these repetitions.
