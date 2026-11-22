# Local model assessment — is the 2B model the bottleneck?

## Evidence that it is the main quality bottleneck

All remaining fixture failures after Phase 13 are generation-side, not retrieval-side:

| Observation | Evidence |
|---|---|
| Retrieval is not the limiter | Mean retrieval page recall is 1.0 across the Phase 12/13 fixture reports; every failed answer had its supporting passage already in context. |
| Conflict surfacing | "How much does the Harvest Menu cost?" — the passages state 40 and 45 credits (acceptance v4) or 520 and 480 (dev); the model reliably reports one value and usually stays silent about the other, despite an explicit instruction to give one claim per value. |
| Quote discipline | `personalized_return`: the model rewrites "The company does not accept…" to "Harbor Tools does not accept…" in the *quote* even with a worked counter-example in the prompt; the claim is then (correctly) dropped and only the partial answer survives. |
| Run-to-run variance | Borderline paraphrases ("How long until my purchased goods arrive?") answer in fixture runs but withheld in two single browser runs; the bounded retry recovers most but not all cases. |
| Prompt sensitivity | Behavior flips between runs on prompt rewording (attribute rule placement changed two cases in opposite directions during Phase 12 tuning) — a small model's decision boundary sits exactly at these cases. |

## What a replacement must demonstrate (comparison protocol, not yet run)

Downloading a larger model needs the owner's approval, so no comparison has been
executed. When approved, run the same frozen suites per model — no code changes, only
`OMNIRAG_OLLAMA_MODEL`:

1. Candidates that plausibly fit an 8 GB Mac alongside macOS and the app (4-bit
   quantized, single model loaded): `qwen3:4b-instruct` (~2.5 GB), `llama3.2:3b`
   (~2 GB), `phi4-mini:3.8b`. 7–8B models are borderline; measure before claiming.
2. Runs: `scripts/evaluate_quality.py --fixture evaluation/acceptance_v4.json
   --with-model --modes hybrid_rerank` and the same for `evaluation/broad_dev.json`,
   with `scripts/record_model.py` before/after.
3. Gates to adopt a model: strictly better contract rate on the frozen set, no new
   unnecessary refusals, median answer latency ≤ 15 s, and observed peak memory
   (`ps` RSS of the Ollama process during inference) leaving ≥ 1.5 GB free on the
   8 GB machine.
4. Rollback: the previous model tag stays in `.env` history and
   `data/local/auth/../models` metadata; switching back is a one-line change.

## What prompt changes cannot fix

Structural limits remain regardless of model size: extractive provenance proves
where words came from, not that they answer the question; tables remain plain text;
images are never interpreted; and no locally verified mechanism distinguishes a
true paraphrase from a fabricated one — only the lexical support floor and the
bounded verification passes exist today.
