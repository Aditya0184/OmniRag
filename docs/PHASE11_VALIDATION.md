# Phase 11 validation — completed 1 November 2026

The selected repair passed the new frozen acceptance fixture and all prior hybrid regressions. The results below describe authored synthetic PDFs and questions; they do not certify general answer accuracy or independently reviewed security. Deployment verification is recorded separately below.

## Fresh evaluation results

Seven isolated runs on 29 October used the actual worker, query endpoint, local retrieval models and installed `qwen3-vl:2b-instruct` through Ollama. Each fixture was evaluated in BM25 and hybrid-rerank modes. No live documents or saved queries were used as test fixtures or modified by these runs.

| Fixture | BM25 passed | Hybrid + reranking passed |
|---|---:|---:|
| New frozen acceptance v2 | 24/24 | 24/24 |
| Former acceptance v1, now regression | 23/24 | 24/24 |
| Quality | 9/10 | 10/10 |
| Paraphrase | 10/12 | 12/12 |
| Record support | 7/7 | 7/7 |
| Answer regression | 8/8 | 8/8 |
| Mixed OCR | 4/4 | 4/4 |
| Total | 85/89 | 89/89 |

All runs completed with zero execution errors. Four BM25 questions returned insufficient evidence with relevant-page retrieval recall 0: `delivery_paraphrase`, `unnamed_delivery`, `return_condition` and `hire_paraphrase`. The quality, paraphrase and former acceptance runs therefore retain strict exit code 2. The Phase 11 activation gate permits those explicitly identified lexical retrieval misses while requiring every hybrid case and every unsupported-question refusal to pass. Keyword mode has no hidden semantic fallback.

The new acceptance fixture has six documents, seven pages and 24 questions: 13 answerable and 11 unsupported. In each retrieval mode, all 13 expected-answer contracts passed, all 11 unsupported questions were refused, and citation-page precision was 1.0. Native, scanned and header-over-scan groups had CER/WER 0 on these synthetic pages. The PDFs were visually checked before inference. This is not a measurement of arbitrary real-world OCR.

The fixture SHA-256 is `359df88268566e1eff763057e6a2ddbadd19b12c09e4938b62d5585091681249`. It was frozen before candidate changes and inference. The first run is retained, without tuning against its results. This is a fresh same-assistant authored evaluation, **not independent human evaluation or an external benchmark**. The old acceptance fixture was used during development; its improved 24/24 hybrid result repairs the five observed Phase 10 failures but is regression evidence, not fresh acceptance evidence.

## Selection audit and source versions

The audit replayed 65 saved hybrid cases using retrieved and reversed passage orders, twice each: **260/260 contracts passed**, including 164 answerable and 96 unsupported observations, with zero errors. All 65 cases produced stable answer fingerprints. Grouping and source scoping made selector inputs identical under reversal for 64 cases; only one case had distinct selector inputs. Therefore the audit primarily measures repeated-input stability, with limited actual order variation; it does not establish broad order independence.

The first full backend run found sentence-initial words incorrectly treated as names. The correction ignores a single ordinary capitalized opener and adds `did` to ignored question words. Three new regression cases cover that grammar boundary; the old missing-name retry test now checks the intentional zero-model-call refusal.

The acceptance-v2, record-support and quality reports record generation hash `7382264cb424a56547a10d5fd86e455d1b7ca4682c98594c70b52518edf6bc77`. The later source has hash `0fe7ef6b854481f237f7a042f40e8561c7cd18c8800818845d213a370e6243c9`. Offline comparison confirmed identical prompts and complete selected excerpt inputs for all **82 observations** in those three reports. Later evaluations and the 260-observation audit ran against the final hash. The earlier report hashes were preserved rather than rewritten.

## Functional checks

- **155 backend tests passed**, including authentication, subject scoping, retry behavior, source binding, API explanations and audit fingerprinting. One upstream Starlette/HTTPX deprecation warning remains.
- Ruff and tracked whitespace checks passed.
- The first browser run passed 9/10 tests. Its only failure expected a model name on an unsupported CEO-birthday question; the new guard correctly refused before inference. The test now explicitly requires a null model, `model_called=false`, `subject_scope_withheld=true`, retained retrieval evidence and no claims. Answerable delivery/review cases continue to require real cited answers.
- The corrected full browser run passed **10/10 tests in 1.3 minutes**, covering uploads, OCR, answers, source links, saved history and mobile layout. The source-panel screenshot was inspected; the embedded PDF area did not paint in that capture. Original-byte equality and page URLs passed, so embedded PDF rendering is not claimed as visually verified.
- Browser regression services use temporary SQLite/Qdrant/document storage and development authentication defaults. Their results complement the backend owner-authentication tests and live access-control checks; they do not substitute for them.
- No frontend product code or dependencies changed in Phase 11. The installed production frontend is the previously validated Phase 10 build.

