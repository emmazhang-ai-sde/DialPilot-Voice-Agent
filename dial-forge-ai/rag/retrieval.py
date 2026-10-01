#!/usr/bin/env python3
"""KnowledgeService-backed retrieval facade for runtime capability calls."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.knowledge_service import KnowledgeRetrievalOptions, KnowledgeService


DEFAULT_SCORE_FLOOR = None

_FOLLOWUP_OPENERS = (
    "and ",
    "what about",
    "how about",
    "how much",
    "how many",
    "what's that",
    "that one",
    "that ",
    "those ",
    "it ",
    "is it",
)

_DEFAULT_SERVICE: KnowledgeService | None = None


def should_retrieve(text: str) -> bool:
    """Cheap gate for utterances too small to be meaningful KB lookups."""

    return len(text.strip().split()) >= 2


def is_followup(text: str) -> bool:
    t = text.strip().lower()
    return len(t.split()) <= 4 or t.startswith(_FOLLOWUP_OPENERS)


def build_query(text: str, prev_user: str = "") -> str:
    """No-model follow-up rewrite used when a short question needs context."""

    if prev_user and is_followup(text):
        return f"{prev_user.strip()} {text.strip()}"
    return text.strip()


def match_detail(
    company_key: str,
    query: str,
    k: int = 3,
    *,
    distance_floor: float | None = None,
    score_floor: float | None = DEFAULT_SCORE_FLOOR,
    prefer_rpc: bool = True,
    service: KnowledgeService | None = None,
) -> list[dict[str, Any]]:
    """Return trusted detail chunks through the new KnowledgeService boundary.

    ``prefer_rpc`` is accepted for compatibility with the archived Supabase
    helper, but the active path now delegates retrieval to KnowledgeService.
    ``distance_floor`` is converted to a cosine-style score floor when present.
    """

    del prefer_rpc
    query = query.strip()
    if not should_retrieve(query):
        return []

    if score_floor is None and distance_floor is not None:
        score_floor = 1.0 - float(distance_floor)

    handler = service or default_service()
    return handler.retrieval_handler(
        company_key=company_key,
        query=query,
        k=k,
        score_floor=score_floor,
    )


def render(chunks: list[dict[str, Any]]) -> str:
    """Turn retrieved chunks into a prompt/tool-result evidence block."""

    return "\n\n".join(str(chunk.get("content") or "") for chunk in chunks if chunk.get("content"))


def default_service() -> KnowledgeService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = KnowledgeService.from_env(str(default_project_root()))
    return _DEFAULT_SERVICE


def default_project_root() -> Path:
    configured = os.environ.get("KNOWLEDGE_PROJECT_ROOT", "").strip()
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[1]


__all__ = [
    "DEFAULT_SCORE_FLOOR",
    "build_query",
    "default_project_root",
    "default_service",
    "is_followup",
    "match_detail",
    "render",
    "should_retrieve",
]
