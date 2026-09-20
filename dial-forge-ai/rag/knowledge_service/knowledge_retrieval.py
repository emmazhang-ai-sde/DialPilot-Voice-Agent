"""Retrieval backend adapters for Knowledge Service query paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag.knowledge_service.knowledge_interfaces import EmbeddingProvider, VectorSearchQuery, VectorStore
from rag.knowledge_service.knowledge_models import Chunk


@dataclass(frozen=True)
class RetrievalRequest:
    company_id: str
    query: str
    top_k: int = 5
    filters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.company_id.strip():
            raise ValueError("company_id is required")
        if not self.query.strip():
            raise ValueError("query is required")
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        object.__setattr__(self, "company_id", self.company_id.strip())
        object.__setattr__(self, "query", self.query.strip())
        object.__setattr__(self, "filters", dict(self.filters))


class QdrantKnowledgeRetrievalBackend:
    """Embeds one query and retrieves tenant-scoped chunks from Qdrant."""

    provider_name = "qdrant"

    def __init__(self, *, embedding_provider: EmbeddingProvider, vector_store: VectorStore):
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def retrieve(self, request: RetrievalRequest) -> list[Chunk]:
        query_embedding = self.embedding_provider.embed_texts([request.query])[0]
        return self.vector_store.search(
            VectorSearchQuery(
                company_id=request.company_id,
                query_embedding=tuple(query_embedding),
                top_k=request.top_k,
                filters=request.filters,
            )
        )

    def retrieve_dicts(self, request: RetrievalRequest) -> list[dict[str, Any]]:
        return [chunk.to_retrieval_dict() for chunk in self.retrieve(request)]


__all__ = ["QdrantKnowledgeRetrievalBackend", "RetrievalRequest"]
