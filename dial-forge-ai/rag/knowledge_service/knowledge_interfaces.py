"""Provider-neutral interfaces for the Knowledge Service pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

from rag.knowledge_service.knowledge_models import Chunk, NormalizedDocument


def _clean(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(frozen=True)
class ParseRequest:
    file_path: str
    company_id: str
    document_id: str
    title: str
    source_type: str
    source_uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_path", _clean(self.file_path, "file_path"))
        object.__setattr__(self, "company_id", _clean(self.company_id, "company_id"))
        object.__setattr__(self, "document_id", _clean(self.document_id, "document_id"))
        object.__setattr__(self, "title", _clean(self.title, "title"))
        object.__setattr__(self, "source_type", _clean(self.source_type, "source_type").lower())
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True)
class VectorSearchQuery:
    company_id: str
    query_embedding: tuple[float, ...]
    top_k: int = 5
    filters: dict[str, Any] = field(default_factory=dict)
    include_metadata: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", _clean(self.company_id, "company_id"))
        object.__setattr__(self, "query_embedding", tuple(float(value) for value in self.query_embedding))
        if not self.query_embedding:
            raise ValueError("query_embedding must not be empty")
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        object.__setattr__(self, "filters", _metadata(self.filters))


@runtime_checkable
class ParserBackend(Protocol):
    provider_name: str

    def parse(self, request: ParseRequest) -> NormalizedDocument:
        ...


@runtime_checkable
class ChunkingAdapter(Protocol):
    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimensions: int | None

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        ...


@runtime_checkable
class VectorStore(Protocol):
    provider_name: str

    def upsert_chunks(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> Any:
        ...

    def search(self, query: VectorSearchQuery) -> list[Chunk]:
        ...


@runtime_checkable
class Reranker(Protocol):
    provider_name: str

    def rerank(self, *, query: str, chunks: Sequence[Chunk], top_k: int | None = None) -> list[Chunk]:
        ...


__all__ = [
    "ChunkingAdapter",
    "EmbeddingProvider",
    "ParseRequest",
    "ParserBackend",
    "Reranker",
    "VectorSearchQuery",
    "VectorStore",
]
