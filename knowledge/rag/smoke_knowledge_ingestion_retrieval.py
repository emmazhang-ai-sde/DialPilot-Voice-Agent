#!/usr/bin/env python3
"""Explicit smoke test for KnowledgeService ingest -> Qdrant -> retrieve."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from rag.knowledge_service import KnowledgeRetrievalOptions, KnowledgeService, ParseRequest
from rag.knowledge_service.knowledge_config import KnowledgeProviderConfig


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    config = KnowledgeProviderConfig.from_project_env(project_root)
    enforce_qdrant_smoke_guard(
        qdrant_url=config.qdrant_url,
        allow_cloud=args.allow_cloud,
        env=os.environ,
    )

    service = KnowledgeService.from_env(str(project_root))
    ingestion = service.ingest(
        ParseRequest(
            file_path=str(Path(args.file).resolve()),
            company_id=args.company_id,
            document_id=args.document_id,
            title=args.title,
            source_type=args.source_type,
            source_uri=args.source_uri,
            metadata={
                "knowledge_base_id": args.knowledge_base_id,
                "document_status": args.document_status,
                "allowed_agent_ids": args.allowed_agent_ids,
            },
        )
    )
    retrieval = service.retrieve(
        company_id=args.company_id,
        query=args.query,
        options=KnowledgeRetrievalOptions(top_k=args.top_k),
    )
    print(
        json.dumps(
            {
                "document_id": ingestion.document.document_id,
                "chunks": ingestion.chunk_count,
                "vector_provider": ingestion.vector_provider,
                "vector_upsert_count": ingestion.vector_upsert_count,
                "has_evidence": retrieval.has_evidence,
                "retrieved_chunks": len(retrieval.rows),
                "citations": [
                    {
                        "chunk_id": row.get("chunk_id"),
                        "document_name": row.get("document_name"),
                        "section": row.get("section"),
                        "page": row.get("page"),
                    }
                    for row in retrieval.rows
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-type", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--knowledge-base-id", default="")
    parser.add_argument("--document-status", default="active")
    parser.add_argument("--allowed-agent-ids", nargs="*", default=[])
    parser.add_argument("--source-uri")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--allow-cloud", action="store_true")
    return parser.parse_args(argv)


def enforce_qdrant_smoke_guard(
    *,
    qdrant_url: str,
    allow_cloud: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    env = env or os.environ
    if not qdrant_url:
        raise SystemExit("QDRANT_URL is required for the Qdrant smoke script")
    if is_local_qdrant_url(qdrant_url):
        return
    if allow_cloud or env.get("RUN_QDRANT_CLOUD_SMOKE") == "1":
        return
    raise SystemExit(
        "Refusing to run against non-local Qdrant without RUN_QDRANT_CLOUD_SMOKE=1 or --allow-cloud"
    )


def is_local_qdrant_url(url: str) -> bool:
    normalized = url.lower().strip()
    return (
        "localhost" in normalized
        or "127.0.0.1" in normalized
        or normalized.startswith("http://0.0.0.0")
    )


if __name__ == "__main__":
    raise SystemExit(main())
