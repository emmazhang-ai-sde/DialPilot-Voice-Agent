"""Shared data models for the company Knowledge Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clean(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(frozen=True)
class SourceMetadata:
    document_id: str
    document_name: str
    source_type: str
    source_uri: str | None = None
    page: int | None = None
    section_path: tuple[str, ...] = ()
    table_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_id", _clean(self.document_id, "document_id"))
        object.__setattr__(self, "document_name", _clean(self.document_name, "document_name"))
        object.__setattr__(self, "source_type", _clean(self.source_type, "source_type").lower())
        if self.page is not None and self.page < 1:
            raise ValueError("page must be positive")
        object.__setattr__(self, "section_path", tuple(str(part).strip() for part in self.section_path if str(part).strip()))
        object.__setattr__(self, "extra", _metadata(self.extra))

    @property
    def section(self) -> str:
        return " > ".join(self.section_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "page": self.page,
            "section_path": list(self.section_path),
            "section": self.section,
            "table_id": self.table_id,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True)
class Section:
    section_id: str
    heading: str
    text: str = ""
    level: int = 1
    page_start: int | None = None
    page_end: int | None = None
    path: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_id", _clean(self.section_id, "section_id"))
        object.__setattr__(self, "heading", str(self.heading).strip())
        object.__setattr__(self, "text", str(self.text).strip())
        if self.level < 1:
            raise ValueError("level must be positive")
        if self.page_start is not None and self.page_start < 1:
            raise ValueError("page_start must be positive")
        if self.page_end is not None and self.page_end < 1:
            raise ValueError("page_end must be positive")
        if self.page_start and self.page_end and self.page_end < self.page_start:
            raise ValueError("page_end cannot be before page_start")
        object.__setattr__(self, "path", tuple(str(part).strip() for part in self.path if str(part).strip()))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def section_path(self) -> tuple[str, ...]:
        return self.path or ((self.heading,) if self.heading else ())

    def source_metadata(self, document: "NormalizedDocument") -> SourceMetadata:
        return SourceMetadata(
            document_id=document.document_id,
            document_name=document.title,
            source_type=document.source_type,
            source_uri=document.source_uri,
            page=self.page_start,
            section_path=self.section_path,
            extra={"section_id": self.section_id, **self.metadata},
        )


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    company_id: str
    document_id: str
    text: str
    source: SourceMetadata
    token_count: int | None = None
    embedding_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", _clean(self.chunk_id, "chunk_id"))
        object.__setattr__(self, "company_id", _clean(self.company_id, "company_id"))
        object.__setattr__(self, "document_id", _clean(self.document_id, "document_id"))
        object.__setattr__(self, "text", _clean(self.text, "text"))
        if self.source.document_id != self.document_id:
            raise ValueError("source.document_id must match document_id")
        if self.token_count is not None and self.token_count < 0:
            raise ValueError("token_count cannot be negative")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def content(self) -> str:
        return self.text

    def to_retrieval_dict(self) -> dict[str, Any]:
        row = {
            "id": self.chunk_id,
            "chunk_id": self.chunk_id,
            "company_id": self.company_id,
            "document_id": self.document_id,
            "source_file": self.source.document_name,
            "document_name": self.source.document_name,
            "source_type": self.source.source_type,
            "source_uri": self.source.source_uri,
            "page": self.source.page,
            "section": self.source.section,
            "content": self.text,
            "metadata": {**self.metadata, "source": self.source.to_dict()},
        }
        if self.score is not None:
            row["score"] = self.score
        return row


@dataclass(frozen=True)
class NormalizedDocument:
    document_id: str
    company_id: str
    title: str
    source_type: str
    source_uri: str | None = None
    sections: tuple[Section, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_id", _clean(self.document_id, "document_id"))
        object.__setattr__(self, "company_id", _clean(self.company_id, "company_id"))
        object.__setattr__(self, "title", _clean(self.title, "title"))
        object.__setattr__(self, "source_type", _clean(self.source_type, "source_type").lower())
        object.__setattr__(self, "sections", tuple(self.sections))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def text(self) -> str:
        return "\n\n".join(section.text for section in self.sections if section.text)

    def source_metadata(self, *, section: Section | None = None) -> SourceMetadata:
        if section is not None:
            return section.source_metadata(self)
        return SourceMetadata(
            document_id=self.document_id,
            document_name=self.title,
            source_type=self.source_type,
            source_uri=self.source_uri,
            extra=dict(self.metadata),
        )

    @classmethod
    def from_text(
        cls,
        *,
        document_id: str,
        company_id: str,
        title: str,
        source_type: str,
        text: str,
        source_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "NormalizedDocument":
        return cls(
            document_id=document_id,
            company_id=company_id,
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            metadata=_metadata(metadata),
            sections=(
                Section(
                    section_id=f"{document_id}:section:0",
                    heading=title,
                    text=text,
                    path=(title,),
                ),
            ),
        )


__all__ = ["Chunk", "NormalizedDocument", "Section", "SourceMetadata"]