## Live Mac activation and preservation

On 30 October, the launcher replaced the verified API with PID **76743**, retaining worker **4119** and Ollama **1607**. The listener was observed on **127.0.0.1:8000**. The compiled UI and authentication health flag are available; anonymous documents, history, readiness, API docs, schema and query requests return 401. The sign-in screen was opened in the app browser.

The original password handoff file returned 401 on one login attempt on 30 October. It was not retried, printed or reset. On **1 November**, the owner signed in and the final authenticated browser check passed: all 29 documents were listed, the latest 20 history entries loaded, readiness reported the model available, retrieval loaded and worker active, and the original included sample PDF returned HTTP 200. The PDF did not paint in the in-app browser capture; authenticated file access is verified, visual PDF rendering is not. All five content-table hashes and all 29 original-PDF hashes were checked again and remained unchanged, including all 35 stored queries. No credentials were read or changed during this final check. CSRF/logout and revocation remain covered by the passed backend suite and historical Phase 10 live check; they were not repeated using the owner’s current session. The owner was left signed in. See the [authenticated completion record](evaluation/phase11-authenticated-mac-2026-11-01.json).

The pre-activation snapshot found **29 documents, 44 chunks, 35 query runs, 23 vector jobs and 43 page-extraction rows**. Compared with the historical Phase 10 snapshot, there was one additional document and four saved queries, timestamped before this validation; every earlier row still matched its prior hash. All five current table hashes remained identical after activation, and all **29 original PDFs** matched their stored SHA-256 hashes. The check preserved the newer rows instead of reverting to the historical counts. No live test upload or saved answer was added by this validation.

[Deployment and preservation report](evaluation/phase11-deployment-mac-2026-10-30.json). No dependencies/models were installed, no migration/reindex was run, and no cloud deployment, commit or push occurred. Existing uncommitted and untracked project work remains; this is not a clean Git checkout.

## Evidence

- [New acceptance v2](evaluation/phase11-acceptance-v2-mac-2026-10-29.json) and [freeze record](evaluation/phase11-acceptance-freeze.json).
- [Former acceptance v1 regression](evaluation/phase11-acceptance-v1-mac-2026-10-29.json).
- [Quality](evaluation/phase11-quality-mac-2026-10-29.json), [paraphrase](evaluation/phase11-paraphrase-mac-2026-10-29.json), [record support](evaluation/phase11-record-support-mac-2026-10-29.json), [answer regression](evaluation/phase11-answer-regression-mac-2026-10-29.json), [mixed OCR](evaluation/phase11-mixed-ocr-mac-2026-10-29.json).
- [Selection audit](evaluation/phase11-selection-mac-2026-10-29.json) and [grammar input equivalence](evaluation/phase11-grammar-equivalence.json).
- Local logs: `data/local/phase11-backend-final.log`, `phase11-validation-chain.log`, `phase11-selection.log`, `phase11-browser-final.log`, `phase11-browser-verified.log`, `phase11-lint-final.log`.

Each archived inference report retains its original source hashes and raw-report digest. The local raw reports include authored-fixture diagnostic assessments. Those assessments are discarded by the production adapter and not saved in user history.

## Scope and remaining limits

The delivered application is a private, single-owner Mac PDF workspace with OCR, retrieval, excerpt-based answers, history, owner authentication and a local launcher. Source-name filtering uses English heuristics and can over-refuse or miss aliases and non-English names. Four lexical BM25 misses remain visible. Extractive citation binding proves quote provenance, not relevance or truth. Independently reviewed general accuracy/security, public hosting, separate user workspaces, semantic image/table interpretation and graph retrieval are not delivered. After reboot the user must run the launcher; there is no automatic login agent or crash supervisor. See [Mac operation](PHASE10.md) and [repair behavior](PHASE11.md).
