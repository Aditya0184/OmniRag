"""Reproducible local retrieval ablation on an authored fixture; never writes live user data."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from omnirag.config import Settings
from omnirag.db import connection, initialize
from omnirag.encoders import LocalEncoders
from omnirag.hybrid import HybridIndex
from omnirag.retrieval import retrieve
from omnirag.worker import run_once
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")


def metrics(ranked, relevant, k=4):
    relevant = set(relevant)
    if not relevant:
        return None
    seen, unique = set(), []
    for key in ranked:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    hits = [int(key in relevant) for key in unique[:k]]
    return {
        "recall_at_4": sum(hits) / len(relevant),
        "mrr_at_4": next((1 / rank for rank, hit in enumerate(hits, 1) if hit), 0.0),
        "ndcg_at_4": sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, 1))
        / sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/local/phase2-evaluation.json"))
    args = parser.parse_args()
    fixture_path = Path("evaluation/retrieval_fixture.json")
    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes)
    settings = Settings()
    load_start = time.perf_counter()
    encoders = LocalEncoders(settings)
    load_seconds = time.perf_counter() - load_start
    results = []
    with tempfile.TemporaryDirectory(prefix="omnirag-evaluation-") as temporary:
        settings.data_dir = Path(temporary)
        settings.prepare()
        initialize(settings.database)
        ids = {
            doc["id"]: str(uuid5(NAMESPACE_URL, "omnirag-eval:" + doc["id"]))
            for doc in fixture["documents"]
        }
        names = {value: key for key, value in ids.items()}
        for doc in fixture["documents"]:
            path = settings.uploads / f"{ids[doc['id']]}.pdf"
            pdf = canvas.Canvas(str(path), invariant=True)
            for page in doc["pages"]:
                for number, line in enumerate(simpleSplit(page, "Helvetica", 12, 490)):
                    pdf.drawString(50, 740 - number * 18, line)
                pdf.showPage()
            pdf.save()
            with connection(settings.database) as con:
                con.execute(
                    "INSERT INTO documents(id,name,sha256,size_bytes,created_at,status) "
                    "VALUES(?,?,?,?,?,'queued')",
                    (
                        ids[doc["id"]],
                        doc["id"] + ".pdf",
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                        path.stat().st_size,
                        1,
                    ),
                )
            assert run_once(settings)
        index = HybridIndex(settings, encoders)
        index_start = time.perf_counter()
        index.open()
        try:
            while index.sync_one():
                pass
            assert index.status()["documents"] == {"ready": len(ids)}
            index_seconds = time.perf_counter() - index_start
            for query in fixture["queries"]:
                scope = [ids[key] for key in query.get("scope", [])]
                relevant = [tuple(key) for key in query["relevant"]]
                for mode in MODES:
                    start = time.perf_counter()
                    evidence = (
                        retrieve(settings.database, query["question"], scope, 4)
                        if mode == "bm25"
                        else index.search(query["question"], scope, mode, 4)
                    )
                    elapsed = (time.perf_counter() - start) * 1000
                    ranked = [(names[row["document_id"]], row["page"]) for row in evidence]
                    if scope:
                        assert all(row["document_id"] in scope for row in evidence)
                    results.append(
                        {
                            "query": query["id"],
                            "mode": mode,
                            "ranked": ranked,
                            "latency_ms": round(elapsed, 3),
                            "metrics": metrics(ranked, relevant),
                        }
                    )
            before = index.search("machine gets too hot", [], "hybrid_rerank", 4)
            index.close()
            index = HybridIndex(settings, encoders)
            index.open()
            assert not index.sync_one()
            assert index.search("machine gets too hot", [], "hybrid_rerank", 4) == before
        finally:
            index.close()
    summary = {}
    for mode in MODES:
        rows = [r for r in results if r["mode"] == mode]
        scored = [r["metrics"] for r in rows if r["metrics"] is not None]
        summary[mode] = {
            key: round(statistics.mean(r[key] for r in scored), 4) for key in scored[0]
        }
        summary[mode]["median_latency_ms"] = round(
            statistics.median(r["latency_ms"] for r in rows), 3
        )
        summary[mode]["unsupported_queries_with_candidates"] = sum(
            bool(r["ranked"]) for r in rows if r["metrics"] is None
        )
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "model_manifest": encoders.manifest,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("fastembed", "qdrant-client", "onnxruntime", "tokenizers")
        },
        "settings": {
            "top_k": 4,
            "candidates": settings.retrieval_candidates,
            "threads": settings.retrieval_threads,
            "rrf_k": 60,
        },
        "model_load_seconds": round(load_seconds, 3),
        "index_seconds": round(index_seconds, 3),
        "restart_preserved_ranking": True,
        "answerable_queries": 12,
        "unsupported_queries": 2,
        "summary": summary,
        "results": results,
        "limitations": "Authored development fixture, not held-out or a general benchmark. "
        "No LLM calls. Dense candidates are not proof of answerability. "
        "One run, no warmup; latency is descriptive only.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
