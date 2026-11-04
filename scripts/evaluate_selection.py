"""Replay saved quality evidence to measure selection stability, without live data writes."""

import argparse
import hashlib
import json
import platform
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from omnirag.config import Settings
from omnirag.evaluation import score_answer, summarize_answers
from omnirag.generation import (
    GenerationError,
    OllamaGateway,
    scoped_evidence,
    source_excerpts,
    validate_citations,
)

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("retrieved", "reversed")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def load_cases(paths, mode):
    cases, inputs, seen = [], [], set()
    for path in paths:
        raw = path.read_bytes()
        report = json.loads(raw)
        if report.get("status") != "completed":
            raise ValueError(f"Report is not completed: {path}")
        fixture = report["fixture"]
        definitions = {case["id"]: case for case in fixture["queries"]}
        if len(definitions) != len(fixture["queries"]):
            raise ValueError(f"Duplicate fixture query IDs: {path}")
        expected = set(definitions)
        loaded = set()
        for row in report["queries"]:
            if row["mode"] != mode or row.get("repeat", 1) != 1:
                continue
            key = (report["fixture_sha256"], row["query"], mode)
            if key in seen:
                raise ValueError(f"Duplicate replay case: {key}")
            if row.get("error") or not isinstance(row.get("search", {}).get("evidence"), list):
                raise ValueError(f"Missing usable search evidence: {key}")
            definition = definitions[row["query"]]
            if row["question"] != definition["question"]:
                raise ValueError(f"Question differs from fixture: {key}")
            seen.add(key)
            loaded.add(row["query"])
            evidence = row["search"]["evidence"]
            if len({item["chunk_id"] for item in evidence}) != len(evidence):
                raise ValueError(f"Duplicate source chunk: {key}")
            for item in evidence:
                for field in ("chunk_id", "document_id", "document_name", "text", "page"):
                    if field not in item:
                        raise ValueError(f"Missing source field {field}: {key}")
            cases.append(
                {
                    "id": ":".join(key),
                    "report_path": str(path),
                    "definition": definition,
                    "evidence": evidence,
                    "prior_metrics": row["metrics"],
                }
            )
        if loaded != expected:
            raise ValueError(f"Report lacks all first-repeat {mode} cases: {path}")
        inputs.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
    if not cases:
        raise ValueError("No replay cases")
    return cases, inputs


def selector_fingerprint(evidence, question):
    evidence = scoped_evidence(question, evidence)
    # Mirror only the excerpt fields sent to the model, excluding opaque provenance IDs.
    return digest(
        [
            {"id": key, "source_group": value["group"], "text": value["text"]}
            for key, value in source_excerpts(evidence).items()
        ]
    )


def answer_fingerprint(response):
    # Ignore claim ordering, request-local IDs and timing; preserve every quoted source.
    claims = sorted(
        (
            claim["text"],
            tuple(
                sorted(
                    (cite["document_id"], cite["page"], cite["quote"])
                    for cite in claim["citations"]
                )
            ),
        )
        for claim in response["claims"]
    )
    return digest({"status": response["status"], "claims": claims})


