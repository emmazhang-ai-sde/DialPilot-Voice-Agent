"""Remote embedding provider adapters for the Knowledge Service."""

from __future__ import annotations

from typing import Sequence

import requests

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_embedding import DeterministicEmbeddingProvider
from rag.knowledge_service.knowledge_interfaces import EmbeddingProvider


class CohereEmbeddingProvider:
    provider_name = "cohere"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        input_type: str = "search_document",
        endpoint: str = "https://api.cohere.com/v2/embed",
        timeout: float = 30.0,
        session: object | None = None,
    ):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("Cohere API key must be configured")
        self.model_name = model_name.strip()
        if not self.model_name:
            raise ValueError("Cohere embedding model must be configured")
        self.input_type = input_type
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = session or requests
        self.dimensions: int | None = None

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        payload = {
            "texts": [str(text) for text in texts],
            "model": self.model_name,
            "input_type": self.input_type,
            "embedding_types": ["float"],
        }
        response = self.session.post(
            self.endpoint,
            headers={
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", {}).get("float", [])
        return _normalize_embeddings(embeddings, expected_count=len(texts))


class GeminiEmbeddingProvider:
    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
        endpoint_root: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 30.0,
        session: object | None = None,
    ):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("Gemini API key must be configured")
        self.model_name = model_name.strip()
        if not self.model_name:
            raise ValueError("Gemini embedding model must be configured")
        self.task_type = task_type
        self.endpoint_root = endpoint_root.rstrip("/")
        self.timeout = timeout
        self.session = session or requests
        self.dimensions: int | None = None

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            response = self.session.post(
                f"{self.endpoint_root}/models/{self.model_name}:embedContent",
                params={"key": self.api_key},
                json={
                    "model": f"models/{self.model_name}",
                    "taskType": self.task_type,
                    "content": {"parts": [{"text": str(text)}]},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            values = response.json().get("embedding", {}).get("values", [])
            embeddings.append([float(value) for value in values])
        return _normalize_embeddings(embeddings, expected_count=len(texts))


def build_embedding_provider(
    config: KnowledgeProviderConfig,
    *,
    force_deterministic: bool = False,
    session: object | None = None,
) -> EmbeddingProvider:
    if force_deterministic:
        return DeterministicEmbeddingProvider()
    for provider in config.provider_order("embedding"):
        if provider == "cohere" and config.is_provider_configured("cohere"):
            return CohereEmbeddingProvider(
                api_key=config.cohere_api_key,
                model_name=config.cohere_embedding_model,
                session=session,
            )
        if provider == "gemini" and config.is_provider_configured("gemini"):
            return GeminiEmbeddingProvider(
                api_key=config.gemini_api_key,
                model_name=config.gemini_embedding_model,
                session=session,
            )
        if provider == "sentence_transformers":
            return DeterministicEmbeddingProvider()
    return DeterministicEmbeddingProvider()


def _normalize_embeddings(embeddings: object, *, expected_count: int) -> list[list[float]]:
    vectors = [[float(value) for value in vector] for vector in list(embeddings or [])]
    if len(vectors) != expected_count:
        raise ValueError("embedding provider returned the wrong number of vectors")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) > 1:
        raise ValueError("embedding provider returned vectors with inconsistent dimensions")
    if any(not vector for vector in vectors):
        raise ValueError("embedding provider returned an empty vector")
    return vectors


__all__ = [
    "CohereEmbeddingProvider",
    "GeminiEmbeddingProvider",
    "build_embedding_provider",
]
