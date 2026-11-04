"""Record the actual local model digest; Ollama tags alone are not immutable experiment IDs."""

import json
from datetime import UTC, datetime

import httpx
from omnirag.config import Settings


def main():
    settings = Settings()
    with httpx.Client(base_url=str(settings.ollama_base_url), timeout=5, trust_env=False) as client:
        tags = client.get("/api/tags")
        tags.raise_for_status()
        version = client.get("/api/version")
        version.raise_for_status()
        matches = [
            m
            for m in tags.json().get("models", [])
            if m["name"] in {settings.ollama_model, f"{settings.ollama_model}:latest"}
        ]
        if not matches:
            raise SystemExit("Configured model not found. Pull it before recording the manifest.")
        details = client.post("/api/show", json={"model": settings.ollama_model})
        details.raise_for_status()
    settings.prepare()
    path = settings.data_dir / "model_manifest.json"
    manifest = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "ollama_version": version.json().get("version"),
        "model": matches[0],
        "num_ctx": settings.context_tokens,
        "num_predict": settings.max_output_tokens,
        "temperature": 0,
        "seed": 42,
        "thinking": details.json().get("thinking"),
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(path.resolve())


if __name__ == "__main__":
    main()
