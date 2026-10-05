"""Shared ingestion result model for Knowledge Service pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag.knowledge_service.knowledge_models import Chunk, NormalizedDocument


@dataclass(frozen=True)
class KnowledgeIngestionResult:
    document: NormalizedDocument
    chunks: list[Chunk]
    latency_ms: float
    embeddings: list[list[float]] = field(default_factory=list)
    parser_provider: str | None = None
    chunker_provider: str = "haystack"
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    vector_provider: str | None = None
    vector_upsert_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def section_count(self) -> int:
        return len(self.document.sections)

    @property
    def has_embeddings(self) -> bool:
        return bool(self.embeddings)


__all__ = ["KnowledgeIngestionResult"]
