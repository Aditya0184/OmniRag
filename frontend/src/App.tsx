import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleAlert,
  Download,
  FileText,
  FolderOpen,
  History,
  Layers3,
  Lightbulb,
  ListChecks,
  LoaderCircle,
  MessageCircleQuestion,
  PanelRightClose,
  Search,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { fileUrl, pagePreviewUrl, request } from "./api";
import type {
  Citation,
  Document,
  QueryResult,
  Readiness,
  SummaryResponse,
} from "./api";

const examples = [
  "What is the supplier’s delivery window?",
  "What does the policy say about acceptance review?",
];
const retrievalNames: Record<string, string> = {
  bm25: "Keyword search",
  dense: "Semantic search",
  hybrid: "Hybrid search",
  hybrid_rerank: "Hybrid + reranking",
  coverage: "Document overview",
  summary: "Document summary",
};

const statusLabels: Record<string, string> = {
  answered: "Answer",
  no_relevant_passage: "No relevant passage",
  unsupported_question: "Not in the document",
  clarification_needed: "Which document?",
  insufficient_evidence: "Insufficient evidence",
};

type ThreadTurn = { question: string; answer: string; documentIds: string[] };

export default function App({ authenticated = false }: { authenticated?: boolean }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [history, setHistory] = useState<QueryResult[]>([]);
  const [question, setQuestion] = useState("");
  const [scope, setScopeState] = useState("");
  const scopeState = useRef({ id: "", revision: 0 });
  const [retrievalMode, setRetrievalMode] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [source, setSource] = useState<Citation | null>(null);
  const [view, setView] = useState<"workspace" | "history">("workspace");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [notice, setNotice] = useState("");
  const [thread, setThread] = useState<ThreadTurn[]>([]);
  const [overview, setOverview] = useState<SummaryResponse | null>(null);
  const [overviewBusy, setOverviewBusy] = useState(false);
  const [detailed, setDetailed] = useState<SummaryResponse | null>(null);
  const [showKeyPoints, setShowKeyPoints] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const lastSnapshot = useRef("");
  const ready = documents.filter((d) => d.status === "ready");
  const pages = ready.reduce((total, d) => total + (d.page_count ?? 0), 0);
  const scopedDoc = ready.find((d) => d.id === scope);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const [docs, state] = await Promise.all([
          request<Document[]>("/documents"),
          request<Readiness>("/readiness"),
        ]);
        if (active) {
          // Update only on real changes: re-rendering identical data every three
          // seconds detaches buttons and selects mid-interaction.
          const signature = JSON.stringify([docs, state]);
          if (signature !== lastSnapshot.current) {
            lastSnapshot.current = signature;
            setDocuments(docs);
            setReadiness(state);
          }
          setConnectionError("");
        }
      } catch (e) {
        if (active) setConnectionError((e as Error).message);
      }
      if (active) timer = setTimeout(refresh, 3000);
    }
    void refresh();
    request<QueryResult[]>("/history")
      .then((h) => {
        if (active) setHistory(h);
      })
      .catch(() => {});
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  function setScope(id: string) {
    if (scopeState.current.id === id) return;
    scopeState.current = { id, revision: scopeState.current.revision + 1 };
    setScopeState(id);
    setOverview(null);
    setDetailed(null);
    setShowKeyPoints(false);
    setThread([]);
    setResult(null);
    setSource(null);
    setError("");
    setNotice("");
    setBusy(false);
    setOverviewBusy(false);
  }

  // Load the selected document's cached overview; a missing one is generated on demand.
  useEffect(() => {
    let active = true;
    let loadedAt = 0;
    if (!scope) return;
    const pull = () => {
      request<SummaryResponse>(`/documents/${scope}/summary?kind=overview`)
        .then((row) => {
          if (active && row.status === "ready" && (row as { created_at?: number }).created_at !== loadedAt) {
            loadedAt = (row as { created_at?: number }).created_at ?? 0;
            setOverview(row);
          }
        })
        .catch(() => {});
    };
    pull();
    const timer = setInterval(pull, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [scope]);

  async function upload(file?: File) {
    if (!file || uploading) return;
    setError("");
    setNotice("");
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Choose a PDF file.");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await request<{ document: Document; duplicate: boolean }>(
        "/documents",
        { method: "POST", body: form },
      );
      setDocuments((docs) => [
        data.document,
        ...docs.filter((d) => d.id !== data.document.id),
      ]);
      setNotice(
        data.duplicate
          ? "This exact file is already in your workspace."
          : "Upload saved. The worker will index it shortly.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  async function ask(event?: FormEvent, overrideQuestion?: string, selectedScope = scope) {
    event?.preventDefault();
    const asked = (overrideQuestion ?? question).trim();
    if (!asked || busy) return;
    const revision = scopeState.current.revision;
    setBusy(true);
    setError("");
    setNotice("");
    setSource(null);
    setView("workspace");
    try {
      const answer = await request<QueryResult>("/queries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: asked,
          document_ids: selectedScope ? [selectedScope] : [],
          retrieval_mode:
            retrievalMode || readiness?.default_retrieval_mode || "bm25",
          conversation: (selectedScope === scope ? thread : []).slice(-2).map((turn) => ({
            question: turn.question,
            answer: turn.answer,
            document_ids: turn.documentIds,
          })),
        }),
      });
      setHistory((h) => [answer, ...h].slice(0, 20));
      if (revision !== scopeState.current.revision) return;
      setResult(answer);
      if (overrideQuestion !== undefined) setQuestion(overrideQuestion);
      const answerText = answer.claims
        .map((claim) => claim.text)
        .join(" ")
        .slice(0, 600);
      setThread((t) =>
        [
          ...t,
          {
            question: asked,
            answer: answerText,
            documentIds: answer.scope?.document_ids ?? (selectedScope ? [selectedScope] : []),
          },
        ].slice(-2),
      );
    } catch (e) {
      if (revision === scopeState.current.revision) setError((e as Error).message);
    } finally {
      if (revision === scopeState.current.revision) setBusy(false);
    }
  }

  async function generateSummary(kind: "overview" | "detailed") {
    if (!scope || overviewBusy) return;
    const revision = scopeState.current.revision;
    setOverviewBusy(true);
    setError("");
    try {
      const row = await request<SummaryResponse>(
        `/documents/${scope}/summary`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind }),
        },
        600_000,
      );
      if (revision !== scopeState.current.revision) return;
      if (row.status === "ready") {
        if (kind === "overview") {
          setOverview(row);
          setNotice("Document overview is ready.");
        } else {
          setDetailed(row);
        }
      } else {
        setError(
          row.error
            ? `Summary failed: ${row.error}`
            : "Summary could not be generated.",
        );
      }
    } catch (e) {
      if (revision === scopeState.current.revision) setError((e as Error).message);
    } finally {
      if (revision === scopeState.current.revision) setOverviewBusy(false);
    }
  }

  function openHistory(item: QueryResult) {
    setResult(item);
    setQuestion(item.question);
    setRetrievalMode(item.retrieval_mode);
    setSource(null);
    setView("workspace");
  }

  function selectCandidate(id: string) {
    setScope(id);
    void ask(undefined, result?.question ?? question, id);
  }

  const renderAnswerCard = (item: QueryResult, isHistory = false) => (
    <section className="answer-card" aria-label="Answer">
      <div className="answer-top">
        <span>
          <BookOpen size={17} />
          {statusLabels[item.status] ?? item.status}
        </span>
        <span className="elapsed">
          {(item.timings.total_ms / 1000).toFixed(1)} s
        </span>
      </div>
      <h2>{item.question}</h2>
      {item.summary && (
        <div className="summary-block">
          {item.summary.document_type && (
            <p className="summary-type">{item.summary.document_type}</p>
          )}
          {item.summary.summary && <p>{item.summary.summary}</p>}
          {item.summary.key_points && (
            <ul className="key-points">
              {item.summary.key_points.map((point, i) => (
                <li key={i}>
                  {point.text}
                  {point.pages.length > 0 && (
                    <button
                      className="page-link"
                      onClick={() =>
                        setSource({
                          document_id: item.scope?.document_ids[0] ?? "",
                          document_name: item.claims[i]?.citations[0]?.document_name ?? "",
                          page: point.pages[0],
                          quote: "",
                          chunk_id: "",
                        })
                      }
                    >
                      p. {point.pages[0]} <ArrowUpRight size={11} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {item.status === "clarification_needed" && item.candidates && (
        <div className="clarify-row" role="group" aria-label="Choose a document">
          {item.candidates.map((candidate) => (
            <button key={candidate.id} onClick={() => selectCandidate(candidate.id)}>
              <FileText size={14} /> {candidate.name}
            </button>
          ))}
        </div>
      )}
      {item.claims.map((claim, i) => (
        <div className="claim" key={i}>
          {claim.kind && (
            <span className={`claim-kind ${claim.kind}`}>
              {claim.kind === "quote" ? "Quoted" : "Explanation"}
            </span>
          )}
          <p>{claim.text}</p>
          <div className="citation-row">
            {claim.citations.map((cite, j) => (
              <button
                className="citation"
                key={`${cite.chunk_id}:${j}`}
                onClick={() => setSource(cite)}
              >
                <FileText size={13} />
                {cite.document_name} · p. {cite.page}
                {cite.extraction_method === "ocr" ? " · OCR" : ""}
                <ArrowUpRight size={12} />
              </button>
            ))}
          </div>
        </div>
      ))}
      {item.status !== "answered" && item.status !== "clarification_needed" && (
        <div className="no-answer-note">
          <p>{item.reason}</p>
          {item.suggestion && <p className="suggestion">{item.suggestion}</p>}
        </div>
      )}
      {item.status === "clarification_needed" && <p>{item.reason}</p>}
      {item.coverage && item.coverage.complete === false && (
        <p className="coverage-note">
          Partial coverage: {item.coverage.pages_used} of {item.coverage.pages_total}{" "}
          indexed pages were read.
        </p>
      )}
      {!isHistory && item.status === "answered" && item.scope && (
        <p className="scope-note">
          Answered from{" "}
          {item.scope.document_ids.length <= 1
            ? scopedDoc?.name ?? "the selected document"
            : `${item.scope.document_ids.length} selected documents`}
          {item.scope.source === "single_document" && " (your only ready document)"}
          {item.scope.source === "conversation" && " (same document as your previous question)"}
          .
        </p>
      )}
      <p className="verification-note">
        {item.verification === "grounded_citation_v1"
          ? "Every claim cites passages whose quotes were verified against the indexed text. Wording support is checked with a lexical method, not full understanding; verify important answers in the original."
          : item.verification === "document_summary"
            ? "Summary statements were checked for lexical support in their sections. Verify important points in the original."
            : item.verification === "clarification"
              ? "Choose a document to continue."
              : "Quotes and source locations are checked. Claim meaning and factual correctness still require review."}
      </p>
      {item.evidence.length > 0 && (
        <details className="evidence-details">
          <summary>
            Retrieved evidence <span>{item.evidence.length} passages</span>
          </summary>
          {item.evidence.map((item_) => (
            <button
              className="evidence-item"
              key={item_.chunk_id}
              onClick={() => setSource({ ...item_, quote: item_.text })}
            >
              <strong>
                {item_.document_name} · page {item_.page}
              </strong>
              <p>{item_.text}</p>
            </button>
          ))}
        </details>
      )}
      <div className="run-meta">
        <span>
          {retrievalNames[item.retrieval_mode] || item.retrieval_mode}
        </span>
        <span>Search {item.timings.retrieval_ms.toFixed(0)} ms</span>
        <span>
          Generation {(item.timings.generation_ms / 1000).toFixed(1)} s
        </span>
      </div>
    </section>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand">
          <span className="brand-icon">
            <Layers3 size={23} />
          </span>
          <span>
            omni<span className="brand-light">rag</span>
            <sup>AI</sup>
          </span>
        </a>
        <div className="workspace-switch">
          <span className="workspace-avatar">O</span>
          <div>
            <strong>Research workspace</strong>
            <small>Local · single user</small>
          </div>
        </div>
        <nav aria-label="Main navigation">
          <button
            className={view === "workspace" ? "nav-item active" : "nav-item"}
            onClick={() => setView("workspace")}
          >
            <Search size={17} /> Discover <ChevronRight size={14} />
          </button>
          <button
            className={view === "history" ? "nav-item active" : "nav-item"}
            onClick={() => setView("history")}
          >
            <History size={17} /> Query history{" "}
            <span className="nav-count">{history.length}</span>
          </button>
        </nav>
        <div className="section-label">
          <span>YOUR DOCUMENTS</span>
          <span>{documents.length}</span>
        </div>
        <button
          className="upload-card"
          disabled={uploading}
          onClick={() => input.current?.click()}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            void upload(event.dataTransfer.files[0]);
          }}
        >
          {uploading ? (
            <LoaderCircle className="spin" size={21} />
          ) : (
            <Upload size={21} />
          )}
          <strong>{uploading ? "Saving document…" : "Add a document"}</strong>
          <small>Drop a text or scanned PDF</small>
        </button>
        <input
          ref={input}
          type="file"
          aria-label="Upload PDF"
          accept="application/pdf,.pdf"
          hidden
          onChange={(e) => void upload(e.target.files?.[0])}
        />
        <div className="document-list" aria-live="polite">
          {documents.length === 0 && (
            <p className="empty-docs">
              Your sources will appear here.
              <br />
              Start with the included sample PDF.
            </p>
          )}
          {documents.map((doc) => (
            <div className="document" key={doc.id}>
              <FileText size={18} className="document-icon" />
              <div className="document-content">
                <button
                  className={`document-name ${scope === doc.id ? "active" : ""}`}
                  title={doc.name}
                  onClick={() =>
                    doc.status === "ready"
                      ? setScope(doc.id)
                      : setSource({
                          document_id: doc.id,
                          document_name: doc.name,
                          page: 1,
                          quote: "",
                          chunk_id: "",
                        })
                  }
                >
                  {doc.name}
                </button>
                <small className={`status status-${doc.status}`}>
                  {doc.status === "ready"
                    ? `${doc.page_count} pages · indexed`
                    : doc.status === "processing"
                      ? "Extracting and indexing…"
                      : doc.status === "queued"
                        ? "Waiting for the worker…"
                        : "Failed"}
                </small>
                {doc.status === "ready" && readiness?.retrieval?.enabled && (
                  <small className="document-warning">
                    {doc.vector_status === "ready"
                      ? "Semantic index ready"
                      : doc.vector_status === "failed"
                        ? "Semantic indexing failed"
                        : "Semantic indexing…"}
                  </small>
                )}
                {doc.error_message && (
                  <p className="document-error">{doc.error_message}</p>
                )}
                {doc.status === "failed" && (
                  <button
                    type="button"
                    onClick={() => {
                      request(`/documents/${doc.id}/retry`, { method: "POST" })
                        .then(() =>
                          setNotice(
                            "Document queued for another indexing attempt.",
                          ),
                        )
                        .catch((e) => setError((e as Error).message));
                    }}
                  >
                    Retry document
                  </button>
                )}
                {doc.warnings.map((w) => (
                  <p className="document-warning" key={w}>
                    {w}
                  </p>
                ))}
              </div>
              {doc.status === "ready" && (
                <button
                  className="doc-view-button"
                  aria-label={`View PDF of ${doc.name}`}
                  title="View the original PDF"
                  onClick={() =>
                    setSource({
                      document_id: doc.id,
                      document_name: doc.name,
                      page: 1,
                      quote: "",
                      chunk_id: "",
                    })
                  }
                >
                  <FileText size={13} />
                </button>
              )}
              {scope === doc.id ? (
                <Check size={14} className="ready-check active" />
              ) : doc.status === "ready" ? (
                <Check size={14} className="ready-check" />
              ) : doc.status === "processing" ? (
                <LoaderCircle className="spin" size={14} />
              ) : null}
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          <span className="phase-dot" />
          <div>
            <strong>Grounded answers · summaries</strong>
            <small>{authenticated ? "Private owner · local storage" : "Local development · no authentication"}</small>
          </div>
        </div>
      </aside>

      <div className="content-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <FolderOpen size={16} />
            <span>Workspace</span>
            <span>/</span>
            <strong>{view === "history" ? "History" : "Discover"}</strong>
          </div>
          <div
            className={`model-state ${readiness?.model.model_available ? "online" : ""}`}
          >
            <span />
            {connectionError
              ? "API offline"
              : readiness?.model.model_available
                ? "Local model ready"
                : "Model unavailable"}
          </div>
        </header>
        <div className={`workspace-body ${source ? "has-source" : ""}`}>
          <main>
            <div className="page-heading">
              <div>
                <div className="eyebrow">KNOWLEDGE, WITH EVIDENCE</div>
                <h1>
                  {view === "history"
                    ? "Your research trail"
                    : "Discover your documents."}
                </h1>
                <p>Ask a question. Follow the evidence back to its source.</p>
              </div>
              <div className="index-stat">
                <strong>{pages}</strong>
                <span>pages indexed</span>
              </div>
            </div>
            {(error || connectionError) && (
              <div className="alert error" role="alert">
                <CircleAlert size={18} />
                <span>{error || connectionError}</span>
                <button aria-label="Dismiss error" onClick={() => setError("")}>
                  <X size={16} />
                </button>
              </div>
            )}
            {notice && (
              <div className="alert notice" role="status">
                <Check size={17} />
                <span>{notice}</span>
              </div>
            )}
            {readiness && !readiness.worker_active && (
              <div className="alert warning">
                <CircleAlert size={17} />
                <span>
                  Ingestion worker is offline. Start it to process uploaded
                  documents.
                </span>
              </div>
            )}
            {readiness?.retrieval?.enabled && !readiness.retrieval?.loaded && (
              <div className="alert warning" role="status">
                <CircleAlert size={17} />
                <span>
                  {readiness.retrieval?.error ||
                    "Preparing semantic search… Keyword search remains available."}
                </span>
              </div>
            )}
            {!!readiness?.retrieval?.documents?.failed && (
              <div className="alert warning">
                <span>
                  Some documents could not be indexed for semantic search.
                </span>
                <button
                  type="button"
                  onClick={() => {
                    request("/retrieval/retry", { method: "POST" })
                      .then(() =>
                        setNotice("Failed semantic indexes queued for retry."),
                      )
                      .catch((e) => setError((e as Error).message));
                  }}
                >
                  Retry indexing
                </button>
              </div>
            )}
            {readiness?.model.reachable === false && (
              <div className="alert warning" role="status">
                <CircleAlert size={17} />
                <span>
                  Ollama is not reachable. Start it with the launcher or run{" "}
                  <code>ollama serve</code>; answers need the local model.
                </span>
              </div>
            )}
            {readiness?.model.reachable &&
              !readiness?.model.model_available && (
                <div className="alert warning" role="status">
                  <CircleAlert size={17} />
                  <span>
                    The configured model is not pulled yet. Run{" "}
                    <code>ollama pull {readiness.model.model}</code>.
                  </span>
                </div>
              )}

            {view === "history" ? (
              <div className="history-list">
                {history.length ? (
                  history.map((item) => (
                    <button key={item.id} onClick={() => openHistory(item)}>
                      <span>
                        <strong>{item.question}</strong>
                        <small>
                          {item.status === "answered"
                            ? item.verification === "document_summary"
                              ? "Document summary"
                              : "Cited answer"
                            : item.status === "clarification_needed"
                              ? "Needed a document choice"
                              : statusLabels[item.status] ?? item.status}{" "}
                          · {(item.timings.total_ms / 1000).toFixed(1)} s
                        </small>
                      </span>
                      <ArrowUpRight size={20} />
                    </button>
                  ))
                ) : (
                  <div className="empty-state">
                    <History size={30} />
                    <h2>No questions yet</h2>
                    <p>Your completed queries will be saved here.</p>
                  </div>
                )}
              </div>
            ) : (
              <>
                <form className="question-box" onSubmit={ask}>
                  <label htmlFor="question">
                    <Search size={17} /> Ask your workspace
                    {scopedDoc ? ` · ${scopedDoc.name}` : ""}
                  </label>
                  <textarea
                    id="question"
                    value={question}
                    maxLength={1200}
                    rows={3}
                    placeholder="What would you like to uncover?"
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        e.currentTarget.form?.requestSubmit();
                      }
                    }}
                  />
                  <div className="question-footer">
                    <select
                      aria-label="Document scope"
                      value={scope}
                      onChange={(e) => setScope(e.target.value)}
                    >
                      <option value="">All indexed documents</option>
                      {ready.map((doc) => (
                        <option key={doc.id} value={doc.id}>
                          {doc.name}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Search method"
                      value={
                        retrievalMode ||
                        readiness?.default_retrieval_mode ||
                        "bm25"
                      }
                      onChange={(e) => setRetrievalMode(e.target.value)}
                    >
                      {Object.entries(retrievalNames)
                        .filter(([mode]) => mode !== "coverage" && mode !== "summary")
                        .map(([mode, name]) => (
                          <option
                            key={mode}
                            value={mode}
                            disabled={
                              mode !== "bm25" && !readiness?.retrieval?.enabled
                            }
                          >
                            {name}
                          </option>
                        ))}
                    </select>
                    <button
                      className="ask-button"
                      disabled={
                        busy || !ready.length || question.trim().length < 3
                      }
                      type="submit"
                    >
                      {busy ? (
                        <LoaderCircle className="spin" size={17} />
                      ) : (
                        <ArrowUp size={17} />
                      )}
                      <span>{busy ? "Reading evidence…" : "Ask question"}</span>
                    </button>
                  </div>
                </form>
                {scopedDoc && (
                  <section className="overview-card" aria-label="Document overview">
                    <div className="overview-head">
                      <span className="overview-title">
                        <FileText size={16} /> About {scopedDoc.name}
                      </span>
                      <div className="overview-actions">
                        <button
                          onClick={() => void generateSummary("detailed")}
                          disabled={overviewBusy}
                        >
                          {overviewBusy ? (
                            <LoaderCircle className="spin" size={14} />
                          ) : (
                            <Sparkles size={14} />
                          )}
                          Summarize document
                        </button>
                        <button
                          onClick={() => setShowKeyPoints((value) => !value)}
                          disabled={!overview}
                        >
                          <ListChecks size={14} /> Show key points
                        </button>
                        <button onClick={() => input.current?.focus()}>
                          <MessageCircleQuestion size={14} /> Ask a question
                        </button>
                      </div>
                    </div>
                    {overviewBusy && !detailed && (
                      <p className="overview-loading">
                        Reading the document and writing an overview…
                      </p>
                    )}
                    {overview?.content && (
                      <>
                        {overview.content.summary && (
                          <p className="overview-summary">{overview.content.summary}</p>
                        )}
                        {!!overview.content.topics?.length && (
                          <div className="topic-chips">
                            {overview.content.topics.map((topic) => (
                              <span key={topic}>{topic}</span>
                            ))}
                          </div>
                        )}
                        {showKeyPoints && !!overview.content.key_points?.length && (
                          <ul className="key-points">
                            {overview.content.key_points.map((point, i) => (
                              <li key={i}>
                                {point.text}
                                {point.pages.length > 0 && (
                                  <button
                                    className="page-link"
                                    onClick={() =>
                                      setSource({
                                        document_id: scope,
                                        document_name: scopedDoc.name,
                                        page: point.pages[0],
                                        quote: "",
                                        chunk_id: "",
                                      })
                                    }
                                  >
                                    p. {point.pages[0]} <ArrowUpRight size={11} />
                                  </button>
                                )}
                              </li>
                            ))}
                          </ul>
                        )}
                        {showKeyPoints && overview.content.key_points?.length === 0 && (
                          <p className="overview-loading">
                            No key points survived support checking. Generate a
                            detailed summary for section notes.
                          </p>
                        )}
                        {!!overview.content.suggested_questions?.length && (
                          <div className="suggested-row">
                            <span className="suggested-label">
                              <Lightbulb size={14} /> Try asking
                            </span>
                            {overview.content.suggested_questions.map((suggestion) => (
                              <button
                                key={suggestion}
                                onClick={() => void ask(undefined, suggestion)}
                              >
                                {suggestion} <ArrowUpRight size={12} />
                              </button>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                    {!overview && !overviewBusy && (
                      <p className="overview-loading">
                        No overview yet. “Summarize document” creates one.
                      </p>
                    )}
                    {detailed?.content && (
                      <div className="detailed-block">
                        <h3>Detailed summary</h3>
                        {detailed.content.summary && (
                          <p>{detailed.content.summary}</p>
                        )}
                        {(detailed.content.sections ?? []).map((section, i) => (
                          <div className="section-notes" key={i}>
                            <span className="section-pages">
                              {section.pages.length > 1
                                ? `pp. ${section.pages[0]}–${section.pages[section.pages.length - 1]}`
                                : `p. ${section.pages[0]}`}
                            </span>
                            <ul>
                              {section.bullets.map((bullet, j) => (
                                <li key={j}>{bullet.text}</li>
                              ))}
                              {section.bullets.length === 0 && (
                                <li className="muted">No notable facts retained.</li>
                              )}
                            </ul>
                          </div>
                        ))}
                        {detailed.coverage && detailed.coverage.complete === false && (
                          <p className="coverage-note">
                            Partial coverage: {detailed.coverage.sections_processed} of{" "}
                            {detailed.coverage.sections_total} sections processed.
                          </p>
                        )}
                      </div>
                    )}
                  </section>
                )}
                {busy && (
                  <div className="working" role="status">
                    <LoaderCircle size={22} className="spin" />
                    <div>
                      <strong>
                        Retrieving passages and preparing an answer
                      </strong>
                      <p>
                        Local inference can take a moment. Source references
                        will be checked.
                      </p>
                    </div>
                  </div>
                )}
                {result && !busy && renderAnswerCard(result)}
                {result &&
                  !busy &&
                  result.status === "answered" &&
                  thread.length > 0 && (
                    <p className="followup-hint">
                      Ask a follow-up — the last exchange stays in context for
                      references like “it” or “they”.
                    </p>
                  )}
                {!result && !busy && !scopedDoc && (
                  <div className="starting-point">
                    <div className="section-label">A STARTING POINT</div>
                    {examples.map((example) => (
                      <button
                        key={example}
                        onClick={() => setQuestion(example)}
                      >
                        {example}
                        <ArrowUpRight size={16} />
                      </button>
                    ))}
                    <p>
                      These questions use the included fictional procurement
                      sample.
                    </p>
                  </div>
                )}
                {!result && !busy && (
                  <div className="empty-state">
                    <div className="empty-icon">
                      <Layers3 size={28} />
                    </div>
                    <h2>Your knowledge starts here.</h2>
                    <p>
                      Upload a PDF to build your first searchable collection.
                      <br />
                      Every answer keeps its evidence within reach.
                    </p>
                  </div>
                )}
              </>
            )}
            <footer className="main-footer">
              <span>OmniRAG AI</span>
              <span>Text & scanned PDFs · Local inference</span>
            </footer>
          </main>
          {source && (
            <aside className="source-panel" aria-label="Source viewer">
              <div className="source-header">
                <span>
                  <FileText size={17} /> Source evidence
                </span>
                <button
                  aria-label="Close source"
                  onClick={() => setSource(null)}
                >
                  <PanelRightClose size={19} />
                </button>
              </div>
              <h2>{source.document_name}</h2>
              <div className="source-location">
                PAGE {source.page}
                <div className="source-links">
                  <a
                    href={fileUrl(source.document_id, source.page)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open PDF <ArrowUpRight size={14} />
                  </a>
                  <a
                    href={fileUrl(source.document_id, source.page)}
                    download={source.document_name}
                  >
                    Download <Download size={13} />
                  </a>
                </div>
              </div>
              {source.quote && <blockquote>{source.quote}</blockquote>}
              {source.extraction_method === "ocr" && (
                <p className="document-warning" role="note">
                  OCR transcription. Recognition may contain errors; compare the
                  quote with the original page.
                </p>
              )}
              <img
                key={`${source.document_id}:${source.page}`}
                className="page-preview"
                title={`Page ${source.page} rendered locally from the original PDF`}
                alt={`Page ${source.page} of ${source.document_name}`}
                src={pagePreviewUrl(source.document_id, source.page)}
              />
              <p className="source-footnote">
                The quote is shown above; the page image is rendered locally from
                the original PDF. Use “Open PDF” for the full document.
              </p>
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
