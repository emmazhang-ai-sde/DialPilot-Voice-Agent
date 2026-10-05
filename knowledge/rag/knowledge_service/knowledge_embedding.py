"""Embedding providers used by Haystack-compatible Knowledge Service components."""

from __future__ import annotations

import hashlib
import math
from typing import Sequence


class DeterministicEmbeddingProvider:
    """Local deterministic embedding provider for tests and offline development."""

    provider_name = "sentence_transformers"
    model_name = "deterministic-hash-embedding"

    def __init__(self, dimensions: int = 32):
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [_embed(text, self.dimensions) for text in texts]


def _embed(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


__all__ = ["DeterministicEmbeddingProvider"]
