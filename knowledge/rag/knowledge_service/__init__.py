"""Haystack-native company Knowledge Service.

This package is intentionally separate from the legacy Supabase/OpenAI RAG
scripts in `rag/ingest.py` and `rag/retrieval.py`.
"""

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_haystack_query_pipeline import (
    KnowledgeRetrievalOptions,
    KnowledgeRetrievalResult,
)
from rag.knowledge_service.knowledge_interfaces import ParseRequest
from rag.knowledge_service.knowledge_retrieval import QdrantKnowledgeRetrievalBackend, RetrievalRequest
from rag.knowledge_service.knowledge_service import KnowledgeService
from rag.knowledge_service.knowledge_vector_store import QdrantVectorStore, VectorStoreRegistry

__all__ = [
    "KnowledgeProviderConfig",
    "KnowledgeRetrievalOptions",
    "KnowledgeRetrievalResult",
    "KnowledgeService",
    "ParseRequest",
    "QdrantVectorStore",
    "QdrantKnowledgeRetrievalBackend",
    "RetrievalRequest",
    "VectorStoreRegistry",
]
