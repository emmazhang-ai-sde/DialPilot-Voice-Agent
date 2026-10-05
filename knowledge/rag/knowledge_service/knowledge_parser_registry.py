"""Parser provider selection for Knowledge Service ingestion."""

from __future__ import annotations

from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig
from rag.knowledge_service.knowledge_document_backends import LocalTextDocumentBackend
from rag.knowledge_service.knowledge_document_backends import parser_backends
from rag.knowledge_service.knowledge_interfaces import ParseRequest, ParserBackend
from rag.knowledge_service.knowledge_models import NormalizedDocument


class ParserRegistry:
    """Selects configured parsers while preserving a stable parse contract."""

    def __init__(self, backends: list[ParserBackend], provider_order: tuple[str, ...]):
        self._backends = {backend.provider_name: backend for backend in backends}
        self._provider_order = provider_order

    @classmethod
    def from_config(cls, config: KnowledgeProviderConfig) -> "ParserRegistry":
        return cls(
            list(parser_backends(config)),
            provider_order=(*config.provider_order("document"), "local_text"),
        )

    def parse(self, request: ParseRequest) -> NormalizedDocument:
        local_backend = self._backends.get("local_text")
        if (
            isinstance(local_backend, LocalTextDocumentBackend)
            and request.file_path.lower().endswith(tuple(local_backend.supported_suffixes))
        ):
            return local_backend.parse(request)

        errors: list[str] = []
        for provider_name in self._provider_order:
            backend = self._backends.get(provider_name)
            if backend is None:
                errors.append(f"{provider_name}: backend is not registered")
                continue
            try:
                return backend.parse(request)
            except (NotImplementedError, RuntimeError, ValueError) as exc:
                errors.append(f"{provider_name}: {exc}")
        raise RuntimeError("no parser backend could parse document; " + "; ".join(errors))


__all__ = ["ParserRegistry"]
