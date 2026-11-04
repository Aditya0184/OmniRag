"""Create or restore a local backup of the OmniRAG workspace (data/local).

Backups capture the SQLite database through the sqlite3 backup API (consistent
under WAL), plus uploaded originals, the Qdrant directory, auth state and the
retrieval model manifest. Everything stays on this Mac under data/local/backups.

Usage from the repository root:
    .venv/bin/python scripts/backup_workspace.py backup [--label phase12]
    .venv/bin/python scripts/backup_workspace.py restore <backup-directory>
    .venv/bin/python scripts/backup_workspace.py list

Restore refuses to run while an API is listening on 127.0.0.1:8000. Stop the
services first (`.venv/bin/python scripts/mac_app.py stop`), restore, then start.
"""

import argparse
import shutil
import socket
import sqlite3
import time
from pathlib import Path

from omnirag.config import Settings

SKIP_NAMES = {"mac-app.lock", "services.json", "logs", "backups", "phase11-*", "phase12-*"}


def api_running() -> bool:
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", 8000)) == 0


def copy_database(source: Path, target: Path) -> None:
    with sqlite3.connect(source) as origin, sqlite3.connect(target) as copy:
        origin.backup(copy)


def create_backup(data_dir: Path, label: str) -> Path:
    if api_running():
        raise SystemExit(
            "The API is running on 127.0.0.1:8000. Stop it first for a consistent backup:"
            " .venv/bin/python scripts/mac_app.py stop"
        )
    database = data_dir / "omnirag.sqlite3"
    if not database.exists():
        raise SystemExit(f"No workspace database at {database}; nothing to back up.")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = data_dir / "backups" / f"{label}-{stamp}" if label else data_dir / "backups" / stamp
    if target.exists():
        raise SystemExit(f"Backup path already exists: {target}")
    target.mkdir(parents=True)
    copy_database(database, target / "omnirag.sqlite3")
    for name in ("uploads", "qdrant", "auth", "models"):
        source = data_dir / name
        if source.exists():
            shutil.copytree(source, target / name)
    print(f"Backup written to {target}")
    return target


def restore_backup(data_dir: Path, backup: Path) -> None:
    if api_running():
        raise SystemExit(
            "Refusing to restore while the API is running. Stop the services first:"
            " .venv/bin/python scripts/mac_app.py stop"
        )
    database = backup / "omnirag.sqlite3"
    if not database.exists():
        raise SystemExit(f"{backup} does not look like a workspace backup.")
    safety = data_dir / "backups" / f"pre-restore-{time.strftime('%Y%m%d-%H%M%S')}"
    safety.mkdir(parents=True)
    current = data_dir / "omnirag.sqlite3"
    if current.exists():
        copy_database(current, safety / "omnirag.sqlite3")
    shutil.copy2(database, current)
    for name in ("uploads", "qdrant", "auth", "models"):
        source, destination = backup / name, data_dir / name
        if source.exists():
            if destination.exists():
                shutil.move(destination, safety / name)
            shutil.copytree(source, destination)
    print(f"Restored {backup} into {data_dir}; previous state kept at {safety}")


def list_backups(data_dir: Path) -> None:
    root = data_dir / "backups"
    if not root.exists():
        print("No backups yet.")
        return
    for path in sorted(root.iterdir()):
        marker = "ok" if (path / "omnirag.sqlite3").exists() else "incomplete"
        print(f"{path.name}  {marker}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore", "list"])
    parser.add_argument("--label", default="")
    parser.add_argument("target", nargs="?", help="backup directory for restore")
    args = parser.parse_args()
    settings = Settings()
    settings.prepare()
    data_dir = settings.data_dir.resolve()
    if args.action == "backup":
        create_backup(data_dir, args.label)
    elif args.action == "restore":
        if not args.target:
            parser.error("restore needs a backup directory (see: list)")
        restore_backup(data_dir, Path(args.target).resolve())
    else:
        list_backups(data_dir)


if __name__ == "__main__":
    main()
