"""Haystack-native retrieval pipeline for runtime Knowledge Service calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from haystack import Pipeline

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_embedding_providers import build_embedding_provider
from rag.knowledge_service.knowledge_haystack_components import (
    CompanyQdrantRetrieverComponent,
    CompanyQueryEmbedderComponent,
    CompanyRetrievalResultFormatterComponent,
)
from rag.knowledge_service.knowledge_interfaces import EmbeddingProvider, VectorStore
from rag.knowledge_service.knowledge_vector_store import VectorStoreRegistry


@dataclass(frozen=True)
class KnowledgeRetrievalOptions:
    top_k: int = 5
    filters: dict[str, Any] = field(default_factory=dict)
    score_floor: float | None = None

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        object.__setattr__(self, "filters", dict(self.filters))


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    query: str
    company_id: str
    rows: list[dict[str, Any]]
    evidence: str
    latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chunks(self) -> list[dict[str, Any]]:
        return self.rows

    @property
    def has_evidence(self) -> bool:
        return bool(self.rows)

    def to_runtime_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "query": self.query,
            "company_id": self.company_id,
            "has_evidence": self.has_evidence,
            "evidence": self.evidence,
            "chunks": self.rows,
            "latency_ms": self.latency_ms,
            "metadata": dict(self.metadata),
        }


class CompanyHaystackQueryPipeline:
    """Embeds a query, retrieves tenant-filtered chunks, and formats evidence."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ):
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.pipeline = Pipeline()
        self.pipeline.add_component("query_embedder", CompanyQueryEmbedderComponent(embedding_provider))
        self.pipeline.add_component("retriever", CompanyQdrantRetrieverComponent(vector_store))
        self.pipeline.add_component("formatter", CompanyRetrievalResultFormatterComponent())
        self.pipeline.connect("query_embedder.query_embedding", "retriever.query_embedding")
        self.pipeline.connect("retriever.chunks", "formatter.chunks")

    @classmethod
    def from_env(cls) -> "CompanyHaystackQueryPipeline":
        config = KnowledgeProviderConfig.from_env()
        return cls(
            embedding_provider=build_embedding_provider(config),
            vector_store=VectorStoreRegistry.from_config(config),
        )

    def retrieve(
        self,
        *,
        company_id: str,
        query: str,
        options: KnowledgeRetrievalOptions | None = None,
    ) -> KnowledgeRetrievalResult:
        started = perf_counter()
        query = str(query or "").strip()
        if not query:
            raise ValueError("query must be a non-empty string")
        options = options or KnowledgeRetrievalOptions()
        result = self.pipeline.run(
            {
                "query_embedder": {"query": query},
                "retriever": {
                    "company_id": company_id,
                    "top_k": options.top_k,
                    "filters": options.filters,
                    "score_floor": options.score_floor,
                },
            }
        )
        formatter = result["formatter"]
        return KnowledgeRetrievalResult(
            query=query,
            company_id=company_id,
            rows=list(formatter["rows"]),
            evidence=str(formatter["evidence"]),
            latency_ms=(perf_counter() - started) * 1000,
            metadata={
                "pipeline": "haystack",
                "embedding_provider": self.embedding_provider.provider_name,
                "vector_provider": self.vector_store.provider_name,
                "top_k": options.top_k,
                "filters": dict(options.filters),
                "score_floor": options.score_floor,
            },
        )


__all__ = [
    "CompanyHaystackQueryPipeline",
    "KnowledgeRetrievalOptions",
    "KnowledgeRetrievalResult",
]
