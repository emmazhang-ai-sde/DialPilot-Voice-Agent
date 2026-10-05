"""Qdrant integration decision helpers for Haystack Knowledge Service pipelines."""

from __future__ import annotations

from dataclasses import dataclass

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig


@dataclass(frozen=True)
class QdrantIntegrationDecision:
    official_integration_available: bool
    selected_strategy: str
    reason: str
    collection: str

    @property
    def use_official_haystack(self) -> bool:
        return self.selected_strategy == "official_haystack_qdrant"


def decide_qdrant_integration(
    config: KnowledgeProviderConfig,
    *,
    tenant_filter_validated: bool = False,
    metadata_roundtrip_validated: bool = False,
) -> QdrantIntegrationDecision:
    """Choose official qdrant-haystack only after safety checks are validated."""

    official_available = _official_qdrant_available()
    if not official_available:
        return QdrantIntegrationDecision(
            official_integration_available=False,
            selected_strategy="wrapped_globifye_qdrant",
            reason="qdrant-haystack is not importable",
            collection=config.qdrant_collection,
        )
    if not tenant_filter_validated:
        return QdrantIntegrationDecision(
            official_integration_available=True,
            selected_strategy="wrapped_globifye_qdrant",
            reason="tenant filter behavior has not been validated",
            collection=config.qdrant_collection,
        )
    if not metadata_roundtrip_validated:
        return QdrantIntegrationDecision(
            official_integration_available=True,
            selected_strategy="wrapped_globifye_qdrant",
            reason="citation metadata roundtrip has not been validated",
            collection=config.qdrant_collection,
        )
    return QdrantIntegrationDecision(
        official_integration_available=True,
        selected_strategy="official_haystack_qdrant",
        reason="official integration is importable and required safety checks passed",
        collection=config.qdrant_collection,
    )


def _official_qdrant_available() -> bool:
    try:
        from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever  # noqa: F401
        from haystack_integrations.document_stores.qdrant import QdrantDocumentStore  # noqa: F401
    except ImportError:
        return False
    return True


__all__ = ["QdrantIntegrationDecision", "decide_qdrant_integration"]
