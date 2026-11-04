# Phase 5 — answers bound to source excerpts

The Phase 4 baseline found a real quote attached to a different claim, unnecessary extra facts, and false abstentions despite relevant retrieval. This local step changes answer construction and labels while retaining the existing retrieval modes, model, OCR pipeline, document schema and saved history. No deployment, paid API, new model, package installation or graph work is included.

## Answer path

1. Retrieve the same configured passages using the selected retrieval mode and document scope.
2. Normalize whitespace and split each passage at sentence-ending punctuation followed by whitespace. Join fragments shorter than 12 characters forward; retain spans of 12–240 characters. Longer spans are omitted rather than truncated. Duplicate spans within one chunk are removed; identical text in different sources retains distinct provenance.
3. Give each excerpt a request-local ID and source group. The local model returns only `answerable` and up to two `source_ids`, constrained to the available IDs. It must decide whether the question's entity and requested fact are supported. It receives no expected fixture answers.
4. Reject unknown/duplicate IDs, inconsistent answerability and extra model-written fields. Build each claim and its single citation from the same selected span. Validate claim/quote equality plus the existing chunk-ID and normalized quote check.
5. Persist the response with `verification=extractive_source_binding`. The browser labels it **Source excerpts** and invites review of relevance and original sources. Older saved responses retain **Source-linked answer** and their original provenance notice.

No second model pass or semantic judge is used. The existing seed, temperature, 4K context, 768-token output allowance, timeout and one-call API semaphore remain. Model usage includes `model_called`, candidate count and selected request-local IDs. When no span is eligible the application abstains without calling Ollama and identifies the answer-length limitation. Source IDs are resolved in the request; persisted citations still use durable document/chunk IDs and page numbers.

The original public `claims`/`citations` response shape is retained. No schema migration or reindex is needed. The package/runtime version strings remain `0.3.0`; use the response's `verification` field to distinguish the new answer path. A running API must be restarted to load Python changes; Vite reloads the frontend change. Stop only the verified API process from this project, then start it from the project root:

```bash
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
uv run --frozen uvicorn omnirag.main:app --host 127.0.0.1 --port 8000
```

Keep the existing Ollama, worker and frontend processes. Full startup instructions remain in README. Do not start another owner of the live Qdrant directory.

## Validation and comparison

The original `evaluation/quality_fixture.json` and metric definitions remain unchanged. Compare the saved Phase 4 report with a new run:

```bash
HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
uv run --frozen python scripts/evaluate_quality.py --with-model --strict

HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
uv run --frozen python scripts/evaluate_quality.py \
  --fixture evaluation/answer_regression_fixture.json --with-model --strict
```

The additional fixture has three documents, four native pages, and eight questions with different entities and numbers, similar codes, negation, conditional returns, a two-part question, wrong-entity scope, and a missing birthday. It is authored development coverage, not a held-out benchmark. The command uses isolated temporary storage, preserves earlier reports, and records runtime/model/source identities.

Regression tests exercise the structured HTTP contract, invalid/duplicate IDs, injected freeform fields, inconsistent answerability, no-call behavior without eligible spans, identical text across different pages, OCR provenance, prevention of a valid-quote/wrong-claim mismatch, persistence and unchanged historical answers. Live browser checks additionally assert claim/quote equality, the new label, and original-page citations.

## Remaining limits

- Selection is still a model judgment. A copied excerpt can be irrelevant, contradictory, misleading out of context, or contain instructions from an untrusted document. Source binding is not a prompt-injection defense or a proof of relevance.
- Answers are quotations, not synthesized prose. Questions requiring calculations, a summary of many sentences, or more than two facts can be incomplete or refused.
- Sentence splitting is a punctuation heuristic, not a semantic parser. Abbreviations, sentence fragments at chunk boundaries, headings and qualifications across sentences may be mishandled. The original page and retrieved passages remain available for review.
- Spans over 240 characters are skipped. A source can contain the answer yet produce no eligible excerpt. This tradeoff retains complete eligible spans instead of clipping clauses to fit the quote limit, but it reduces coverage.
- OCR errors propagate into quotations. Native-header/scanned-body extraction remains the Phase 3 limitation. No ready document is reprocessed.
- The original paraphrased-delivery case still abstained under hybrid retrieval in the final comparison. The strict original fixture therefore remains failing. See [observed validation](PHASE5_VALIDATION.md) for measured improvements and failures.
