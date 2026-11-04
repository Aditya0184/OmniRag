"""Read-only environment inventory. Does not install packages or read credentials."""

import json
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    print("OmniRAG environment check")
    print(f"Python: {platform.python_version()} (supported: 3.11–3.13)")
    print(f"System: {platform.system()} {platform.release()} / {platform.machine()}")
    if platform.system() == "Darwin":
        print("macOS:", platform.mac_ver()[0], "(current Ollama needs macOS 14+)")
        memory = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
        print(f"Unified memory: {int(memory) / 1024**3:.1f} GiB")
    disk = shutil.disk_usage(Path.cwd())
    print(f"Available disk: {disk.free / 1024**3:.1f} GiB")
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
    print("SQLite FTS5: available")
    for name in ["uv", "node", "npm", "ollama", "git", "tesseract"]:
        binary = shutil.which(name)
        print(f"{name}: {'found' if binary else 'not found'}")
        if binary and name in {"node", "git"}:
            print(subprocess.check_output([binary, "--version"], text=True).strip())
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            names = [m["name"] for m in json.load(response).get("models", [])]
        print("Local Ollama models:", ", ".join(names) or "none pulled")
    except (URLError, TimeoutError, ValueError):
        print("Local Ollama: not reachable at 127.0.0.1:11434")
    if sys.version_info < (3, 11):  # noqa: UP036 - this preflight can run before uv creates the venv
        raise SystemExit("Use uv sync --python 3.11 to install the supported Python environment.")


if __name__ == "__main__":
    main()
