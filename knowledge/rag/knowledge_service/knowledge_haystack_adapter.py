"""Thin translation layer between GlobiFYE models and Haystack documents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from haystack import Document
from haystack.components.preprocessors import DocumentSplitter

from rag.knowledge_service.knowledge_models import Chunk, NormalizedDocument, SourceMetadata


@dataclass(frozen=True)
class HaystackChunkingConfig:
    split_by: str = "word"
    split_length: int = 220
    split_overlap: int = 30

    def __post_init__(self) -> None:
        if self.split_length < 1:
            raise ValueError("split_length must be positive")
        if self.split_overlap < 0:
            raise ValueError("split_overlap cannot be negative")


class HaystackChunkAdapter:
    """Converts owned models to Haystack Documents and back to owned chunks."""

    provider_name = "haystack"

    def __init__(self, config: HaystackChunkingConfig | None = None):
        self.config = config or HaystackChunkingConfig()
        self._splitter = DocumentSplitter(
            split_by=self.config.split_by,
            split_length=self.config.split_length,
            split_overlap=self.config.split_overlap,
        )

    def to_haystack_documents(self, document: NormalizedDocument) -> list[Document]:
        docs: list[Document] = []
        for section in document.sections:
            if not section.text.strip():
                continue
            source = section.source_metadata(document)
            metadata = {
                **document.metadata,
                **section.metadata,
                "company_id": document.company_id,
                "document_id": document.document_id,
                "document_name": document.title,
                "source_type": document.source_type,
                "source_uri": document.source_uri,
                "section_id": section.section_id,
                "section_heading": section.heading,
                "section_path": list(section.section_path),
                "page_start": section.page_start,
                "page_end": section.page_end,
                "source": source.to_dict(),
            }
            metadata.setdefault("document_status", "active")
            docs.append(Document(content=section.text, meta=metadata, id=section.section_id))
        return docs

    def split_documents(self, documents: list[Document]) -> list[Document]:
        if not documents:
            return []
        return list(self._splitter.run(documents=documents)["documents"])

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        return self.from_haystack_documents(
            self.split_documents(self.to_haystack_documents(document))
        )

    def from_haystack_documents(self, documents: list[Document]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for index, doc in enumerate(documents):
            content = (doc.content or "").strip()
            if not content:
                continue
            meta = dict(doc.meta or {})
            source = _source_from_meta(meta)
            chunk_id = str(meta.get("chunk_id") or _chunk_id(meta, doc.id, index))
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    company_id=str(meta["company_id"]),
                    document_id=str(meta["document_id"]),
                    text=content,
                    source=source,
                    token_count=len(content.split()),
                    embedding_model=meta.get("embedding_model"),
                    metadata=_chunk_metadata(meta),
                    score=doc.score,
                )
            )
        return chunks


def _source_from_meta(meta: dict[str, Any]) -> SourceMetadata:
    source = dict(meta.get("source") or {})
    return SourceMetadata(
        document_id=str(meta.get("document_id") or source.get("document_id")),
        document_name=str(meta.get("document_name") or source.get("document_name") or meta.get("document_id")),
        source_type=str(meta.get("source_type") or source.get("source_type") or "unknown"),
        source_uri=meta.get("source_uri") or source.get("source_uri"),
        page=meta.get("page_start") or source.get("page"),
        section_path=tuple(meta.get("section_path") or source.get("section_path") or ()),
        table_id=source.get("table_id"),
        extra={**dict(source.get("extra") or {}), "section_id": meta.get("section_id")},
    )


def _chunk_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in meta.items()
        if key not in {"source"} and not key.startswith("_")
    }


def _chunk_id(meta: dict[str, Any], haystack_id: str, index: int) -> str:
    raw = "|".join(
        [
            str(meta.get("company_id", "")),
            str(meta.get("document_id", "")),
            str(meta.get("section_id", "")),
            str(meta.get("split_id", index)),
            str(haystack_id),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


__all__ = ["HaystackChunkAdapter", "HaystackChunkingConfig"]
