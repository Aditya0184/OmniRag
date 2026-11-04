"""Isolated OCR/retrieval/answer evaluation using the production worker and query endpoint."""

import argparse
import hashlib
import importlib.metadata
import io
import json
import platform
import re
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi.testclient import TestClient
from omnirag.config import Settings
from omnirag.db import connection, initialize
from omnirag.evaluation import score_answer, summarize_answers, transcription_metrics
from omnirag.generation import GenerationError, OllamaGateway, validate_citations, validate_grounded
from omnirag.hybrid import HybridIndex
from omnirag.main import create_app
from omnirag.worker import run_once
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_fixture(path):
    fixture = json.loads(path.read_text())
    documents = {doc["id"]: doc for doc in fixture["documents"]}
    if not documents or len(documents) != len(fixture["documents"]):
        raise ValueError("Fixture requires unique documents")
    for key, doc in documents.items():
        if not re.fullmatch(r"[a-z0-9_]+", key) or not doc["pages"]:
            raise ValueError("Invalid fixture document ID or empty pages")
        for page in doc["pages"]:
            if page["kind"] not in {"native", "scan", "degraded_scan", "header_scan"}:
                raise ValueError("Unknown fixture page kind")
            if not page["text"].strip() or page["stratum"] not in {"core", "challenge"}:
                raise ValueError("Invalid fixture page reference")
    seen = set()
    for query in fixture["queries"]:
        if query["id"] in seen or query["stratum"] not in {"core", "challenge"}:
            raise ValueError("Invalid or duplicate query")
        seen.add(query["id"])
        if query.get("kind", "answer") not in {"answer", "summary"}:
            raise ValueError("Unknown query kind")
        if not query.get("question", "").strip():
            raise ValueError("Every query needs a question")
        if query.get("kind") == "summary":
            if query["summary_of"] not in documents:
                raise ValueError("Summary query references an unknown document")
            query["scope"] = [query["summary_of"]]
        query.setdefault("scope", [])
        if any(key not in documents for key in query["scope"]):
            raise ValueError("Unknown document scope")
        for key, page in query["relevant"]:
            if key not in documents or not 1 <= page <= len(documents[key]["pages"]):
                raise ValueError("Unknown reference page")
            if query["scope"] and key not in query["scope"]:
                raise ValueError("Reference outside scope")
        if query.get("expected_status") and query["answerable"]:
            raise ValueError("Expected status with an answerable query is contradictory")
        for turn in query.get("conversation", []):
            if not turn.get("question") or "answer" not in turn:
                raise ValueError("Conversation turns need a question and an answer")
        if (
            bool(query["relevant"]) != query["answerable"]
            or (bool(query["expected_facts"]) != query["answerable"])
            or any(
                not group or not all(phrase.strip() for phrase in group)
                for group in query["expected_facts"]
            )
        ):
            raise ValueError("Answerability and reference facts disagree")
    if not seen:
        raise ValueError("Fixture has no queries")
    return fixture


def make_pdf(document):
    """Deterministic synthetic scans: no hidden text on raster-only pages."""
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(560, 720), invariant=True)
    for page in document["pages"]:
        if page["kind"] == "native":
            pdf.setFont("Helvetica", 12)
            for i, line in enumerate(simpleSplit(page["text"], "Helvetica", 12, 480)):
                pdf.drawString(40, 650 - i * 20, line)
        else:
            image = Image.new("RGB", (1400, 1800), "white")
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default(size=36)
            lines, line = [], ""
            for word in page["text"].split():
                candidate = f"{line} {word}".strip()
                if font.getlength(candidate) > 1220:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for i, line in enumerate(lines):
                draw.text((90, 180 + i * 65), line, fill="black", font=font)
            if page["kind"] == "degraded_scan":
                image = image.resize((700, 900)).resize((1400, 1800))
                image = image.rotate(2, fillcolor="white").filter(ImageFilter.GaussianBlur(0.8))
            pdf.drawImage(ImageReader(image), 0, 0, width=560, height=720)
            image.close()
            if page["kind"] == "header_scan":
                pdf.setFont("Helvetica", 12)
                pdf.drawString(40, 680, page["header"])
        pdf.showPage()
    pdf.save()
    data = output.getvalue()
    reader = PdfReader(io.BytesIO(data))
    for page, expected in zip(reader.pages, document["pages"], strict=True):
        if expected["kind"] in {"scan", "degraded_scan"} and page.extract_text():
            raise ValueError("Scan fixture unexpectedly has a hidden text layer")
    return data


