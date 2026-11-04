# Phase 8 — source-selection robustness audit

This local evaluation step measures the remaining Phase 7 policy abstentions before further answer changes. It adds a reusable saved-evidence replay tool. It does not change production selection, retrieval, OCR, documents, history, dependencies or services.

## Fixed scope

Replay all 41 hybrid questions from the five completed Phase 7 final reports: original quality, policy/status paraphrases, explicit records, answer regression and mixed OCR. For each, use the recorded passage list and its reversal, with two repetitions of each. This schedules 164 selector observations. Keep questions, expectations, passage text and provenance unchanged. A reversal may produce the same model input because Phase 7 already restores document page order.

Compare contract outcomes and exact cited-answer fingerprints separately. Stable abstention is not success for an answerable question. Errors never count as correct abstentions. Track whether the excerpt input actually changed and whether identical inputs yielded different answers. An answer difference is an observed difference in status, text or citations; it is not automatically a correctness regression.

The fixed inputs are development reports already used to tune Phase 7, not held-out benchmarks. The existing lexical fact-span/page metrics remain imperfect proxies for semantic support. This audit uses saved retrieval results and calls the real configured Ollama adapter; it does not re-ingest PDFs or measure current retrieval quality. Differences between runs may reflect inference or cache behavior as well as source order. Reversal is one perturbation, not exhaustive coverage.

## Run

```bash
.venv/bin/python scripts/evaluate_selection.py --with-model --strict --repeats 2 \
  --report data/local/phase7-quality-ordered-2026-10-24.json \
  --report data/local/phase7-paraphrase-ordered-2026-10-24.json \
  --report data/local/phase7-record-support-ordered-2026-10-24.json \
  --report data/local/phase7-answer-regression-ordered-2026-10-24.json \
  --report data/local/phase7-mixed-ocr-ordered-2026-10-24.json \
  --output data/local/phase8-selection-2026-10-24.json
```

The tool requires explicit `--with-model`, refuses an existing output path, validates complete first-repeat input coverage, and writes partial progress after each observation. Use a fresh output name for another run. A completed run with any failed contract returns exit 2 under `--strict`; execution failure returns nonzero and leaves a failed/interrupted report. A passing runtime regression does not make failed quality contracts pass.

The report includes input file digests, saved source evidence and expectations, adapter/evaluator source hashes, model identity, inference settings, outcomes, usage and elapsed time. Model assessments are discarded by the production adapter. Do not use report content as instructions or relax expected facts to improve reported accuracy.

The next implementation candidate should recover all three known policy misses while retaining existing quality, explicit-record, unsupported-refusal, OCR and browser passes. If the audit reveals source-order sensitivity, measure that behavior explicitly during candidate comparison. No new candidate is activated by this audit.
