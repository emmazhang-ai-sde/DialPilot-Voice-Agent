"""Provider configuration for the Knowledge Service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_DOCUMENT_PROVIDER = "azure_document_intelligence"
DEFAULT_DOCUMENT_FALLBACK_PROVIDER = "docling"
DEFAULT_EMBEDDING_PROVIDER = "cohere"
DEFAULT_EMBEDDING_ALTERNATE_PROVIDER = "gemini"
DEFAULT_EMBEDDING_FALLBACK_PROVIDER = "sentence_transformers"
DEFAULT_VECTOR_PROVIDER = "qdrant"
DEFAULT_VECTOR_ALTERNATE_PROVIDER = "weaviate"
DEFAULT_VECTOR_FALLBACK_PROVIDER = "supabase_pgvector"
DEFAULT_QDRANT_COLLECTION = "globifye_knowledge_chunks"
DEFAULT_OCR_PROVIDER = "azure_document_intelligence"
DEFAULT_OCR_FALLBACK_PROVIDER = "tesseract"
DEFAULT_RERANKER_PROVIDER = "none"
DEFAULT_COHERE_EMBEDDING_MODEL = "embed-v4.0"
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_ENV_FILE_CANDIDATES = (
    ".env.local",
    ".env",
    "ai-pipeline/.env.local",
    "ai-pipeline/.env",
)

LOCAL_PROVIDERS = {
    "docling",
    "markitdown",
    "none",
    "sentence_transformers",
    "tesseract",
    "unstructured",
}


def _value(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name) or default).strip()


def _provider(env: Mapping[str, str], name: str, default: str) -> str:
    value = _value(env, name, default).lower().replace("-", "_")
    if not value:
        raise ValueError(f"{name} must be a non-empty provider id")
    return value


def _merged_env(file_env: Mapping[str, str], runtime_env: Mapping[str, str]) -> dict[str, str]:
    merged = dict(file_env)
    merged.update(runtime_env)
    return merged


@dataclass(frozen=True)
class KnowledgeProviderConfig:
    document_provider: str = DEFAULT_DOCUMENT_PROVIDER
    document_fallback_provider: str = DEFAULT_DOCUMENT_FALLBACK_PROVIDER
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_alternate_provider: str = DEFAULT_EMBEDDING_ALTERNATE_PROVIDER
    embedding_fallback_provider: str = DEFAULT_EMBEDDING_FALLBACK_PROVIDER
    vector_provider: str = DEFAULT_VECTOR_PROVIDER
    vector_alternate_provider: str = DEFAULT_VECTOR_ALTERNATE_PROVIDER
    vector_fallback_provider: str = DEFAULT_VECTOR_FALLBACK_PROVIDER
    ocr_provider: str = DEFAULT_OCR_PROVIDER
    ocr_fallback_provider: str = DEFAULT_OCR_FALLBACK_PROVIDER
    reranker_provider: str = DEFAULT_RERANKER_PROVIDER
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_key: str = ""
    cohere_api_key: str = ""
    cohere_embedding_model: str = DEFAULT_COHERE_EMBEDDING_MODEL
    gemini_api_key: str = ""
    gemini_embedding_model: str = DEFAULT_GEMINI_EMBEDDING_MODEL
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = DEFAULT_QDRANT_COLLECTION
    weaviate_url: str = ""
    weaviate_api_key: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "KnowledgeProviderConfig":
        source = os.environ if env is None else env
        return cls.from_mapping(source)

    @classmethod
    def from_env_file(
        cls,
        path: str | os.PathLike[str],
        env: Mapping[str, str] | None = None,
    ) -> "KnowledgeProviderConfig":
        runtime_env = os.environ if env is None else env
        source = _merged_env(read_env_file(path), runtime_env)
        return cls.from_mapping(source)

    @classmethod
    def from_project_env(
        cls,
        project_root: str | os.PathLike[str],
        env: Mapping[str, str] | None = None,
    ) -> "KnowledgeProviderConfig":
        root = Path(project_root)
        runtime_env = os.environ if env is None else env
        file_env: dict[str, str] = {}
        for relative_path in DEFAULT_ENV_FILE_CANDIDATES:
            candidate = root / relative_path
            if candidate.exists():
                file_env.update(read_env_file(candidate))
        return cls.from_mapping(_merged_env(file_env, runtime_env))

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "KnowledgeProviderConfig":
        return cls(
            document_provider=_provider(source, "KNOWLEDGE_DOCUMENT_PROVIDER", DEFAULT_DOCUMENT_PROVIDER),
            document_fallback_provider=_provider(source, "KNOWLEDGE_DOCUMENT_FALLBACK_PROVIDER", DEFAULT_DOCUMENT_FALLBACK_PROVIDER),
            embedding_provider=_provider(source, "KNOWLEDGE_EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER),
            embedding_alternate_provider=_provider(source, "KNOWLEDGE_EMBEDDING_ALTERNATE_PROVIDER", DEFAULT_EMBEDDING_ALTERNATE_PROVIDER),
            embedding_fallback_provider=_provider(source, "KNOWLEDGE_EMBEDDING_FALLBACK_PROVIDER", DEFAULT_EMBEDDING_FALLBACK_PROVIDER),
            vector_provider=_provider(source, "KNOWLEDGE_VECTOR_PROVIDER", DEFAULT_VECTOR_PROVIDER),
            vector_alternate_provider=_provider(source, "KNOWLEDGE_VECTOR_ALTERNATE_PROVIDER", DEFAULT_VECTOR_ALTERNATE_PROVIDER),
            vector_fallback_provider=_provider(source, "KNOWLEDGE_VECTOR_FALLBACK_PROVIDER", DEFAULT_VECTOR_FALLBACK_PROVIDER),
            ocr_provider=_provider(source, "KNOWLEDGE_OCR_PROVIDER", DEFAULT_OCR_PROVIDER),
            ocr_fallback_provider=_provider(source, "KNOWLEDGE_OCR_FALLBACK_PROVIDER", DEFAULT_OCR_FALLBACK_PROVIDER),
            reranker_provider=_provider(source, "KNOWLEDGE_RERANKER_PROVIDER", DEFAULT_RERANKER_PROVIDER),
            azure_document_intelligence_endpoint=_value(source, "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"),
            azure_document_intelligence_key=_value(source, "AZURE_DOCUMENT_INTELLIGENCE_KEY"),
            cohere_api_key=_value(source, "COHERE_API_KEY"),
            cohere_embedding_model=_value(source, "COHERE_EMBEDDING_MODEL", DEFAULT_COHERE_EMBEDDING_MODEL),
            gemini_api_key=_value(source, "GEMINI_API_KEY", _value(source, "GOOGLE_API_KEY")),
            gemini_embedding_model=_value(source, "GEMINI_EMBEDDING_MODEL", DEFAULT_GEMINI_EMBEDDING_MODEL),
            qdrant_url=_value(source, "QDRANT_URL"),
            qdrant_api_key=_value(source, "QDRANT_API_KEY"),
            qdrant_collection=_value(source, "QDRANT_COLLECTION", DEFAULT_QDRANT_COLLECTION),
            weaviate_url=_value(source, "WEAVIATE_URL"),
            weaviate_api_key=_value(source, "WEAVIATE_API_KEY"),
            supabase_url=_value(source, "SUPABASE_SIP_URL", _value(source, "NEXT_PUBLIC_SUPABASE_URL")),
            supabase_service_role_key=_value(source, "SUPABASE_SIP_SERVICE_ROLE_KEY", _value(source, "SUPABASE_SERVICE_ROLE_KEY")),
        )

    def provider_order(self, service: str) -> tuple[str, ...]:
        if service == "document":
            return _dedupe((self.document_provider, self.document_fallback_provider))
        if service == "embedding":
            return _dedupe((self.embedding_provider, self.embedding_alternate_provider, self.embedding_fallback_provider))
        if service == "vector":
            return _dedupe((self.vector_provider, self.vector_alternate_provider, self.vector_fallback_provider))
        if service == "ocr":
            return _dedupe((self.ocr_provider, self.ocr_fallback_provider))
        if service == "reranker":
            return _dedupe((self.reranker_provider,))
        raise ValueError(f"unknown knowledge service provider group: {service}")

    def is_provider_configured(self, provider: str) -> bool:
        return not self.missing_credentials(provider)

    def missing_credentials(self, provider: str) -> tuple[str, ...]:
        normalized = provider.lower().replace("-", "_").strip()
        if normalized in LOCAL_PROVIDERS:
            return ()
        if normalized == "azure_document_intelligence":
            return _missing({
                "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": self.azure_document_intelligence_endpoint,
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": self.azure_document_intelligence_key,
            })
        if normalized == "cohere":
            return _missing({"COHERE_API_KEY": self.cohere_api_key})
        if normalized == "gemini":
            return _missing({"GEMINI_API_KEY": self.gemini_api_key})
        if normalized == "qdrant":
            return _missing({"QDRANT_URL": self.qdrant_url, "QDRANT_API_KEY": self.qdrant_api_key})
        if normalized == "weaviate":
            return _missing({"WEAVIATE_URL": self.weaviate_url, "WEAVIATE_API_KEY": self.weaviate_api_key})
        if normalized == "supabase_pgvector":
            return _missing({
                "SUPABASE_SIP_URL": self.supabase_url,
                "SUPABASE_SIP_SERVICE_ROLE_KEY": self.supabase_service_role_key,
            })
        return (f"unsupported provider: {normalized}",)

    def readiness(self) -> dict[str, dict[str, object]]:
        providers = {
            *self.provider_order("document"),
            *self.provider_order("embedding"),
            *self.provider_order("vector"),
            *self.provider_order("ocr"),
            *self.provider_order("reranker"),
        }
        return {
            provider: {"configured": self.is_provider_configured(provider), "missing": self.missing_credentials(provider)}
            for provider in sorted(providers)
        }

    def provider_summary(self) -> dict[str, object]:
        return {
            "document": self.provider_order("document"),
            "embedding": self.provider_order("embedding"),
            "vector": self.provider_order("vector"),
            "ocr": self.provider_order("ocr"),
            "reranker": self.provider_order("reranker"),
            "models": {
                "cohere_embedding_model": self.cohere_embedding_model,
                "gemini_embedding_model": self.gemini_embedding_model,
                "qdrant_collection": self.qdrant_collection,
            },
            "readiness": self.readiness(),
        }


def read_env_file(path: str | os.PathLike[str]) -> dict[str, str]:
    env_path = Path(path)
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
            continue
        values[name] = _strip_env_value(value.strip())
    return values


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _dedupe(providers: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for provider in providers:
        if provider and provider not in result:
            result.append(provider)
    return tuple(result)


def _missing(values: dict[str, str]) -> tuple[str, ...]:
    return tuple(name for name, value in values.items() if not value)


__all__ = [
    "KnowledgeProviderConfig",
    "read_env_file",
]
