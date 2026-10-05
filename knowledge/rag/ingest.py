#!/usr/bin/env python3
"""KnowledgeService ingestion CLI for local files or configured KB profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.knowledge_service import KnowledgeService, ParseRequest


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    service = KnowledgeService.from_env(str(project_root))
    requests = build_requests(args, project_root)
    results = [service.ingest(request) for request in requests]
    print(
        json.dumps(
            {
                "documents": len(results),
                "chunks": sum(result.chunk_count for result in results),
                "vector_upsert_count": sum(result.vector_upsert_count for result in results),
                "embedding_provider": results[0].embedding_provider if results else None,
                "vector_provider": results[0].vector_provider if results else None,
                "document_ids": [result.document.document_id for result in results],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def build_requests(args: argparse.Namespace, project_root: Path) -> list[ParseRequest]:
    if args.profile:
        return profile_requests(args.profile, project_root)

    if not args.file:
        raise SystemExit("Either --profile or --file is required")
    file_path = Path(args.file).resolve()
    company_id = args.company_id or file_path.parent.name
    document_id = args.document_id or file_path.stem
    return [
        ParseRequest(
            file_path=str(file_path),
            company_id=company_id,
            document_id=document_id,
            title=args.title or file_path.stem.replace("-", " ").title(),
            source_type=args.source_type or file_path.suffix.lstrip(".") or "file",
            source_uri=args.source_uri,
            metadata={"knowledge_base_id": args.knowledge_base_id or company_id},
        )
    ]


def profile_requests(profile_id: str, project_root: Path) -> list[ParseRequest]:
    knowledge_base_root = project_root / "examples" / "knowledge-bases"
    profiles_path = knowledge_base_root / "knowledge_profiles.json"
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    profile = profiles.get(profile_id)
    if profile is None:
        raise SystemExit(f"Unknown knowledge profile: {profile_id}")
    company_id = str(profile["company_key"])
    requests: list[ParseRequest] = []
    for relative_path in profile.get("source_files") or []:
        path = knowledge_base_root / relative_path
        if not path.exists():
            continue
        requests.append(
            ParseRequest(
                file_path=str(path),
                company_id=company_id,
                document_id=f"{company_id}:{Path(relative_path).stem}",
                title=Path(relative_path).stem.replace("-", " ").title(),
                source_type=path.suffix.lstrip(".") or "file",
                source_uri=str(path),
                metadata={
                    "knowledge_base_id": profile_id,
                    "document_status": profile.get("status", "active"),
                },
            )
        )
    return requests


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="knowledge profile id from knowledge_profiles.json")
    parser.add_argument("--file", help="single file to ingest")
    parser.add_argument("--company-id")
    parser.add_argument("--document-id")
    parser.add_argument("--title")
    parser.add_argument("--source-type")
    parser.add_argument("--source-uri")
    parser.add_argument("--knowledge-base-id")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
