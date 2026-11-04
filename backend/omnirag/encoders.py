"""Pinned offline ONNX models. No document text or inference requests leave this process."""

import hashlib
import json

from omnirag.config import Settings

WINDOW_TOKENS = 256
OVERLAP_TOKENS = 32


def token_windows(text, tokenizer, size=WINDOW_TOKENS, overlap=OVERLAP_TOKENS):
    """Use original character offsets, preserving quotation text and all tail tokens."""
    if not 0 <= overlap < size:
        raise ValueError("Invalid token window overlap")
    offsets = tokenizer.encode(text, add_special_tokens=False).offsets
    windows = []
    for start in range(0, len(offsets), size - overlap):
        part = offsets[start : start + size]
        windows.append(text[part[0][0] : part[-1][1]])
        if start + size >= len(offsets):
            break
    return windows


class LocalEncoders:
    dimensions = 384

    def __init__(self, settings: Settings):
        # Imports are lazy: BM25-only operation requires no model files or ONNX session.
        import onnxruntime as ort

        ort.disable_telemetry_events()
        from fastembed import TextEmbedding
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        from tokenizers import Tokenizer

        manifest = json.loads(settings.retrieval_manifest.read_text())
        for role, model in manifest["models"].items():
            for filename, expected in model["files"].items():
                with (settings.retrieval_models_dir / role / filename).open("rb") as source:
                    actual = hashlib.file_digest(source, "sha256").hexdigest()
                if actual != expected:
                    raise ValueError(f"Model checksum mismatch: {role}/{filename}")
        self.manifest = manifest
        identity = json.dumps(
            {
                "embedding": manifest["models"]["embedding"],
                "window": WINDOW_TOKENS,
                "overlap": OVERLAP_TOKENS,
                "pipeline": "bge-no-prefix-v1",
            },
            sort_keys=True,
        )
        self.signature = hashlib.sha256(identity.encode()).hexdigest()[:20]
        options = {
            "threads": settings.retrieval_threads,
            "providers": ["CPUExecutionProvider"],
            "local_files_only": True,
        }
        self.embedding = TextEmbedding(
            manifest["models"]["embedding"]["name"],
            specific_model_path=str(settings.retrieval_models_dir / "embedding"),
            **options,
        )
        self.reranker = TextCrossEncoder(
            manifest["models"]["reranker"]["name"],
            specific_model_path=str(settings.retrieval_models_dir / "reranker"),
            **options,
        )
        self.tokenizer = Tokenizer.from_file(
            str(settings.retrieval_models_dir / "embedding/tokenizer.json")
        )
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()

    def windows(self, text):
        return token_windows(text, self.tokenizer)

    def embed(self, texts):
        return [vector.tolist() for vector in self.embedding.embed(texts, batch_size=8)]

    def query(self, question):
        if len(self.tokenizer.encode(question).ids) > 128:
            raise ValueError("Semantic search supports questions up to 128 tokenizer tokens.")
        return self.embed([question])[0]

    def rerank(self, question, texts):
        # Both pinned models use the same WordPiece tokenizer. Score every bounded window,
        # then retain its parent passage's best score rather than truncating away its tail.
        windows = [self.windows(text) for text in texts]
        scores = iter(
            self.reranker.rerank(
                question,
                [window for group in windows for window in group],
                batch_size=8,
            )
        )
        return [max(float(next(scores)) for _ in group) for group in windows]
