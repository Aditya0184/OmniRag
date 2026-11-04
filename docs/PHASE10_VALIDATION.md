# Phase 10 validation — completed 28 October 2026

Owner authentication and the built Mac app are active at **http://127.0.0.1:8000**. Functional, browser and live preservation checks passed. The new quality evaluation completed successfully as an execution, but **failed its quality gate**. This report keeps those outcomes separate.

## Fresh frozen quality evaluation

The 26 October run evaluated five new authored documents (six pages) and 24 questions in both BM25 and hybrid-rerank modes. The fixture was frozen before the first inference; its SHA-256 is `d8ac4cc935996668ea65ba53914e643878f7934a29212dacaa8b345680424683`. The archive includes the freeze record and original generation/source hashes. Phase 9 generation is unchanged after the evaluation.

| Measure | BM25 | Hybrid + reranking |
|---|---:|---:|
| Contracts passed | 17/24 | 19/24 |
| Answerable expected facts matched | 11/13 | 12/13 |
| Unsupported questions correctly refused | 8/11 | 8/11 |
| Execution errors | 0 | 0 |
| Mean citation-page precision when answered | 0.667 | 0.719 |
| Mean relevant-page retrieval recall | 0.923 | 1.000 |

All native, scanned and header-over-scan transcription groups had zero CER/WER on these synthetic pages. PDF previews were inspected for legibility and clipping before inference. This does not establish real-world OCR accuracy.

The five hybrid failures were:

- `hire_duration`: included both the requested company's duration and another company's duration. The expected fact was present, but the extra citation made the complete contract fail.
- `included_battery`: answered with hire duration and deposit instead of the required battery-return rule, despite retrieval containing the relevant page.
- `absent_refund`: answered a question about rental R-999 with the refund date for R-482.
- `wrong_scope`: supplied Alder's deposit for a question about Birch despite the selected scope excluding Birch.
- `lowercase_entity`: supplied Alder's hire period for a lowercase question about Birch.

BM25 also failed `hire_paraphrase` through no matching evidence and `deposit` through an additional other-company deposit. Both modes therefore returned strict quality failure (exit 2). Citation provenance remained valid: the wrong answers still copied actual source text. These cases demonstrate why quote binding and retrieval recall are insufficient to establish semantic correctness.

These are fresh authored cases, not an external benchmark or independent human evaluation. The same assistant authored the evaluation after implementing earlier phases. The run was not used to change generation or fixture expectations. The UI now specifically warns that excerpts can refer to the wrong person, record or policy. Answer quality remains an open limitation; no claim of complete reliability or universal robustness is made.

## Authentication and application validation

- **136 backend tests passed** (including 16 authentication cases); one existing upstream Starlette/HTTPX deprecation warning. After final authentication response-header and connection-lifetime changes, the focused **16 authentication cases passed again**.
- Tests cover anonymous denial of original files/documents/history/readiness/docs, fail-closed unconfigured ownership, password verification, origin/custom-header checks, CSRF, persistent login throttling, cookie attributes, hashed session storage, expiry, rotation, revocation, restart persistence, private file permissions and built frontend serving.
- **10 existing browser regressions passed** with actual local Ollama in 2.0 minutes, using temporary documents and isolated API/worker/frontend services. They cover uploads, retrieval, answers, source links, history, OCR and mobile layout. This regression stack used development authentication defaults; it does not substitute for the separate owner-login checks.
- An isolated owner-account browser check verified login, the authenticated workspace, the password-change form/cancel and logout. Password-change submission was tested through the backend suite, not submitted through browser automation. The deployed sign-in screen was subsequently inspected at port 8000.
- Frontend production build, Ruff and whitespace checks passed. No dependency/model installation or source-generation tuning was performed.

## Live Mac activation and preservation

The launcher replaced the verified API with PID **50547** and retained the verified worker **4119** and Ollama **1607**. The old Vite development frontend **1610** was subsequently verified and stopped; the compiled frontend is now served by the API. Repeating `start` reused the running services. The API listener was observed bound to **127.0.0.1:8000**, with no public binding.

The final live check on 28 October verified:

- Anonymous reads of documents, history, readiness, API docs and schema return 401. An anonymous query is denied without saving a live query.
- Owner login succeeds using the private local handoff file without printing/logging its contents. Authenticated documents/history/readiness and an original-PDF download succeed.
- Logout without CSRF is rejected; valid logout revokes access. Retrieval is loaded, the model is available, and the worker is active.
- All **28 original PDF hashes** match stored document hashes. All five content-table row hashes match the Phase 9 baseline: **28 documents, 41 chunks, 31 query runs, 22 vector jobs and 41 page-extraction rows**.

Authentication uses a separate private database; the document schema remains version 3. Login/session checks mutate only authentication storage. No live test documents or generated answers were added. Existing `.env`, Git history and uncommitted work were preserved. No cloud deployment, commit or push occurred. The final verification was delayed by an automatic approval-review usage limit, then completed successfully through the normal approval mechanism.

## Evidence and remaining limits

- [Complete frozen acceptance report](evaluation/phase10-acceptance-mac-2026-10-26.json), including original evidence, claims, expected facts and failure metrics.
- [Live deployment and preservation report](evaluation/phase10-deployment-mac-2026-10-28.json).
- Local logs: `data/local/phase10-backend.log`, `phase10-auth-final.log`, `phase10-browser-final.log`, `phase10-build-final.log`, `phase10-browser-ui.json` and `phase10-deployment.json`.
- [Mac startup, password recovery and security boundary](PHASE10.md).

The delivered scope is a single-owner Mac installation plus fresh evaluation. Public hosting, independently audited security, multi-user document isolation and independently reviewed general answer accuracy are not delivered. The launcher must be run after reboot; no automatic login agent or crash supervisor was installed. The new evaluation identifies concrete answer-quality work rather than certifying the app as fully accurate.
