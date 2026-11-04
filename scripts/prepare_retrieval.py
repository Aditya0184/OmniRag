"""Download public ONNX artifacts once; pin revisions and file hashes for offline inference."""

import hashlib
import json

from huggingface_hub import HfApi, hf_hub_download
from omnirag.config import Settings

MODELS = {
    "embedding": (
        "BAAI/bge-small-en-v1.5",
        "Qdrant/bge-small-en-v1.5-onnx-Q",
        "model_optimized.onnx",
        "mit",
    ),
    "reranker": (
        "Xenova/ms-marco-MiniLM-L-6-v2",
        "Xenova/ms-marco-MiniLM-L-6-v2",
        "onnx/model.onnx",
        "apache-2.0",
    ),
}


def main():
    settings = Settings()
    path = settings.retrieval_manifest
    pinned = json.loads(path.read_text()) if path.exists() else None
    result = {"format": 1, "models": {}}
    for role, (name, repo, weights, license_name) in MODELS.items():
        old = pinned["models"][role] if pinned else None
        revision = old["revision"] if old else HfApi().model_info(repo).sha
        files = (
            list(old["files"])
            if old
            else [
                weights,
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
            ]
        )
        hashes = {}
        for filename in files:
            downloaded = hf_hub_download(
                repo,
                filename,
                revision=revision,
                local_dir=settings.retrieval_models_dir / role,
            )
            with open(downloaded, "rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if old and digest != old["files"][filename]:
                raise SystemExit(f"Checksum mismatch: {role}/{filename}")
            hashes[filename] = digest
        result["models"][role] = {
            "name": name,
            "repo": repo,
            "revision": revision,
            "license": license_name,
            "files": hashes,
        }
        print(f"Verified {role}: {name} @ {revision}", flush=True)
    if not pinned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Artifacts ready; manifest: {path.resolve()}")


if __name__ == "__main__":
    main()
