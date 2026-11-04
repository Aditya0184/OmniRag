# Phase 11 — answer subject and requested-fact repair

Phase 10 exposed answers drawn from another company's policy or a different rental record, plus a response that selected a duration instead of the requested return condition. Phase 11 narrows the model's source context to the named subject and clarifies requested-attribute selection. The private single-owner Mac application, owner authentication, retrieval choices and source-linked answers remain the delivered scope. See [observed validation](PHASE11_VALIDATION.md).

## Behavior

Before constructing model excerpts, `scoped_evidence` extracts name-like phrases and alphanumeric record codes from the question. It retains a retrieved document only when that document's retrieved text contains all those constraints. Word boundaries distinguish nearby identifiers such as PX-51 and PX-510. A shared multiword-name suffix also recognizes some lowercase company references. Ordinary sentence-initial capitalization alone is not treated as a name. The filter preserves source order and provenance and does not change the public retrieval results.

If retrieval returns passages but none survive this guard, the API returns insufficient evidence with a named-subject explanation and makes no model call. Usage records `subject_scope_withheld`, `scope_excluded_chunks` and policy version `subject_scoped_policy_v3`; retrieved passages remain inspectable. Questions beginning with what, which or whose receive the original selection instructions plus a clarification to select the requested attribute and avoid adding individual examples to general-policy answers. Other questions retain the original prompt. The existing guarded policy retry, two-attempt maximum, shared token/time budget and exact quote binding remain in effect.

This is a conservative English heuristic, not entity resolution or proof of semantic support. Aliases, unusual capitalization, non-English names, comparisons across separate documents and several entities within one document can defeat or overconstrain it. Citation provenance still does not prove that a quoted statement answers a question. Review the original source.

## Evaluation boundary

`evaluation/acceptance_v1.json` became a development regression fixture after its Phase 10 failures informed this repair. Its original expectations and failed report remain unchanged. `evaluation/acceptance_v2.json` was frozen before candidate edits and first inference. Its [freeze record](evaluation/phase11-acceptance-freeze.json) and [first run](evaluation/phase11-acceptance-v2-mac-2026-10-29.json) are archived. These are same-assistant authored fixtures, not an external benchmark or independent human review. The new acceptance results were not used to tune the selection prompts.

A candidate had to retain previous hybrid regressions and the saved browser example, repair the old acceptance failures, pass the new hybrid acceptance set, and pass backend/API/browser checks. Genuine BM25 lexical retrieval misses remain explicit failures in the strict evaluator; no semantic fallback was added to keyword mode. Live activation also requires preservation of documents, original PDFs and saved history.

## Development evidence

- Candidate 1 added model-produced entity fields: 7/9 targeted cases; rejected for renewal and personalized-return failures.
- Candidate 2 retained the original selector with literal subject filtering: 8/9 targeted cases; the accessory requirement remained wrong.
- Candidate 3 used a shorter prompt: 9/9 targeted cases, but source-coverage inspection found false exclusions from question openers and a weekday.
- Candidate 4 corrected those exclusions: 58/66 full replay cases; rejected for unsupported answers and malformed selections.
- Candidate 5 used requested-attribute clarification: 13/14 targeted cases; a general delivery answer included an unnecessary individual record.
- Candidate 6 prohibited those added examples: 14/14 targeted but 65/66 full replay cases; rejected for abstaining on the saved browser delivery example.
- Candidate 7 applies the attribute clarification only to what/which/whose questions: 66/66 full replay cases; selected for fresh evaluation.

The first full backend run exposed sentence-initial words incorrectly treated as names. A grammar correction fixed that issue without changing the prompts or any of the 82 evaluated inputs whose reports record the earlier generation hash; the [equivalence record](evaluation/phase11-grammar-equivalence.json) preserves that distinction. The final source hash is recorded with deployment. Raw rejected-candidate reports and source snapshots remain under ignored local `data/local/phase11-*` and `tmp/phase11/`. Their model assessments are test diagnostics, not production response/history fields.

For launch, owner password changes, recovery and shutdown, use the existing [Mac operation guide](PHASE10.md). There is no public deployment, multi-user isolation, reboot login agent or crash supervisor.
