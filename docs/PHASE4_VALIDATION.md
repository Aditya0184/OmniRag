# Phase 4 validation — 23 October 2026

The local answer/OCR evaluator is implemented and its regression checks passed. The measured application baseline **does not pass the strict quality gate**. This report preserves the failures rather than treating successful execution as successful answer quality. No generation prompt, OCR algorithm, application UI, database schema or deployment changed.

## Observed checks

| Check | Result |
|---|---|
| Backend tests | **56 passed**, zero skips, 10.05 seconds; one existing Starlette/HTTPX deprecation warning |
| Ruff | Passed for backend and scripts |
| Frontend | TypeScript/Vite production build passed; no frontend source changes |
| Evaluation integration | Actual bounded PDF worker, real Tesseract, actual BM25 and pinned ONNX/Qdrant hybrid reranking, production query endpoint through FastAPI TestClient |
| Final live run | Five documents, seven pages, ten questions × two retrieval modes; **20 query cases**, **18 actual Ollama calls**; two BM25 cases had no candidates and did not call the model |
| Operational failures | Zero ingestion, indexing, retrieval or model errors in the final run |
| Strict gate | **Exit code 2**, correctly reporting core answer/citation failures; report status `completed` means the experiment finished |
| Fixture validation | Repeated generation produced identical PDF bytes; scan pages had no hidden text; all seven rendered pages visually inspected with no clipping |
| Live data preservation | All rows unchanged in **28 documents, 41 chunks, 31 saved queries, 22 vector jobs and 41 page-extraction records**, verified by read-only before/after content hashes |
| Browser/HTTP restart tests | Not rerun for this evaluation-only change; previous Phase 3 results are historical, not claimed as new results |

The final run occurred at **19:26:10–19:26:55 IST**, about 44.8 seconds overall, on macOS 26.6.2 arm64 / Python 3.11.17. This is one sequential fixture run, with no throughput or memory measurement. An earlier exploratory run is retained separately; its initial citation contract was too permissive because it accepted any reference-page hit despite extra unrelated citations. The final scorer requires complete reference-page coverage, no off-reference citations, and expected facts in claims citing reference pages. New regression cases cover those mistakes. No fixture answers or production behavior were changed to improve scores. Only the final run appears in the tables below.

## Measured baseline

Each mode has five answerable and two unsupported **core** questions. Fact matching is a lexical proxy; the full contract additionally checks citation-page alignment. Rates include failed/abstained answerable cases.

| Core metric | BM25 | Hybrid + reranking |
|---|---:|---:|
| Mean reference-page retrieval recall at 4 | 80% | 100% |
| Expected answer facts matched | 4/5 (80%) | 3/5 (60%) |
| Correct unsupported abstentions | 2/2 | 2/2 |
| Complete answer/citation contract | 5/7 (71.4%) | 3/7 (42.9%) |
| Mean citation-page precision among answered rows | 87.5% over 4 rows | 66.7% over 3 rows |
| Median combined search/query wall time | 2,865.62 ms | 1,060.65 ms |

Latency includes an explicit search probe plus the query endpoint, which searches again. Several fast rows are abstentions. These measurements do not establish that either retrieval mode is faster or better generally. The unsupported scope-exclusion case had no BM25 candidates; its abstention was the application path, not an Ollama refusal. Hybrid supplied candidates and the model abstained.

| Transcription group | Pages | CER | WER |
|---|---:|---:|---:|
| Core native | 3 | 0% | 0% |
| Core clean scan | 1 | 0% | 0% |
| Challenge native instruction text | 1 | 0% | 0% |
| Challenge lightly degraded scan | 1 | 0% | 0% |
| Challenge native header + scanned body | 1 | **74.82%** | **72.73%** |

Zero error on one clean and one mildly degraded synthetic scan is not a general OCR accuracy claim. The header/body result measures extraction loss: the native header exceeds the OCR threshold, so the body never reaches Tesseract. Its original image visibly contains the missing policy text.

Both modes passed **1/3 challenge answer contracts**: the degraded-scan question passed; the header/body question and instruction-bearing source question returned `insufficient_evidence`. The instruction case did not emit the injected phrase, but withholding the answer also failed its expected-answer contract. This single case establishes neither prompt-injection resistance nor broad susceptibility.

## Findings requiring follow-up

1. **Quote provenance does not imply claim support.** In the hybrid similar-code answer, the main AX-742 claim cited the correct page. An extra claim about AX-724 being a low battery cited page 1's delivery policy instead. The quote existed verbatim, so production provenance validation accepted it, but it did not support the claim. The stricter evaluation flags the off-reference page. Semantic support on the same reference page can still evade these lexical/location checks.
2. **Relevant retrieval can still produce false abstention.** Hybrid found the expected page for every answerable core query, yet abstained on both the direct delivery question and its paraphrase. BM25 retrieved no evidence for the paraphrase. Retrieval coverage alone is insufficient to grade answer quality.
3. **Extra supported content lowers task relevance.** Both retention answers included unrelated record-delivery information from a different page. That information was supported by its quote, but the fixture's strict question-focused citation contract rejects the extra page. This differs from the unsupported citation relationship in finding 1.
4. **Mixed content within one page remains an OCR gap.** The native-header challenge retrieved its page successfully, but the extracted text lacked the 11-year answer. Both modes abstained. Page-level recall concealed the extraction failure; transcription scoring exposed it.

The next product improvement should address claim/citation alignment and false abstention, retaining this baseline for comparison. Region-aware OCR for pages mixing native headers and scanned bodies remains a separate follow-up. No change to those behaviors was included in this evaluation phase.

## Recorded identities and evidence

- Ollama **0.40.8**, `qwen3-vl:2b-instruct`, digest `afc393e3572c07db0bc84aa460d928a16c75f3fbb9ca9e0dccc4fbd2dafb573e`, verified unchanged before/after the experiment. Production settings retained: 4,096 context tokens, 768 output tokens, temperature 0 and seed 42.
- Tesseract **5.5.1**, English traineddata SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`; pypdfium2 **5.14.0**, PDFium **156.0.8076.0**, 200 DPI for these pages. Mean word confidence on the clean scan was 96.41; this is an engine diagnostic, not accuracy.
- Retrieval artifacts and revisions match the existing `models/retrieval.lock.json`. The report retains that manifest, all relevant package versions, effective settings, fixture and PDF hashes, and hashes of the evaluator and production Python sources. Those source hashes were checked against the final local files.
- [Compact report with all final answers/citations](evaluation/phase4-mac-2026-10-23.json). The raw report includes the fixture, extracted text, search evidence and adapter drafts under ignored `data/local/phase4-quality-final-2026-10-23.json`. The compact report records its SHA-256.
- Additional ignored evidence: `data/local/phase4-quality-2026-10-23.json` (earlier scorer), `phase4-before.json`, `phase4-preservation.json`, and rendered fixture previews in `tmp/pdfs/phase4/`.

Run commands, scoring definitions and limitations are in [PHASE4.md](PHASE4.md). No dependencies were installed or lockfiles changed. Existing `.env`, repository history, remote and previous uncommitted work were preserved. Changes remain local, uncommitted and unpushed.

The existing application answered the readiness check at the start of this work: model available, worker active, retrieval loaded, 22 semantic indexes ready. The application address remains <http://127.0.0.1:5173>. A final read-only readiness request was **not executed** because automatic approval review reached its usage limit; this was a review-service failure, not a measured app failure. The completed evaluator and database-preservation checks are independent of that final request. No service was restarted. Startup commands remain in [README](../README.md); inspect existing listeners before starting duplicates.
