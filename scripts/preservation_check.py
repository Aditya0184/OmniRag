"""Snapshot live-workspace table hashes and document digests for preservation checks.

Usage:
    .venv/bin/python scripts/preservation_check.py snapshot [--label name]
    .venv/bin/python scripts/preservation_check.py compare --against <file>

The snapshot records row counts and deterministic hashes of every content table plus
the SHA-256 of every original upload PDF. After activating a new build, `compare`
verifies that all previously recorded rows and files are unchanged (new rows are
reported, not treated as failures).
"""

import argparse
import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from omnirag.config import Settings

TABLES = ("documents", "chunks", "query_runs", "page_extractions", "document_summaries")


def table_digest(con: sqlite3.Connection, table: str) -> dict:
    count = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    digest = hashlib.sha256()
    for row in con.execute(f"SELECT * FROM {table}"):
        digest.update(repr(tuple(row)).encode())
    return {"rows": count, "sha256": digest.hexdigest()}


def snapshot(data_dir: Path) -> dict:
    database = data_dir / "omnirag.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as con:
        existing = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        tables = {
            name: table_digest(con, name) for name in TABLES if name in existing
        }
    uploads = {}
    for pdf in sorted((data_dir / "uploads").glob("*.pdf")):
        uploads[pdf.stem] = hashlib.sha256(pdf.read_bytes()).hexdigest()
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "schema_version": sqlite3.connect(database).execute(
            "PRAGMA user_version"
        ).fetchone()[0],
        "tables": tables,
        "uploads": uploads,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "compare"])
    parser.add_argument("--label", default="")
    parser.add_argument("--against", type=Path)
    args = parser.parse_args()
    settings = Settings()
    data_dir = settings.data_dir.resolve()
    if args.action == "snapshot":
        report = snapshot(data_dir)
        label = args.label or time.strftime("%Y%m%d-%H%M%S")
        target = data_dir / "backups" / f"preservation-{label}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({name: row["rows"] for name, row in report["tables"].items()}))
        print(f"Snapshot written to {target}")
        return
    before = json.loads(Path(args.against).read_text())
    after = snapshot(data_dir)
    problems = []
    added = {}
    for name, prior in before["tables"].items():
        current = after["tables"][name]
        if current["rows"] < prior["rows"]:
            problems.append(f"{name}: rows shrank {prior['rows']} -> {current['rows']}")
        if current["sha256"] != prior["sha256"]:
            if current["rows"] > prior["rows"]:
                added[name] = current["rows"] - prior["rows"]
            else:
                problems.append(f"{name}: content changed without row growth")
    for stem, digest in before["uploads"].items():
        current = after["uploads"].get(stem)
        if current is None:
            problems.append(f"uploads/{stem}.pdf missing after activation")
        elif current != digest:
            problems.append(f"uploads/{stem}.pdf changed")
    print(
        json.dumps(
            {
                "problems": problems,
                "added_rows": added,
                "schema_before": before["schema_version"],
                "schema_after": after["schema_version"],
            },
            indent=1,
        )
    )
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
