"""Haystack-compatible components for company-scoped Knowledge Service flows."""

from __future__ import annotations

from typing import Any, Sequence

from haystack import Document, component

from rag.knowledge_service.knowledge_haystack_adapter import HaystackChunkAdapter
from rag.knowledge_service.knowledge_interfaces import EmbeddingProvider, VectorSearchQuery, VectorStore
from rag.knowledge_service.knowledge_models import Chunk


@component
class CompanyMetadataNormalizerComponent:
    """Keeps tenant and citation metadata in every Haystack document."""

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]) -> dict[str, list[Document]]:
        normalized: list[Document] = []
        for doc in documents:
            meta = dict(doc.meta or {})
            _require_meta(meta, "company_id")
            _require_meta(meta, "document_id")
            meta.setdefault("source", {})
            normalized.append(Document(content=doc.content, meta=meta, id=doc.id))
        return {"documents": normalized}


@component
class CompanyEmbedderComponent:
    """Embeds chunk documents while preserving Haystack document metadata."""

    def __init__(self, embedding_provider: EmbeddingProvider):
        self.embedding_provider = embedding_provider

    @component.output_types(documents=list[Document], embeddings=list[list[float]])
    def run(self, documents: list[Document]) -> dict[str, object]:
        texts = [doc.content or "" for doc in documents]
        embeddings = self.embedding_provider.embed_texts(texts)
        if len(embeddings) != len(documents):
            raise ValueError("embedding provider returned the wrong number of vectors")

        embedded: list[Document] = []
        for doc, embedding in zip(documents, embeddings):
            meta = {**dict(doc.meta or {}), "embedding_model": self.embedding_provider.model_name}
            embedded.append(
                Document(
                    content=doc.content,
                    meta=meta,
                    id=doc.id,
                    embedding=list(embedding),
                )
            )
        return {"documents": embedded, "embeddings": embeddings}


@component
class CompanyQdrantWriterComponent:
    """Writes embedded Haystack documents through the GlobiFYE vector-store contract."""

    def __init__(self, vector_store: VectorStore, adapter: HaystackChunkAdapter | None = None):
        self.vector_store = vector_store
        self.adapter = adapter or HaystackChunkAdapter()

    @component.output_types(chunks=list[Chunk], upsert_count=int)
    def run(self, documents: list[Document]) -> dict[str, object]:
        chunks = self.adapter.from_haystack_documents(documents)
        embeddings = [list(doc.embedding or []) for doc in documents]
        if any(not embedding for embedding in embeddings):
            raise ValueError("writer requires embedded documents")
        upsert_count = self.vector_store.upsert_chunks(chunks, embeddings)
        return {"chunks": chunks, "upsert_count": int(upsert_count or 0)}


@component
class CompanyQueryEmbedderComponent:
    """Embeds the user query for a company-scoped retrieval pipeline."""

    def __init__(self, embedding_provider: EmbeddingProvider):
        self.embedding_provider = embedding_provider

    @component.output_types(query=str, query_embedding=list[float])
    def run(self, query: str) -> dict[str, object]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("query must be a non-empty string")
        return {
            "query": query,
            "query_embedding": self.embedding_provider.embed_texts([query])[0],
        }


@component
class CompanyQdrantRetrieverComponent:
    """Retrieves chunks through a mandatory tenant-scoped vector query."""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    @component.output_types(chunks=list[Chunk])
    def run(
        self,
        query_embedding: list[float],
        company_id: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        score_floor: float | None = None,
    ) -> dict[str, object]:
        if not str(company_id or "").strip():
            raise ValueError("company_id is required for retrieval")
        chunks = self.vector_store.search(
            VectorSearchQuery(
                company_id=str(company_id).strip(),
                query_embedding=tuple(float(value) for value in query_embedding),
                top_k=top_k,
                filters=dict(filters or {}),
            )
        )
        if score_floor is not None:
            chunks = [chunk for chunk in chunks if (chunk.score or 0.0) >= score_floor]
        return {"chunks": chunks}


@component
class CompanyRetrievalResultFormatterComponent:
    """Formats retrieved chunks into the runtime evidence contract."""

    @component.output_types(rows=list[dict[str, Any]], evidence=str)
    def run(self, chunks: list[Chunk]) -> dict[str, object]:
        rows = [chunk.to_retrieval_dict() for chunk in chunks]
        evidence = "\n\n".join(row["content"] for row in rows if row.get("content"))
        return {"rows": rows, "evidence": evidence}


def _require_meta(meta: dict[str, Any], key: str) -> None:
    if not str(meta.get(key) or "").strip():
        raise ValueError(f"Haystack document metadata must include {key}")


__all__ = [
    "CompanyEmbedderComponent",
    "CompanyMetadataNormalizerComponent",
    "CompanyQdrantRetrieverComponent",
    "CompanyQdrantWriterComponent",
    "CompanyQueryEmbedderComponent",
    "CompanyRetrievalResultFormatterComponent",
]
