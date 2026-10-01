"""Stable Knowledge Service boundary for ingestion and runtime retrieval."""

from __future__ import annotations

from typing import Any

from rag.knowledge_service.knowledge_haystack_pipeline import CompanyHaystackIngestionPipeline
from rag.knowledge_service.knowledge_haystack_query_pipeline import (
    CompanyHaystackQueryPipeline,
    KnowledgeRetrievalOptions,
    KnowledgeRetrievalResult,
)
from rag.knowledge_service.knowledge_ingestion import KnowledgeIngestionResult
from rag.knowledge_service.knowledge_interfaces import ParseRequest


class KnowledgeService:
    """Product-owned API that hides parser, embedding, and vector-store internals."""

    def __init__(
        self,
        *,
        ingestion_pipeline: CompanyHaystackIngestionPipeline,
        query_pipeline: CompanyHaystackQueryPipeline,
    ):
        self.ingestion_pipeline = ingestion_pipeline
        self.query_pipeline = query_pipeline

    @classmethod
    def from_env(cls, project_root: str | None = None) -> "KnowledgeService":
        ingestion_pipeline = CompanyHaystackIngestionPipeline.from_env(project_root)
        return cls(
            ingestion_pipeline=ingestion_pipeline,
            query_pipeline=CompanyHaystackQueryPipeline(
                embedding_provider=ingestion_pipeline.embedding_provider,
                vector_store=ingestion_pipeline.vector_store,
            ),
        )

    def ingest(self, request: ParseRequest) -> KnowledgeIngestionResult:
        return self.ingestion_pipeline.ingest(request)

    def retrieve(
        self,
        *,
        company_id: str,
        query: str,
        options: KnowledgeRetrievalOptions | None = None,
    ) -> KnowledgeRetrievalResult:
        return self.query_pipeline.retrieve(
            company_id=company_id,
            query=query,
            options=options,
        )

    def retrieval_handler(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Compatibility adapter for existing runtime retrieval handler calls."""

        top_k = int(kwargs.get("k") or kwargs.get("top_k") or 5)
        score_floor = kwargs.get("score_floor")
        if score_floor is None:
            score_floor = kwargs.get("distance_floor")
        filters = dict(kwargs.get("filters") or {})
        filters.setdefault("document_status", "active")
        result = self.retrieve(
            company_id=str(kwargs["company_key"]),
            query=str(kwargs["query"]),
            options=KnowledgeRetrievalOptions(
                top_k=top_k,
                filters=filters,
                score_floor=float(score_floor) if score_floor is not None else None,
            ),
        )
        return result.rows


__all__ = [
    "KnowledgeRetrievalOptions",
    "KnowledgeRetrievalResult",
    "KnowledgeService",
]