class RecordingGateway(OllamaGateway):
    """Observe the real adapter without changing prompts, options or API behavior."""

    observation = None

    def _record(self, kwargs):
        self.observation = {"called": True, **kwargs}

    def generate_json(self, system, request, schema, num_predict, deadline):
        self._record({"summary_call": system[:80]})
        return super().generate_json(system, request, schema, num_predict, deadline)

    def generate(self, question, evidence):
        self._record({})
        try:
            draft, usage = super().generate(question, evidence)
            self.observation.update(draft=draft.model_dump(), usage=usage)
            self.observation["called"] = usage.get("model_called", True)
            # The endpoint repeats this validation; retain failures it otherwise withholds.
            try:
                validate_citations(draft, evidence, extractive=True)
                self.observation["quote_provenance_valid"] = True
            except GenerationError as exc:
                self.observation["error"] = exc.code
            return draft, usage
        except GenerationError as exc:
            self.observation["error"] = exc.code
            raise

    def generate_grounded(self, question, evidence, conversation=None, intent=None):
        self._record({"conversation": conversation, "intent": intent})
        try:
            draft, usage = super().generate_grounded(
                question, evidence, conversation=conversation, intent=intent
            )
            self.observation.update(draft=draft.model_dump(), usage=usage)
            self.observation["called"] = usage.get("model_called", True)
            try:
                validate_grounded(draft, evidence)
                self.observation["quote_provenance_valid"] = True
            except GenerationError as exc:
                self.observation["error"] = exc.code
            return draft, usage
        except GenerationError as exc:
            self.observation["error"] = exc.code
            raise


class EvaluationIndex(HybridIndex):
    def start(self):
        # Synchronous preparation in this isolated process, no second index owner.
        self.open()
        while self.sync_one():
            pass
        if any(state != "ready" for state in self.status()["documents"]):
            raise RuntimeError("Fixture semantic indexing failed")


def summary_query_response(summary_row):
    """Adapt a cached summary row to the query-result shape the scorer expects."""
    content = summary_row.get("content") or {}
    claims = [
        {
            "text": point.get("text", ""),
            "citations": [
                {
                    "document_id": summary_row["document_id"],
                    "document_name": summary_row.get("document_name"),
                    "page": page,
                }
                for page in point.get("pages", [])[:1]
            ],
        }
        for point in content.get("key_points", [])
    ]
    return {
        "status": "answered" if summary_row.get("status") == "ready" else summary_row.get("status"),
        "claims": claims,
        "summary": content,
        "coverage": summary_row.get("coverage"),
    }


def model_identity(settings):
    if settings.ollama_base_url.host not in {"127.0.0.1", "localhost", "::1", "[::1]"}:
        raise ValueError("Evaluation requires a loopback Ollama URL")
    with httpx.Client(base_url=str(settings.ollama_base_url), timeout=5, trust_env=False) as client:
        tags = client.get("/api/tags")
        tags.raise_for_status()
        version = client.get("/api/version")
        version.raise_for_status()
    model = next(
        (
            m
            for m in tags.json()["models"]
            if m["name"] in {settings.ollama_model, settings.ollama_model + ":latest"}
        ),
        None,
    )
    if model is None or not model.get("digest"):
        raise ValueError("Configured Ollama model or digest unavailable")
    return {"version": version.json()["version"], "model": model}


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    temporary.replace(path)


