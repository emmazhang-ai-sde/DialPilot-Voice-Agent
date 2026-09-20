"""Document parser backends for the Knowledge Service boundary."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from rag.knowledge_service.knowledge_interfaces import ParseRequest
from rag.knowledge_service.knowledge_models import NormalizedDocument, Section


class LocalTextDocumentBackend:
    """Deterministic parser for local Markdown and plain-text files."""

    provider_name = "local_text"
    supported_suffixes = {".md", ".markdown", ".txt"}

    def parse(self, request: ParseRequest) -> NormalizedDocument:
        path = Path(request.file_path)
        if path.suffix.lower() not in self.supported_suffixes:
            raise ValueError(f"{self.provider_name} cannot parse {path.suffix or 'unknown'} files")
        text = path.read_text(encoding="utf-8")
        sections = _parse_markdown_sections(
            text,
            document_id=request.document_id,
            default_heading=request.title,
        )
        return NormalizedDocument(
            document_id=request.document_id,
            company_id=request.company_id,
            title=request.title,
            source_type=request.source_type,
            source_uri=request.source_uri or str(path),
            sections=tuple(sections),
            metadata={**request.metadata, "parser_provider": self.provider_name},
        )


class DoclingDocumentBackend:
    """Docling-backed parser placeholder with deterministic text fallback.

    Docling is the planned local fallback for richer document types. The current
    code keeps the provider slot explicit while still allowing Markdown/TXT
    tests and local development to run without the optional Docling dependency.
    """

    provider_name = "docling"

    def __init__(self, fallback: LocalTextDocumentBackend | None = None):
        self._fallback = fallback or LocalTextDocumentBackend()

    def parse(self, request: ParseRequest) -> NormalizedDocument:
        path = Path(request.file_path)
        if path.suffix.lower() in self._fallback.supported_suffixes:
            document = self._fallback.parse(request)
            return _with_parser_provider(document, self.provider_name)
        try:
            import docling  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Docling parsing requires the optional docling package for non-text files"
            ) from exc
        raise NotImplementedError("Docling parser integration is not wired yet")


class AzureDocumentIntelligenceBackend:
    """Azure Document Intelligence parser placeholder.

    The service boundary can select this backend from config now. Full PDF/DOCX
    extraction should be added behind this class without changing callers.
    """

    provider_name = "azure_document_intelligence"

    def __init__(self, fallback: LocalTextDocumentBackend | None = None):
        self._fallback = fallback or LocalTextDocumentBackend()

    def parse(self, request: ParseRequest) -> NormalizedDocument:
        path = Path(request.file_path)
        if path.suffix.lower() in self._fallback.supported_suffixes:
            document = self._fallback.parse(request)
            return _with_parser_provider(document, self.provider_name)
        raise NotImplementedError(
            "Azure Document Intelligence parsing is reserved for the managed parser integration"
        )


def _parse_markdown_sections(
    text: str,
    *,
    document_id: str,
    default_heading: str,
) -> list[Section]:
    blocks: list[Section] = []
    heading_stack: list[tuple[int, str]] = []
    current_heading = default_heading
    current_level = 1
    current_body: list[str] = []
    current_path: tuple[str, ...] = (default_heading,)
    index = 0

    def flush() -> None:
        nonlocal index
        body = "\n".join(current_body).strip()
        if not body:
            return
        blocks.append(
            Section(
                section_id=f"{document_id}:section:{index}",
                heading=current_heading,
                text=body,
                level=current_level,
                path=current_path,
            )
        )
        index += 1

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            flush()
            current_body = []
            current_level = len(match.group(1))
            current_heading = match.group(2).strip()
            heading_stack = [
                item for item in heading_stack if item[0] < current_level
            ]
            heading_stack.append((current_level, current_heading))
            current_path = tuple(heading for _, heading in heading_stack)
            continue
        current_body.append(line)

    flush()
    if blocks:
        return blocks

    stripped = text.strip()
    if not stripped:
        raise ValueError("document text is empty")
    return [
        Section(
            section_id=f"{document_id}:section:0",
            heading=default_heading,
            text=stripped,
            level=1,
            path=(default_heading,),
        )
    ]


def _with_parser_provider(document: NormalizedDocument, provider_name: str) -> NormalizedDocument:
    return NormalizedDocument(
        document_id=document.document_id,
        company_id=document.company_id,
        title=document.title,
        source_type=document.source_type,
        source_uri=document.source_uri,
        sections=document.sections,
        metadata={**document.metadata, "parser_provider": provider_name},
        version=document.version,
    )


def parser_backends() -> Iterable[object]:
    local = LocalTextDocumentBackend()
    return (
        AzureDocumentIntelligenceBackend(fallback=local),
        DoclingDocumentBackend(fallback=local),
        local,
    )


__all__ = [
    "AzureDocumentIntelligenceBackend",
    "DoclingDocumentBackend",
    "LocalTextDocumentBackend",
    "parser_backends",
]
