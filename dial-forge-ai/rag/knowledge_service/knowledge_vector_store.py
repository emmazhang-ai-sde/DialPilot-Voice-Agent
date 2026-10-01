"""Vector store implementations for Knowledge Service pipelines."""

from __future__ import annotations

import math
import uuid
from typing import Sequence

import requests

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_interfaces import VectorSearchQuery
from rag.knowledge_service.knowledge_models import Chunk, SourceMetadata


class InMemoryVectorStore:
    """Small vector store for unit tests and local offline spikes."""

    provider_name = "in_memory"

    def __init__(self):
        self._rows: list[tuple[Chunk, tuple[float, ...]]] = []

    def upsert_chunks(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        by_id = {chunk.chunk_id: (chunk, tuple(float(value) for value in embedding)) for chunk, embedding in self._rows}
        for chunk, embedding in zip(chunks, embeddings):
            vector = tuple(float(value) for value in embedding)
            if not vector:
                raise ValueError("embedding vectors must not be empty")
            by_id[chunk.chunk_id] = (chunk, vector)
        self._rows = list(by_id.values())
        return len(chunks)

    def search(self, query: VectorSearchQuery) -> list[Chunk]:
        filters = dict(query.filters)
        scored: list[Chunk] = []
        for chunk, embedding in self._rows:
            if chunk.company_id != query.company_id:
                continue
            if not _matches_filters(chunk, filters):
                continue
            score = _cosine(query.query_embedding, embedding)
            scored.append(
                Chunk(
                    chunk_id=chunk.chunk_id,
                    company_id=chunk.company_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    source=chunk.source,
                    token_count=chunk.token_count,
                    embedding_model=chunk.embedding_model,
                    metadata=dict(chunk.metadata),
                    score=score,
                )
            )
        return sorted(scored, key=lambda chunk: chunk.score or 0.0, reverse=True)[: query.top_k]


class QdrantVectorStore:
    """Qdrant REST-backed vector store for company Knowledge Service chunks."""

    provider_name = "qdrant"

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        collection: str,
        timeout: float = 15.0,
        session: object | None = None,
        distance: str = "Cosine",
    ):
        self.url = url.rstrip("/")
        if not self.url:
            raise ValueError("Qdrant URL must be configured")
        self.api_key = api_key.strip()
        if not self.api_key and not _is_local_qdrant_url(self.url):
            raise ValueError("Qdrant API key must be configured")
        self.collection = collection.strip()
        if not self.collection:
            raise ValueError("Qdrant collection must be configured")
        self.timeout = timeout
        self.session = session or requests
        self.distance = distance

    @classmethod
    def from_config(
        cls,
        config: KnowledgeProviderConfig,
        *,
        session: object | None = None,
    ) -> "QdrantVectorStore":
        return cls(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection=config.qdrant_collection,
            session=session,
        )

    def upsert_chunks(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return 0

        vectors = [tuple(float(value) for value in embedding) for embedding in embeddings]
        vector_size = len(vectors[0])
        if vector_size < 1:
            raise ValueError("embedding vectors must not be empty")
        for vector in vectors:
            if len(vector) != vector_size:
                raise ValueError("all embedding vectors must have the same dimensions")

        self.ensure_collection(vector_size=vector_size)
        points = [
            {
                "id": stable_qdrant_point_id(chunk.chunk_id),
                "vector": list(vector),
                "payload": qdrant_payload(chunk),
            }
            for chunk, vector in zip(chunks, vectors)
        ]
        response = self.session.put(
            f"{self.url}/collections/{self.collection}/points",
            headers=self._headers(),
            json={"points": points},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return len(points)

    def search(self, query: VectorSearchQuery) -> list[Chunk]:
        payload_filter = {
            "must": [
                {"key": "company_id", "match": {"value": query.company_id}},
                {"key": "tenant.company_id", "match": {"value": query.company_id}},
            ]
        }
        for key, value in query.filters.items():
            if value is None:
                continue
            payload_filter["must"].append({"key": key, "match": {"value": value}})

        response = self.session.post(
            f"{self.url}/collections/{self.collection}/points/query",
            headers=self._headers(),
            json={
                "query": list(query.query_embedding),
                "limit": query.top_k,
                "with_payload": query.include_metadata,
                "filter": payload_filter,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return [chunk_from_qdrant_point(point) for point in _qdrant_points(response.json())]

    def ensure_collection(self, *, vector_size: int) -> None:
        if vector_size < 1:
            raise ValueError("vector_size must be positive")
        response = self.session.get(
            f"{self.url}/collections/{self.collection}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code == 404:
            create_response = self.session.put(
                f"{self.url}/collections/{self.collection}",
                headers=self._headers(),
                json={"vectors": {"size": vector_size, "distance": self.distance}},
                timeout=self.timeout,
            )
            create_response.raise_for_status()
            return
        response.raise_for_status()
        self._validate_existing_collection(response.json(), vector_size=vector_size)

    def _validate_existing_collection(self, body: dict[str, object], *, vector_size: int) -> None:
        result = body.get("result") if isinstance(body, dict) else {}
        config = result.get("config") if isinstance(result, dict) else {}
        params = config.get("params") if isinstance(config, dict) else {}
        vectors = params.get("vectors") if isinstance(params, dict) else {}
        if not isinstance(vectors, dict):
            return
        existing_size = vectors.get("size")
        existing_distance = vectors.get("distance")
        if existing_size is not None and int(existing_size) != vector_size:
            raise ValueError(
                f"Qdrant collection {self.collection} vector size {existing_size} "
                f"does not match embedding dimension {vector_size}"
            )
        if existing_distance and str(existing_distance).lower() != self.distance.lower():
            raise ValueError(
                f"Qdrant collection {self.collection} distance {existing_distance} "
                f"does not match expected {self.distance}"
            )

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers


class VectorStoreRegistry:
    """Selects the configured vector store while keeping offline tests local."""

    @classmethod
    def from_config(
        cls,
        config: KnowledgeProviderConfig,
        *,
        session: object | None = None,
        force_in_memory: bool = False,
    ):
        if force_in_memory:
            return InMemoryVectorStore()
        if config.vector_provider == "qdrant" and config.is_provider_configured("qdrant"):
            return QdrantVectorStore.from_config(config, session=session)
        return InMemoryVectorStore()


def stable_qdrant_point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"globifye:knowledge-chunk:{chunk_id}"))


def qdrant_payload(chunk: Chunk) -> dict[str, object]:
    metadata = dict(chunk.metadata)
    source = chunk.source.to_dict()
    knowledge_base_id = metadata.get("knowledge_base_id")
    allowed_agent_ids = metadata.get("allowed_agent_ids")
    document_status = metadata.get("document_status")
    return {
        **metadata,
        "company_id": chunk.company_id,
        "document_id": chunk.document_id,
        "chunk_id": chunk.chunk_id,
        "document_name": chunk.source.document_name,
        "page": chunk.source.page,
        "section": chunk.source.section,
        "content": chunk.text,
        "text": chunk.text,
        "source": source,
        "tenant": {
            "company_id": chunk.company_id,
            "knowledge_base_id": knowledge_base_id,
            "allowed_agent_ids": allowed_agent_ids,
            "document_status": document_status,
        },
    }


def chunk_from_qdrant_point(point: dict[str, object]) -> Chunk:
    payload = dict(point.get("payload") or {})
    source_payload = dict(payload.get("source") or {})
    source = SourceMetadata(
        document_id=str(payload.get("document_id") or source_payload.get("document_id")),
        document_name=str(payload.get("document_name") or source_payload.get("document_name") or payload.get("document_id")),
        source_type=str(payload.get("source_type") or source_payload.get("source_type") or "unknown"),
        source_uri=payload.get("source_uri") or source_payload.get("source_uri"),
        page=payload.get("page") or source_payload.get("page"),
        section_path=tuple(source_payload.get("section_path") or payload.get("section_path") or ()),
        table_id=source_payload.get("table_id"),
        extra=dict(source_payload.get("extra") or {}),
    )
    return Chunk(
        chunk_id=str(payload.get("chunk_id") or point.get("id")),
        company_id=str(payload["company_id"]),
        document_id=str(payload["document_id"]),
        text=str(payload.get("content") or payload.get("text") or ""),
        source=source,
        token_count=_optional_int(payload.get("token_count")),
        embedding_model=str(payload["embedding_model"]) if payload.get("embedding_model") else None,
        metadata={
            key: value
            for key, value in payload.items()
            if key not in {"content", "text", "source"}
        },
        score=float(point["score"]) if point.get("score") is not None else None,
    )


def _qdrant_points(body: dict[str, object]) -> list[dict[str, object]]:
    result = body.get("result")
    if isinstance(result, dict):
        points = result.get("points", [])
        return [dict(point) for point in points if isinstance(point, dict)]
    if isinstance(result, list):
        return [dict(point) for point in result if isinstance(point, dict)]
    return []


def _matches_filters(chunk: Chunk, filters: dict[str, object]) -> bool:
    for key, expected in filters.items():
        if expected is None:
            continue
        actual = chunk.metadata.get(key)
        if actual is None and hasattr(chunk, key):
            actual = getattr(chunk, key)
        if isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _is_local_qdrant_url(url: str) -> bool:
    normalized = str(url or "").lower().strip()
    return (
        "localhost" in normalized
        or "127.0.0.1" in normalized
        or normalized.startswith("http://0.0.0.0")
    )


__all__ = [
    "InMemoryVectorStore",
    "QdrantVectorStore",
    "VectorStoreRegistry",
    "chunk_from_qdrant_point",
    "qdrant_payload",
    "stable_qdrant_point_id",
]
