"""Launch isolated API/worker processes and test real HTTP, without an LLM or existing data."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from omnirag.retrieval import retrieve


def wait_for_api(url, processes):
    with httpx.Client(base_url=url, trust_env=False, timeout=2) as client:
        for _ in range(100):
            try:
                if client.get("/api/v1/health").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if any(p.poll() is not None for p in processes):
                raise SystemExit("A test service exited before startup.")
            time.sleep(0.1)
    raise SystemExit("API did not start.")


def stop_services(processes):
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    processes.clear()


def main():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="omnirag-http-") as data_dir:
        env = dict(
            os.environ,
            OMNIRAG_DATA_DIR=data_dir,
            OMNIRAG_RETRIEVAL_ENABLED="false",
            OMNIRAG_DEFAULT_RETRIEVAL_MODE="bm25",
        )
        processes = []
        try:
            commands = [
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "omnirag.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                [sys.executable, "-m", "omnirag.worker"],
            ]
            for command in commands:
                processes.append(subprocess.Popen(command, cwd=root, env=env))
            wait_for_api(url, processes)
            subprocess.run(
                [sys.executable, "scripts/smoke.py", "--base-url", url],
                cwd=root,
                env=env,
                check=True,
            )
            with httpx.Client(base_url=url, trust_env=False, timeout=5) as client:
                response = client.post(
                    "/api/v1/queries", json={"question": "Quasizorb nebular xenobiology?"}
                )
                response.raise_for_status()
                assert response.json()["status"] == "no_relevant_passage"
                assert response.json()["model"] is None
                documents = client.get("/api/v1/documents").json()
                history = client.get("/api/v1/history").json()
                database = Path(data_dir) / "omnirag.sqlite3"
                evidence = retrieve(database, "standard delivery", [], 4)
                assert evidence and evidence[0]["page"] == 1
                stop_services(processes)
                for command in commands:
                    processes.append(subprocess.Popen(command, cwd=root, env=env))
                wait_for_api(url, processes)
                assert client.get("/api/v1/documents").json() == documents
                assert client.get("/api/v1/history").json() == history
                assert retrieve(database, "standard delivery", [], 4) == evidence
                original = client.get(f"/api/v1/documents/{documents[0]['id']}/file")
                original.raise_for_status()
                assert original.content == (root / "examples/procurement_sample.pdf").read_bytes()
                print(
                    "PASS: real API/worker restart preserved documents, FTS, history and originals"
                )
        finally:
            stop_services(processes)


if __name__ == "__main__":
    main()
