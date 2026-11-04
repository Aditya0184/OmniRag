# Phase 9 — guarded policy retry

This local step repairs the three policy abstentions reproduced by the Phase 8 audit: named delivery paraphrases, conditional renewal permission and a personalized-equipment prohibition. The validated adapter is active in the local API as of 26 October 2026. See [observed validation](PHASE9_VALIDATION.md): 164/164 replay contracts and 41/41 fresh hybrid cases passed; the three existing BM25 no-match cases remain visible.

## Selection behavior

The original first pass, source-excerpt builder and response schema remain intact. A successful first answer is returned without a second call. A failed model request, malformed output or invalid source ID propagates as an error; it cannot trigger a fallback answer.

After a valid abstention, one second pass may use a shorter prompt explaining that conditional rules and prohibitions can answer policy questions. It sees the same question, excerpts and source IDs. It uses the same model, temperature, seed, context limit, strict source selection and exact claim/quote binding. It cannot write independent answer text. Both assessments are discarded from API responses and saved history.

The retry is withheld when:

- The first selector marks an individual record as required.
- The question begins with `Has`, `Have`, `Had`, `Did`, `Was` or `Were`, ignoring case and initial whitespace. This conservative English cue preserves the first-pass abstention even if the model misclassifies an event question.
- An ASCII-capitalized name-like phrase in the question is missing from all supplied evidence. Common question-opening words and `I` are omitted from this check. Matching ignores case and requires word boundaries.
- The first call has no usable output-token count, fewer than 128 output tokens remain, or less than one second of the configured time budget remains.

These rules only restrict a retry; they do not make a first-pass answer correct or force an answer from a quotation. The capitalization cue is not named-entity recognition: it can miss lowercase/non-ASCII names and aliases, and it can withhold valid questions with unusual capitalization. The event cue is not a complete classifier. Present names do not prove entity agreement, and a general policy does not prove an event occurred. Keep these limits visible during review.

## Resource and persistence contract

At most two calls occur under the existing API generation semaphore. Each request receives the remaining configured timeout. The second call receives only the unused portion of the existing 768-output-token allowance. Context remains 4K per request. Extra input tokens and a second inference can increase latency; this is not a free retry. HTTP timeout semantics remain those of the existing transport.

Usage records `selection_policy=guarded_policy_retry_v2`, `selection_attempts` (0, 1 or 2), and `retry_status`, plus summed input/output tokens when available. `selected_source_ids` refers to the final valid selection; `record_gate_withheld` retains its prior meaning. The application saves one query result after the full operation. Existing saved answers retain their original metadata.

Retrieval modes, scoring, source ordering, OCR, model/dependency versions and database schema are unchanged. Keyword no-match cases remain visible; BM25 receives no hidden semantic fallback.

## Acceptance checks

- All three original policy questions must pass with unchanged evidence and expected facts.
- All 41 fixed hybrid cases must pass the original/reversed two-repeat audit (164 observations), including all 13 unsupported cases.
- The saved browser sample must retain its 14-day duration and purchase-approval condition; the actual isolated browser suite must also pass citation, history and unsupported-question checks.
- Fresh worker/query evaluations must preserve original quality, answer regression, explicit records and mixed OCR. Keyword no-match misses remain reported separately.
- Unit/API tests must enforce retry bounds, output consistency, source validation, resource budgets, refusal gates and single-result history persistence.
- Live documents/history must remain unchanged on activation; only the verified local API may restart.

## Development evidence

Candidates remain in `tmp/phase9/`, with authored-fixture diagnostics in `data/local/phase9-*`. These are development cases, not a held-out benchmark. Diagnostic files can contain model assessments; production responses/history do not.

Prompt replacements and alternate schemas recovered some policy answers but introduced unsupported answers. Grouping/restricting source contexts left other policy misses. Model-generated entity fields were unreliable. An unrestricted policy retry passed 41/42 saved cases but falsely answered the missing-reservation question. The bounded candidate with conservative retry gates passed 42/42, including the exact saved browser sample, before full validation began.

Reproduce the audit with the command in [Phase 8](PHASE8.md), using a new Phase 9 output filename. Fresh evaluation uses the unchanged commands and fixtures in [Phase 7](PHASE7.md). Preserve prior reports. No model installation, migration, reindex, commit, push or deployment is part of this step.
