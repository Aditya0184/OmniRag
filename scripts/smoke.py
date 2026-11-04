"""Real API + worker smoke test; --with-model also requires actual local Ollama generation."""

import argparse
import json
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-model", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    sample = Path(__file__).resolve().parents[1] / "examples" / "procurement_sample.pdf"
    with httpx.Client(base_url=args.base_url, timeout=180, trust_env=False) as client:
        response = client.get("/api/v1/health")
        response.raise_for_status()
        with sample.open("rb") as pdf:
            response = client.post(
                "/api/v1/documents", files={"file": (sample.name, pdf, "application/pdf")}
            )
        response.raise_for_status()
        document_id = response.json()["document"]["id"]
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            response = client.get(f"/api/v1/documents/{document_id}")
            response.raise_for_status()
            document = response.json()
            if document["status"] == "failed":
                raise SystemExit(f"Ingestion failed: {document['error_code']}")
            if document["status"] == "ready":
                break
            time.sleep(1)
        else:
            raise SystemExit("Worker did not finish. Start uv run python -m omnirag.worker.")
        assert document["page_count"] == 2
        response = client.get(f"/api/v1/documents/{document_id}/file")
        response.raise_for_status()
        assert response.content == sample.read_bytes()
        print("PASS: upload, durable worker, two-page extraction, original source download")
        if args.with_model:
            response = client.post(
                "/api/v1/queries",
                json={
                    "question": "What is the standard delivery window for Orion Supplies?",
                    "document_ids": [document_id],
                },
            )
            if response.status_code != 200:
                raise SystemExit(f"Live model check failed: {response.status_code} {response.text}")
            result = response.json()
            print(json.dumps(result, indent=2))
            if result["status"] != "answered":
                raise SystemExit(
                    "Live model abstained; inspect retrieved evidence and model output behavior."
                )
            if not any("14" in claim["text"] for claim in result["claims"]):
                raise SystemExit(
                    "Live answer did not contain the expected sample value (14). Review it."
                )
            if not any(c["page"] == 1 for claim in result["claims"] for c in claim["citations"]):
                raise SystemExit("Expected a source citation to page 1.")
            print("PASS: live model returned the expected sample value with page-1 source evidence")
        else:
            print("SKIPPED: model generation. Use --with-model after starting Ollama.")


if __name__ == "__main__":
    main()