def ingest_fixture(settings, fixture, report):
    ids = {
        doc["id"]: str(uuid5(NAMESPACE_URL, "omnirag-quality-v1:" + doc["id"]))
        for doc in fixture["documents"]
    }
    for document in fixture["documents"]:
        key = document["id"]
        data = make_pdf(document)
        path = settings.uploads / f"{ids[key]}.pdf"
        path.write_bytes(data)
        with connection(settings.database) as con:
            con.execute(
                "INSERT INTO documents(id,name,sha256,size_bytes,created_at,status) "
                "VALUES(?,?,?,?,?,'queued')",
                (ids[key], key + ".pdf", digest(data), len(data), 1),
            )
        started = time.perf_counter()
        if not run_once(settings):
            raise RuntimeError("Fixture ingestion job was not claimed")
        with connection(settings.database) as con:
            row = dict(con.execute("SELECT * FROM documents WHERE id=?", (ids[key],)).fetchone())
            extracted = {
                r["page"]: dict(r)
                for r in con.execute(
                    "SELECT * FROM chunks WHERE document_id=? ORDER BY ordinal", (ids[key],)
                )
            }
            metadata = {
                r["page"]: json.loads(r["metadata"])
                for r in con.execute(
                    "SELECT * FROM page_extractions WHERE document_id=?", (ids[key],)
                )
            }
            # These intentionally short pages must fit one chunk, avoiding overlap-biased CER.
            if con.execute(
                "SELECT count(*) FROM chunks WHERE document_id=?", (ids[key],)
            ).fetchone()[0] != len(extracted):
                raise ValueError("Quality fixture pages must fit a single chunk")
        report["documents"].append(
            {
                "id": key,
                "pdf_sha256": digest(data),
                "status": row["status"],
                "error": row["error_code"],
                "ingestion_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
        for page_number, page in enumerate(document["pages"], 1):
            reference = (page["header"] + " ") if page["kind"] == "header_scan" else ""
            reference += page["text"]
            observed = extracted.get(page_number, {}).get("text", "")
            report["pages"].append(
                {
                    "document": key,
                    "page": page_number,
                    "kind": page["kind"],
                    "stratum": page["stratum"],
                    "reference": reference,
                    "observed": observed,
                    "metadata": metadata.get(page_number),
                    "error": row["error_code"],
                    "metrics": transcription_metrics(reference, observed),
                }
            )
        print(f"Ingested {key}: {row['status']}", flush=True)
    return ids


def summarize(report):
    transcription, answers = {}, {}
    for stratum in ("core", "challenge"):
        for kind in ("native", "scan", "degraded_scan", "header_scan"):
            rows = [r for r in report["pages"] if r["stratum"] == stratum and r["kind"] == kind]
            if rows:
                metrics = [r["metrics"] for r in rows]
                transcription[f"{stratum}/{kind}"] = {
                    "pages": len(rows),
                    "errors": sum(r["error"] is not None for r in rows),
                    "cer": sum(m["character_edits"] for m in metrics)
                    / sum(m["reference_characters"] for m in metrics),
                    "wer": sum(m["word_edits"] for m in metrics)
                    / sum(m["reference_words"] for m in metrics),
                }
        for mode in report["modes"]:
            rows = [r for r in report["queries"] if r["stratum"] == stratum and r["mode"] == mode]
            summary = summarize_answers(rows)
            recalls = [
                r["retrieval_page_recall"] for r in rows if r["retrieval_page_recall"] is not None
            ]
            summary["mean_retrieval_page_recall"] = statistics.mean(recalls) if recalls else None
            times = [r["elapsed_ms"] for r in rows if r.get("elapsed_ms") is not None]
            summary["median_elapsed_ms"] = statistics.median(times) if times else None
            answers[f"{stratum}/{mode}"] = summary
    return {"transcription": transcription, "answers": answers}


def evaluate(settings, fixture, report, output, repeats, with_model):
    ids = ingest_fixture(settings, fixture, report)
    names = {value: key for key, value in ids.items()}
    gateway = RecordingGateway(settings)
    index = EvaluationIndex(settings) if settings.retrieval_enabled else None
    write_report(output, report)
    with TestClient(create_app(settings, gateway, index)) as client:
        if index:
            report["retrieval_manifest"] = index.encoders.manifest
        for repeat in range(1, repeats + 1):
            for query in fixture["queries"]:
                summary_kind = query.get("summary_kind", "overview")
                modes = report["modes"] if query.get("kind") != "summary" else ["summary"]
                for mode in modes:
                    payload = {
                        "question": query["question"],
                        "document_ids": [ids[k] for k in query["scope"]],
                        "retrieval_mode": "hybrid_rerank"
                        if mode == "summary"
                        else mode,
                    }
                    if query.get("conversation"):
                        payload["conversation"] = [
                            {
                                "question": turn["question"],
                                "answer": turn["answer"],
                                "document_ids": [ids[k] for k in query["scope"]],
                            }
                            for turn in query["conversation"]
                        ]
                    row = {
                        "query": query["id"],
                        "question": query["question"],
                        "repeat": repeat,
                        "mode": mode,
                        "stratum": query["stratum"],
                        "answerable": query["answerable"],
                        "error": None,
                        "metrics": None,
                        "retrieval_page_recall": 0.0
                        if query["answerable"] and mode != "summary"
                        else None,
                        "model": {"called": False},
                    }
                    started = time.perf_counter()
                    try:
                        failed = [
                            doc["id"]
                            for doc in report["documents"]
                            if doc["error"] and (not query["scope"] or doc["id"] in query["scope"])
                        ]
                        if failed:
                            raise RuntimeError("FIXTURE_INGESTION_FAILED: " + ", ".join(failed))
                        if mode == "summary":
                            cached = client.get(
                                f"/api/v1/documents/{payload['document_ids'][0]}/summary"
                                f"?kind={summary_kind}"
                            )
                            if cached.status_code == 200 and cached.json()["status"] == "ready":
                                row["response"] = summary_query_response(cached.json())
                            else:
                                created = client.post(
                                    f"/api/v1/documents/{payload['document_ids'][0]}/summary",
                                    json={"kind": summary_kind},
                                )
                                row["response"] = created.json()
                                row["http_status"] = created.status_code
                                if created.status_code != 200:
                                    row["error"] = (
                                        created.json()
                                        .get("detail", {})
                                        .get("code", f"HTTP_{created.status_code}")
                                    )
                            row["model"] = gateway.observation or {"called": False}
                        else:
                            search = client.post("/api/v1/search", json=payload)
                            search.raise_for_status()
                            row["search"] = search.json()
                            evidence = row["search"]["evidence"]
                            if query["scope"] and any(
                                e["document_id"] not in payload["document_ids"] for e in evidence
                            ):
                                raise RuntimeError("SCOPE_LEAK")
                            ranked = {(names[e["document_id"]], e["page"]) for e in evidence}
                            relevant = {tuple(key) for key in query["relevant"]}
                            row["retrieval_page_recall"] = (
                                len(ranked & relevant) / len(relevant) if relevant else None
                            )
                            if with_model:
                                gateway.observation = {"called": False}
                                response = client.post("/api/v1/queries", json=payload)
                                row["response"] = response.json()
                                row["http_status"] = response.status_code
                                row["model"] = gateway.observation
                                row["error"] = row["model"].get("error")
                                if response.status_code != 200:
                                    row["error"] = (
                                        row["response"]
                                        .get("detail", {})
                                        .get("code", f"HTTP_{response.status_code}")
                                    )
                    except Exception as exc:
                        row["error"] = f"{type(exc).__name__}: {exc}"
                    if with_model and row.get("response") is not None:
                        row["metrics"] = score_answer(
                            query, row.get("response", {}), names, error=row["error"]
                        )
                    row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                    report["queries"].append(row)
                    report["summary"] = summarize(report)
                    write_report(output, report)
                    outcome = row["error"] or (row["metrics"] or {}).get("contract_pass", "not run")
                    print(f"{repeat} {mode} {query['id']}: {outcome}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "evaluation/quality_fixture.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--with-model", action="store_true", help="Call installed loopback Ollama")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=["bm25", "hybrid_rerank"])
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--strict", action="store_true", help="Also fail on core quality misses")
    args = parser.parse_args()
    if args.strict and not args.with_model:
        parser.error("--strict requires --with-model so answer gates are not skipped")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / f"data/local/phase4-{stamp}.json"
    if output.exists():
        parser.error("Output exists; choose a new path to preserve earlier observations")
    modes = list(dict.fromkeys(args.modes))
    report = {
        "format": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "with_model": args.with_model,
        "modes": modes,
        "repeats": args.repeats,
        "documents": [],
        "pages": [],
        "queries": [],
        "limitations": "Authored development fixture, not held-out. Fact-span and page checks "
        "are lexical proxies, not semantic entailment; negation, extra false claims and valid "
        "unlisted paraphrases require human review. CER/WER normalize NFKC and whitespace, "
        "preserve case/punctuation and may exceed 1. Failed extraction is scored as empty. "
        "Latency includes a search probe plus the query path, no warmup, sequential calls. "
        "No browser or throughput benchmark. Repeated runs do not guarantee identical outputs.",
    }
    exit_code = 1
    try:
        fixture = read_fixture(args.fixture)
        report["fixture_sha256"] = digest(args.fixture.read_bytes())
        report["fixture"] = fixture
        sources = [Path(__file__), *sorted((ROOT / "backend/omnirag").glob("*.py"))]
        report["source_sha256"] = {
            str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sources
        }
        report["packages"] = {
            name: importlib.metadata.version(name)
            for name in (
                "fastapi",
                "httpx",
                "pypdf",
                "pypdfium2",
                "pillow",
                "reportlab",
                "fastembed",
                "qdrant-client",
                "onnxruntime",
                "tokenizers",
            )
        }
        settings = Settings()
        settings.retrieval_enabled = any(mode != "bm25" for mode in modes)
        settings.default_retrieval_mode = modes[0]
        report["settings"] = settings.model_dump(mode="json", exclude={"data_dir"})
        if args.with_model:
            report["ollama"] = model_identity(settings)
        with tempfile.TemporaryDirectory(prefix="omnirag-quality-") as directory:
            settings.data_dir = Path(directory)
            settings.prepare()
            initialize(settings.database)
            evaluate(settings, fixture, report, output, args.repeats, args.with_model)
        if args.with_model and model_identity(settings) != report["ollama"]:
            raise RuntimeError("Ollama identity changed during evaluation")
        report["summary"] = summarize(report)
        errors = any(r["error"] for r in report["queries"] + report["documents"])
        report["status"] = "completed_with_errors" if errors else "completed"
        core_misses = any(
            r["stratum"] == "core" and r["metrics"] and not r["metrics"]["contract_pass"]
            for r in report["queries"]
        )
        core_misses |= any(
            r["stratum"] == "core" and (r["metrics"]["cer"] > 0.05 or r["metrics"]["wer"] > 0.10)
            for r in report["pages"]
        )
        exit_code = 1 if errors else (2 if args.strict and core_misses else 0)
    except Exception as exc:
        import traceback

        report.update(
            status="failed",
            fatal_error=f"{type(exc).__name__}: {exc}",
            fatal_traceback=traceback.format_exc(),
        )
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["exit_code"] = exit_code
        write_report(output, report)
    print(json.dumps(report.get("summary", {"error": report.get("fatal_error")}), indent=2))
    print(output.resolve())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