def evaluate_case(gateway, case, variant, repeat):
    evidence = list(case["evidence"])
    if variant == "reversed":
        evidence.reverse()
    definition = case["definition"]
    response, usage, error = {"status": "error", "claims": []}, {}, None
    started = time.perf_counter()
    try:
        draft, usage = gateway.generate(definition["question"], evidence)
        claims = validate_citations(draft, evidence, extractive=True)
        response = {
            "status": "answered" if draft.answerable else "insufficient_evidence",
            "claims": claims,
        }
    except GenerationError as exc:
        error = exc.code
    names = {item["document_id"]: item["document_name"].removesuffix(".pdf") for item in evidence}
    return {
        "case_id": case["id"],
        "query": definition["id"],
        "variant": variant,
        "repeat": repeat,
        "answerable": definition["answerable"],
        "error": error,
        "input_order": [item["chunk_id"] for item in evidence],
        "selector_fingerprint": selector_fingerprint(evidence, definition["question"]),
        "response": response,
        "answer_fingerprint": answer_fingerprint(response),
        "usage": usage,
        "elapsed_ms": round(1000 * (time.perf_counter() - started), 2),
        "metrics": score_answer(definition, response, names, error=error),
    }


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["case_id"]].append(row)
    stability = []
    for key, group in groups.items():
        successful = [row for row in group if row["error"] is None]
        fingerprints = defaultdict(set)
        for row in successful:
            fingerprints[row["selector_fingerprint"]].add(row["answer_fingerprint"])
        stability.append(
            {
                "case_id": key,
                "query": group[0]["query"],
                "observations": len(group),
                "errors": len(group) - len(successful),
                "distinct_selector_inputs": len({row["selector_fingerprint"] for row in group}),
                "distinct_successful_answers": len(
                    {row["answer_fingerprint"] for row in successful}
                ),
                "all_contracts_pass": all(row["metrics"]["contract_pass"] for row in group),
                "any_contract_pass": any(row["metrics"]["contract_pass"] for row in group),
                "same_input_answer_changed": any(
                    len(answers) > 1 for answers in fingerprints.values()
                ),
            }
        )
    return {
        "overall": summarize_answers(rows),
        "by_variant": {
            variant: summarize_answers([row for row in rows if row["variant"] == variant])
            for variant in VARIANTS
        },
        "case_stability": stability,
        "strict_pass": bool(rows) and all(row["metrics"]["contract_pass"] for row in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument(
        "--mode", choices=("bm25", "dense", "hybrid", "hybrid_rerank"), default="hybrid_rerank"
    )
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-model", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if not args.with_model:
        parser.error("Pass --with-model to authorize actual configured Ollama calls.")
    try:
        cases, inputs = load_cases(args.report, args.mode)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    settings = Settings()
    gateway = OllamaGateway(settings)
    report = {
        "format": 1,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "mode": args.mode,
        "repeats": args.repeats,
        "variants": VARIANTS,
        "scheduled": len(cases) * len(VARIANTS) * args.repeats,
        "inputs": inputs,
        "cases": cases,
        "rows": [],
        "settings": {
            key: getattr(settings, key)
            for key in (
                "ollama_model",
                "context_tokens",
                "max_output_tokens",
                "model_timeout_seconds",
            )
        },
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/evaluate_selection.py",
                "backend/omnirag/generation.py",
                "backend/omnirag/evaluation.py",
            )
        },
        "limitations": [
            "Saved evidence replay, not a fresh retrieval or ingestion evaluation.",
            "Authored development cases, not a held-out benchmark.",
            "Lexical facts and citation pages do not establish semantic entailment.",
            "Reversing retrieved passages may leave the selector input unchanged.",
            "Repeated outputs and order effects are observations, not causal proof.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwrite and retain a valid partial report after interruption.
    with args.output.open("x") as output:
        json.dump(report, output, indent=2)
    try:
        with httpx.Client(
            base_url=str(settings.ollama_base_url), trust_env=False, timeout=5
        ) as client:
            tags = client.get("/api/tags")
            tags.raise_for_status()
            report["ollama_models"] = [
                model
                for model in tags.json()["models"]
                if model["name"] in (settings.ollama_model, settings.ollama_model + ":latest")
            ]
        for repeat in range(1, args.repeats + 1):
            for case in cases:
                for variant in VARIANTS:
                    row = evaluate_case(gateway, case, variant, repeat)
                    report["rows"].append(row)
                    args.output.write_text(json.dumps(report, indent=2) + "\n")
                    print(
                        repeat,
                        case["definition"]["id"],
                        variant,
                        row["metrics"]["contract_pass"],
                        row["error"],
                        flush=True,
                    )
        report["summary"] = summarize(report["rows"])
        report["status"] = "completed"
        report["exit_code"] = 2 if args.strict and not report["summary"]["strict_pass"] else 0
    except (Exception, KeyboardInterrupt) as exc:
        report["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        report["error"] = type(exc).__name__
        report["exit_code"] = 1
        raise
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
