"""Run the Playwright browser suite against an isolated local stack.

Temporary SQLite/Qdrant/document storage and development (no-auth) defaults:
results never touch the live workspace in data/local. Real-model cases
(OMNIRAG_E2E_MODEL=1 inside the harness) call the installed loopback Ollama.

Usage from the repository root:
    .venv/bin/python scripts/browser_tests.py [--label phase12] [--no-model]
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="")
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="Skip cases that need real Ollama generation.",
    )
    parser.add_argument(
        "--grep",
        default="",
        help="Playwright -g filter to run a subset of tests.",
    )
    args = parser.parse_args()
    label = args.label
    api_port, ui_port = free_port(), free_port()
    api = f"http://127.0.0.1:{api_port}"
    with tempfile.TemporaryDirectory(prefix="omnirag-browser-") as data, tempfile.TemporaryDirectory(  # noqa: E501
        prefix=".phase12-", dir=ROOT / "frontend"
    ) as configs:
        configs = Path(configs)
        env = {
            **os.environ,
            "OMNIRAG_DATA_DIR": data,
            "OMNIRAG_RETRIEVAL_ENABLED": "true",
            "OMNIRAG_DEFAULT_RETRIEVAL_MODE": "hybrid_rerank",
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "OMNIRAG_E2E_MODEL": "" if args.no_model else "1",
        }
        vite = configs / "vite.config.ts"
        vite.write_text(
            'import { mergeConfig } from "vite"; import base from "../vite.config";'
            " export default mergeConfig(base,"
            + json.dumps(
                {
                    "root": str(ROOT / "frontend"),
                    "server": {
                        "host": "127.0.0.1",
                        "port": ui_port,
                        "strictPort": True,
                        "proxy": {
                            "/api": {
                                "target": api,
                                "changeOrigin": True,
                                "headers": {"origin": "http://127.0.0.1:5173"},
                            }
                        },
                    },
                }
            )
            + ");"
        )
        playwright = configs / "playwright.config.ts"
        playwright.write_text(
            "export default "
            + json.dumps(
                {
                    "testDir": str(ROOT / "frontend/tests"),
                    "outputDir": str(ROOT / f"frontend/test-results/phase12{label}"),
                    "timeout": 150_000,
                    "workers": 1,
                    "use": {
                        "channel": "chromium",
                        "baseURL": f"http://127.0.0.1:{ui_port}",
                        "viewport": {"width": 1440, "height": 1000},
                        "screenshot": "only-on-failure",
                    },
                    "reporter": "list",
                }
            )
            + ";"
        )
        processes = []
        try:
            for role, command in [
                (
                    "api",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "omnirag.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                ),
                ("worker", [sys.executable, "-m", "omnirag.worker"]),
                (
                    "frontend",
                    [
                        shutil.which("node"),
                        str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                        "--config",
                        str(vite),
                    ],
                ),
            ]:
                with (ROOT / f"data/local/phase12-browser{label}-{role}.log").open("w") as log:
                    processes.append(
                        subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
                    )
            with httpx.Client(base_url=api, timeout=5, trust_env=False) as client:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if any(proc.poll() is not None for proc in processes):
                        raise RuntimeError("A temporary service exited early")
                    try:
                        ready = client.get("/api/v1/readiness")
                        ready.raise_for_status()
                        front = client.get(f"http://127.0.0.1:{ui_port}")
                        if ready.json()["retrieval"]["loaded"] and front.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.3)
                else:
                    raise RuntimeError("Temporary stack did not become ready")
                if not args.no_model:
                    # Seed one document so non-model cases have stable retrieval state.
                    with (ROOT / "examples/procurement_sample.pdf").open("rb") as source:
                        response = client.post(
                            "/api/v1/documents",
                            files={"file": ("procurement_sample.pdf", source, "application/pdf")},
                        )
                    response.raise_for_status()
                    document_id = response.json()["document"]["id"]
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        rows = client.get("/api/v1/documents").json()
                        if any(
                            row["id"] == document_id and row["vector_status"] == "ready"
                            for row in rows
                        ):
                            break
                        time.sleep(0.3)
                    else:
                        raise RuntimeError("Seed document was not indexed")
            with (ROOT / f"data/local/phase12-browser{label}.log").open("w") as log:
                test = subprocess.run(
                    [
                        shutil.which("node"),
                        str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
                        "test",
                        "--config",
                        str(playwright),
                        *([item for item in ("-g", args.grep) if args.grep]),
                    ],
                    cwd=ROOT / "frontend",
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=1200 if not args.no_model else 600,
                )
            print((ROOT / f"data/local/phase12-browser{label}.log").read_text())
            if test.returncode:
                raise SystemExit(test.returncode)
        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
            for proc in processes:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    main()
