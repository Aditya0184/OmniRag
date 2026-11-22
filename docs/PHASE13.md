# Phase 13 — closing the known answer failures and finishing the workflow

Phase 13 follows the Phase 12 validation report and the owner's completion checklist.
Its scope: the four documented Phase 12 failures, the remaining UX gaps (a PDF viewer
that actually renders, follow-up phrasings, context reset on document switching), a
justified improvement to the evaluation rules, and a fresh frozen acceptance set. See
[validation results](PHASE13_VALIDATION.md).

## The four carried-over failures, and what was done

1. **"What desserts are included in the Garden Menu?" answered with unrelated menu
   facts** (`meridian_unsupported`). Diagnosis: generation — the 2B model answered a
   different question with true facts. Fix: the request now carries
   `asked_attribute` (the specific noun a *what/which* question asks about when it is
   absent from the passages — "desserts"), with an instruction to abstain when the
   passages never mention it; and validation independently withholds any answer that
   never addresses the asked attribute (usage `attribute_absent`, with a specific
   user-facing reason). Requirement questions ("what proof do I need…") are exempt
   from the withholding rule because their answers legitimately paraphrase
   ("an original receipt is required").
2. **"What proof do I need to bring something back?" refused although the passages
   state the receipt requirement** (`return_condition`). Diagnosis: generation — the
   model over-refused and the abstention-retry never fired because the question shares
   no words with the answer ("proof" vs "original receipt"). Fix: requirement
   questions (need/required/must/allowed/proof/condition/…) now always get one
   bounded reconsideration, and the reconsideration prompt explicitly asks for a
   condition or exception that answers the question in other words.
3. **A valid answer discarded because the model rewrote a quote**
   (`personalized_return` — "The company does not accept…" rewritten to "Harbor Tools
   does not accept…"). Diagnosis: generation — the 2B model edits quotes. Fix: an
   explicit prompt rule with a worked example; and claim-level quote handling from
   Phase 12 already lets the surviving claim answer partially. A new record-code rule
   also drops any claim that attaches an asked identifier (e.g. `L-28`) to a quote
   which never mentions it — that closed a fabricated-date path the extra runs
   exposed (`due_date_record`).
4. **A correct paraphrase rejected by overly literal evaluation** (`payment_record` —
   "Payment **for Ridge Parts order R-517** cleared on 18 September 2025" vs the
   expected consecutive phrase). Diagnosis: evaluation, not the application. Fix:
   expected-fact matching now requires all tokens **in order, gaps allowed**, with
   positive and negative unit tests (changed value ✗, reordered ✗, missing token ✗,
   14≠118 ✓). Consecutive matching is unchanged for quotes and forbidden phrases.

## Other behavior changes

- **Topic-only keyword queries** ("cancellation policy", "menus", "skills"): keyword
  search now also tries the other-side plural form of each token ("cancellation" →
  "cancellations"). Still exact token matching; no synonyms.
- **Follow-ups**: "Explain that.", "What else…?", "Give more detail…" work through
  the conversation expansion (the action-request guard no longer misfires on
  "Give…", while "Transfer…" and "Announce…" are still declined).
- **Context reset**: switching the selected document clears the conversation thread
  in the workspace, and the backend additionally drops conversation turns whose
  recorded scope does not include the current document.
- **Conflicting values**: the prompt instructs one claim per value when passages
  disagree. Measured honestly below — the 2B model often surfaces only one value.
- **Page preview that actually renders**: the source panel now shows a PNG rendered
  locally with PDFium (`GET /documents/{id}/pages/{n}/preview`) instead of an
  embedded PDF iframe, which headless and embedded viewers render unreliably. The
  browser suite asserts `naturalWidth > 100` — real pixels, not just a URL. "Open
  PDF" and "Download" links remain for the full document.

## Evaluation changes and their justification

- Expected-fact matching: subsequence rule as above (evaluated change, not a
  loosening to pass a known case: the payment_record answer had been substantively
  correct since the rule change in Phase 12's final code, and the tightening
  direction — order and completeness required — is preserved).
- The whole-answer page-precision *requirement* was removed in Phase 12's final
  scoring because `facts_on_reference_pages` already forces every expected fact into
  a claim citing a reference page; precision stays a reported metric.
- Phase 12's acceptance v3 is now development evidence (its failures informed these
  repairs). Phase 13's `evaluation/acceptance_v4.json` — 8 new documents, 26 new
  queries — was frozen before any Phase 13 tuning run
  ([freeze record](../docs/evaluation/phase13-acceptance-freeze.json)).
