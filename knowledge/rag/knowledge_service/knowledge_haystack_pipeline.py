"""Haystack-native ingestion pipeline behind the Knowledge Service boundary."""

from __future__ import annotations

from time import perf_counter

from haystack import Pipeline
from haystack.components.preprocessors import DocumentSplitter

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_embedding_providers import build_embedding_provider
from rag.knowledge_service.knowledge_haystack_adapter import HaystackChunkAdapter, HaystackChunkingConfig
from rag.knowledge_service.knowledge_haystack_components import (
    CompanyEmbedderComponent,
    CompanyMetadataNormalizerComponent,
    CompanyQdrantWriterComponent,
)
from rag.knowledge_service.knowledge_ingestion import KnowledgeIngestionResult
from rag.knowledge_service.knowledge_interfaces import EmbeddingProvider, ParseRequest, ParserBackend, VectorStore
from rag.knowledge_service.knowledge_parser_registry import ParserRegistry
from rag.knowledge_service.knowledge_vector_store import VectorStoreRegistry


class CompanyHaystackIngestionPipeline:
    """Parse, split, embed, and write documents using a Haystack graph."""

    def __init__(
        self,
        *,
        parser: ParserBackend,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        chunking_config: HaystackChunkingConfig | None = None,
    ):
        self.parser = parser
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.adapter = HaystackChunkAdapter(chunking_config)
        self.pipeline = Pipeline()
        self.pipeline.add_component("normalizer", CompanyMetadataNormalizerComponent())
        self.pipeline.add_component(
            "splitter",
            DocumentSplitter(
                split_by=self.adapter.config.split_by,
                split_length=self.adapter.config.split_length,
                split_overlap=self.adapter.config.split_overlap,
            ),
        )
        self.pipeline.add_component("embedder", CompanyEmbedderComponent(embedding_provider))
        self.pipeline.add_component("writer", CompanyQdrantWriterComponent(vector_store, adapter=self.adapter))
        self.pipeline.connect("normalizer.documents", "splitter.documents")
        self.pipeline.connect("splitter.documents", "embedder.documents")
        self.pipeline.connect("embedder.documents", "writer.documents")

    @classmethod
    def from_env(cls, project_root: str | None = None) -> "CompanyHaystackIngestionPipeline":
        config = (
            KnowledgeProviderConfig.from_project_env(project_root)
            if project_root
            else KnowledgeProviderConfig.from_env()
        )
        return cls(
            parser=ParserRegistry.from_config(config),
            embedding_provider=build_embedding_provider(config),
            vector_store=VectorStoreRegistry.from_config(config),
        )

    def ingest(self, request: ParseRequest) -> KnowledgeIngestionResult:
        started = perf_counter()
        document = self.parser.parse(request)
        haystack_documents = self.adapter.to_haystack_documents(document)
        result = self.pipeline.run({"normalizer": {"documents": haystack_documents}})
        writer_result = result["writer"]
        chunks = list(writer_result["chunks"])
        embeddings = [list(embedding) for embedding in result["embedder"]["embeddings"]]
        return KnowledgeIngestionResult(
            document=document,
            chunks=chunks,
            embeddings=embeddings,
            latency_ms=(perf_counter() - started) * 1000,
            parser_provider=document.metadata.get("parser_provider"),
            embedding_provider=self.embedding_provider.provider_name,
            embedding_model=self.embedding_provider.model_name,
            embedding_dimensions=self.embedding_provider.dimensions,
            vector_provider=self.vector_store.provider_name,
            vector_upsert_count=int(writer_result["upsert_count"]),
            metadata={
                "pipeline": "haystack",
                "knowledge_base_id": document.metadata.get("knowledge_base_id"),
            },
        )


__all__ = ["CompanyHaystackIngestionPipeline"]
