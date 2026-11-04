# Phase 12 — grounded written answers, document overviews and clearer statuses

Phase 12 repairs the product failure where ordinary questions ("What is in this PDF?",
"Tell me about this document.", "Summarize this.", "Which internships are listed?",
"How does it work?") returned *insufficient evidence* or unrelated excerpts. The cause
was structural: since Phase 5 the "answer" was always one or two verbatim excerpts
(12–240 characters each) selected by the model, and whole-document, list, summary and
explanation questions have no single spanning excerpt. Phase 12 keeps the validated
provenance machinery but lets the model **write** a short answer whose every claim
cites passages with server-verified exact quotes. It also adds document overviews and
summaries, follow-up conversation memory, a clarification flow, and honest status
messages. See [validation results and limitations](PHASE12_VALIDATION.md).

## Grounded answers (`OMNIRAG_ANSWER_MODE=grounded`, the default)

The local model receives whole retrieved chunks (no more 240-character excerpt
limiting) plus the question, and returns structured JSON: `answerable`,
`missing_information`, and up to three claims, each citing 1–2 passages with an exact
quote copied from that passage. The server then enforces, without the model:

- **Quote provenance** — each cited quote must occur verbatim (whitespace-normalized)
  in the cited chunk, and the chunk must be one of the retrieved passages. Invalid
  quotes invalidate the whole answer, as before.
- **Lexical claim support** — a written claim must share enough content words with the
  text it cites (≥ 50%, with bounded plural/possessive folding). Unsupported claims are
  dropped individually and the count is disclosed; if all claims are dropped the
  answer is withheld.
- **Number conservation** — every number in a claim (digits or simple English number
  words, including compounds like "twenty-one") must also appear in the cited text.
  Claims cannot compute or alter values ("14 days" cannot become "30 days").
- **Record-code guard** — if the question names a code such as `QS-0002` and a claim
  discusses a different code, the claim is dropped; if no kept claim concerns the asked
  code, the answer is withheld instead of substituting a similar record.
- **Subject scoping stays soft.** The literal name/code filter from Phase 11 still
  focuses passages before the call, but when it would exclude everything the app now
  continues with all retrieved passages and reports `scope_relaxed` instead of
  refusing without the model.
- **One bounded reconsideration** — an abstention with no explanation, or a malformed
  first response, gets one retry with the same passages inside the same time/token
  budget. A failed retry falls back to the first valid response rather than erroring.

Each claim is labeled **Quoted** (the claim text is the cited quote) or **Explanation**
(model wording). This distinction is presentational support, not proof of correctness.

The prompt instructs the model to answer list questions exhaustively, to describe the
document for whole-document questions, to distinguish general policies from individual
records (a policy never proves a personal event), to match named entities, and to
refuse instructions embedded in passages or in the question. The Phase 5–11
excerpt-selection behavior remains available as `OMNIRAG_ANSWER_MODE=extractive` and is
still covered by its original tests; it is no longer the default.

## Question intents, coverage and clarification

The query endpoint classifies the question: `summarize`, `key_points`, `overview`
("what is in this PDF", "tell me about this document"), `list` ("which X are listed" —
retrieval widens to up to 8 passages), and `factual`.

- **Overview questions with a selected document** are answered from a *coverage
  sample* of the document in reading order (all chunks up to ~9,000 characters; beyond
  that, the first page plus evenly spaced pages). The result reports
  `coverage.complete` and, when partial, the reason discloses exactly how many of how
  many indexed pages were read.
- **"Summarize" / key points** use the document overview (below) when cached, or
  generate it once and cache it.
- **"This document" resolution** — an overview-family question with no explicit scope
  uses the single ready document when there is exactly one; with several ready
  documents it returns `clarification_needed` with the candidate list, and the UI
  offers one-click selection. Factual questions without scope keep the existing
  search-everything behavior.
- **Follow-ups** — the workspace sends the last exchange; retrieval expands the query
  with the user's own previous words (never synonyms), and the prompt resolves
  references like "it" or "they". The scope of the previous turn is reused for
  follow-up questions that don't name a document.

## Document overviews and summaries

Schema 4 adds a `document_summaries` table (`overview` and `detailed` per document,
with status, content, coverage, model and error). A **migration backup** is required
before activating; see [backup and restore](#backup-and-restore).

- **Overview** (one structured call over the coverage sample): document type, a short
  summary, topic chips, up to six key points — each checked for lexical support in the
  page(s) it cites and dropped when unsupported — and three suggested questions. The
  worker generates an overview automatically right after a document becomes ready;
  older documents get one on demand from the workspace. Overview generation failure is
  recorded and visible; it never fails the document.
- **Detailed summary** ("Summarize document" action): the overview plus a bounded
  section-by-section map pass (up to 8 sections × 4 supported bullets each). Long
  documents report `sections_processed` of `sections_total` with a partial-coverage
  note.
- Workspace actions per ready document: **Summarize document**, **Show key points**,
  **Ask a question**, plus suggested questions that fill the ask box.

## Statuses and explanations

Query results now distinguish: `answered`; `no_relevant_passage` (retrieval found
nothing — keyword mode suggests Hybrid + reranking); `unsupported_question` (passages
were retrieved but the model found no support — the reason states what is missing and
the suggestion names next steps); `clarification_needed` (choose a document). Errors
keep distinct codes: `MODEL_UNAVAILABLE` ("Start Ollama…"), `MODEL_NOT_FOUND` ("Pull
the configured model…"), `MODEL_BUSY`, `DOCUMENT_NOT_READY` (with the document name and
its actual state), `RETRIEVAL_*`. The UI maps each to a specific message and shows the
retrieval mode used, the answer's scope, OCR warnings and partial-coverage notes.
Legacy history entries with `insufficient_evidence` still render.

## Backup and restore

```bash
.venv/bin/python scripts/backup_workspace.py backup --label phase12
.venv/bin/python scripts/backup_workspace.py list
.venv/bin/python scripts/backup_workspace.py restore <backup-directory>
```

Backup copies the SQLite database via the consistent sqlite3 backup API plus
`uploads/`, `qdrant/`, `auth/` and `models/` into `data/local/backups/<label>-<stamp>/`.
It refuses to run while the API is running. Restore refuses while the API is running,
keeps a safety copy of the current state, and then replaces the database and
directories. Stop the services first (`scripts/mac_app.py stop`), restore, then start.
Everything remains on this Mac; nothing is uploaded.

## Extraction, tables and images

Extraction is unchanged from Phase 6 (native text, bounded Tesseract OCR for sparse
and image-only pages, mixed-content heuristic). Lists and headings inside chunks
extract as plain text; multi-column layouts and complex tables can lose their reading
order — a known limitation, documented in validation. Charts, figures and images are
not interpreted anywhere in the pipeline, and the UI does not claim otherwise.

## Scope and remaining limits

Single owner, one Mac, loopback only. One model call at a time; overview generation in
the worker can briefly contend with a query. Claim support is a lexical proxy, not
entailment; quotes prove provenance, not truth. Retrieval scores are not confidence.
See [validation](PHASE12_VALIDATION.md) for measured results and open limitations.
