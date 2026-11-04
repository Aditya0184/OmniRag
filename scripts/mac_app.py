"""Start, inspect or stop this Mac's private OmniRAG installation (loopback only)."""

import argparse
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx
from omnirag.auth import AuthStore
from omnirag.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv/bin/python")
COMMANDS = {
    "api": [PYTHON, "-m", "uvicorn", "omnirag.main:app", "--host", "127.0.0.1", "--port", "8000"],
    "worker": [PYTHON, "-m", "omnirag.worker"],
}


def identity(pid, command):
    if not isinstance(pid, int) or pid <= 1:
        return False
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True
    )
    cwd = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True
    )
    return result.stdout.strip() == " ".join(command) and "n" + str(ROOT) in cwd.stdout.splitlines()


def alive(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
    return result.returncode == 0 and not result.stdout.strip().startswith("Z")


def stop_verified(pid, command):
    if not identity(pid, command):
        raise RuntimeError("Process identity changed; refusing to stop it.")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 20
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    if alive(pid):
        raise RuntimeError("Process did not stop. No force kill or duplicate launch performed.")


def port_open(port):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "restart", "stop", "status"])
    args = parser.parse_args()
    os.chdir(ROOT)
    settings = Settings()
    data = settings.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    with (data / "mac-app.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = data / "services.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}

        def save():
            temporary = state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=2) + "\n")
            temporary.replace(state_path)

        if args.action == "status":
            print(
                json.dumps(
                    {
                        name: {"pid": state.get(name), "verified": identity(state.get(name), cmd)}
                        for name, cmd in COMMANDS.items()
                    },
                    indent=2,
                )
            )
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.get("http://127.0.0.1:8000/api/v1/health")
                response.raise_for_status()
                print(json.dumps(response.json()))
            return
        if args.action in {"start", "restart"}:
            store = AuthStore(data / "auth")
            if not store.path.exists() or not store.configured():
                raise RuntimeError("Set up the owner first: .venv/bin/python scripts/owner.py")
            if not (ROOT / "frontend/dist/index.html").exists():
                raise RuntimeError("Build the UI first: npm --prefix frontend run build")
        for name in (
            ["api", "worker"]
            if args.action == "stop"
            else ["api"]
            if args.action == "restart"
            else []
        ):
            pid = state.get(name)
            if pid and alive(pid):
                stop_verified(pid, COMMANDS[name])
            state.pop(name, None)
            save()
        if args.action == "stop":
            print(
                "Verified API and worker stopped. Documents and the shared Ollama service remain."
            )
            return
        logs = data / "logs"
        logs.mkdir(exist_ok=True)
        env = {
            **os.environ,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", ""),
            "OMNIRAG_AUTH_ENABLED": "true",
            "OMNIRAG_SERVE_FRONTEND": "true",
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }

        def launch(name, command, environment):
            with (logs / f"{name}.log").open("ab") as log:
                process = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            state[name] = process.pid
            save()
            return process

        # Reuse a reachable loopback Ollama; never pull a model or stop a shared instance.
        base = str(settings.ollama_base_url)
        if settings.ollama_base_url.host not in {"127.0.0.1", "localhost", "::1", "[::1]"}:
            raise RuntimeError("Mac deployment requires a loopback Ollama endpoint.")
        with httpx.Client(timeout=3, trust_env=False) as client:
            try:
                client.get(base + "api/tags").raise_for_status()
            except httpx.HTTPError:
                if port_open(11434):
                    raise RuntimeError("Ollama port is occupied but unavailable.") from None
                ollama = shutil.which("ollama", path=env["PATH"])
                if not ollama:
                    raise RuntimeError("Ollama is not installed.") from None
                launch(
                    "ollama",
                    [ollama, "serve"],
                    {
                        **env,
                        "OLLAMA_HOST": "127.0.0.1:11434",
                        "OLLAMA_NO_CLOUD": "1",
                        "OLLAMA_NUM_PARALLEL": "1",
                        "OLLAMA_MAX_LOADED_MODELS": "1",
                    },
                )
                for _ in range(50):
                    try:
                        client.get(base + "api/tags").raise_for_status()
                        break
                    except httpx.HTTPError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Ollama did not become ready.") from None
            if not identity(state.get("worker"), COMMANDS["worker"]):
                if state.get("worker") and alive(state["worker"]):
                    raise RuntimeError("Recorded worker identity changed; refusing a duplicate.")
                launch("worker", COMMANDS["worker"], env)
            if port_open(8000):
                if not identity(state.get("api"), COMMANDS["api"]):
                    raise RuntimeError("Port 8000 belongs to an unverified process.")
                health = client.get("http://127.0.0.1:8000/api/v1/health")
                if not health.json().get("authentication"):
                    raise RuntimeError(
                        "Old API is running. Use restart to activate the private build."
                    )
            else:
                launch("api", COMMANDS["api"], env)
            for _ in range(150):
                try:
                    health = client.get("http://127.0.0.1:8000/api/v1/health")
                    health.raise_for_status()
                    if health.json().get("authentication"):
                        page = client.get("http://127.0.0.1:8000/")
                        page.raise_for_status()
                        print("Private OmniRAG is ready: http://127.0.0.1:8000")
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            raise RuntimeError("API did not become ready. Inspect data/local/logs/api.log.")


if __name__ == "__main__":
    main()
