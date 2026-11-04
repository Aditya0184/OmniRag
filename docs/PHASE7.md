# Phase 7 — policy paraphrases and abstention

This local step addresses a source-selection miss: hybrid retrieval found the correct delivery policy for a question phrased differently, but answer selection abstained. It also evaluates whether a general rule is being mistaken for a record of an individual event. Retrieval modes, documents, OCR and the source-excerpt answer contract remain separate from this change.

## Answer selection

The one local model call now returns a bounded `evidence_assessment` of 1–240 characters, followed by `requires_individual_record`, `individual_record_present`, `answerable` and at most two source IDs. The assessment asks the model to identify the requested fact and source support before deciding. Instructions distinguish ordinary policy questions phrased with “I” or “my” from an individual's actual status, completed event or exact date. Two unrelated illustrative examples explain why a prerequisite does not establish that it happened.

The server still rejects unknown/duplicate source IDs, malformed fields, extra output and inconsistent answerability. It additionally withholds a selection when the model says an individual record is required but absent. Otherwise it constructs answer text and its single citation from each selected excerpt, checks equality and original chunk provenance, and retains the same public response shape. It never uses the model-written assessment as answer text or evidence.

The assessment is discarded after validation; it is not exposed in API answers, stored in history, or rendered in the browser. Usage records `selection_policy=policy_record_assessment_v1` and `record_gate_withheld`; withheld candidates do not appear in `selected_source_ids`. Existing saved answers retain their original fields. The public verification marker remains `extractive_source_binding` because source binding is unchanged.

The selector builds its sentence candidates from each document’s retrieved passages in ascending page order; documents retain their first-appearance retrieval order. Combined spans are appended after the individual candidates and retain their source-group IDs. Retrieval scores and the public evidence list are unchanged. Passages on the same page retain retrieval order when no ordinal is supplied. This restores reading order for answer selection but does not retrieve any missing page.

The excerpt builder also keeps a bounded pair of linked sentences together. When a sentence begins with `The`, `This`, `That`, `These` or `Those` followed by a two-word ASCII phrase found in the preceding sentence, their exact contiguous span can replace the separate excerpts. Both sentences must belong to the same chunk and fit the existing 240-character quote limit. For example, a rule describing a review period and a following sentence beginning “This review period…” can remain one quote. This is a literal English heuristic, not grammatical or semantic parsing. It can include extra context and misses other forms of reference. It never joins across a skipped long sentence, chunk or page, or truncates text to make it fit.

No second model pass, query rewriting, semantic score cutoff or external judge is introduced. The same local model, 4K context, 768-token output cap, temperature 0, seed 42, timeout and request semaphore remain. The extra structured fields require more generated tokens and can increase latency. This is a small-model selection aid, not a proof of entailment: classification and assessment can be wrong, a fabricated assessment can still accompany a selection, and a retrieved record may be stale or misleading. The original source remains the authority for review.

## Evaluation scope

Keep the original quality, answer regression and mixed OCR fixtures unchanged. The additional `evaluation/paraphrase_fixture.json` contains six answerable questions and six unsupported questions. It was fixed before the prompt experiments and first run against the Phase 6 implementation.

The fixture includes unnamed and named policy paraphrases, return requirements, a prohibition, a loan period and renewal condition. Unsupported cases ask about a particular order's arrival/payment, a personal loan's exact due date, a reservation, a missing delivery cost and a different company's policy outside the selected document scope. Source conditions must remain in the selected quotations.

The separate `evaluation/record_support_fixture.json` was fixed before testing the record gate. It supplies explicit historical payment, delivery, loan-date and reservation records, checks similar but missing order/loan IDs, and retains a general-policy question. This guards against accepting a change that simply refuses every personal question.

The same lexical fact-span and citation-page metrics apply. They are development proxies, not semantic entailment, and can miss extra irrelevant text from an otherwise correct page. Preserve per-case outputs for review. These authored cases are not a held-out benchmark.

## Reproduce

```bash
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 uv run --frozen python scripts/evaluate_quality.py --with-model --strict
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 uv run --frozen python scripts/evaluate_quality.py \
  --fixture evaluation/paraphrase_fixture.json --with-model --strict
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 uv run --frozen python scripts/evaluate_quality.py \
  --fixture evaluation/record_support_fixture.json --with-model --strict
```

These commands default to keyword search and hybrid with reranking. Keyword search remains literal BM25 over the existing FTS tokenizer. Questions without matching words can still fail in that mode; this step does not add a hidden semantic fallback or change the quality gate. To evaluate only the semantic mode, explicitly supply `--modes hybrid_rerank`.

The evaluator runs the production worker/query path with temporary document and vector storage and records source hashes, model identity, expected facts and raw answers. Earlier reports are not overwritten. Existing ready documents and saved answers are not modified by evaluation.

The API process must be restarted to load a selected adapter change. Verify the PID command and cwd before stopping only that API, then start it using the README command; keep the existing worker, frontend and Ollama. No migration or reindex is needed. The runtime/package version remains 0.3.0; the selection-policy usage marker distinguishes new answers.
