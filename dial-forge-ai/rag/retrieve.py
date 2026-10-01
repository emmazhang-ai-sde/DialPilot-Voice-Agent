#!/usr/bin/env python3
"""KnowledgeService retrieval smoke CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag import retrieval


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    rows = retrieval.match_detail(
        company_key=args.company,
        query=args.query,
        k=args.top_k,
        score_floor=args.score_floor,
    )
    print(f"query:   {args.query!r}")
    print(f"company: {args.company}   chunks retrieved: {len(rows)}\n")
    if not rows:
        print("No evidence returned. Check that the configured vector store has been ingested.")
        return 1
    for index, row in enumerate(rows, 1):
        preview = str(row.get("content") or "").replace("\n", " ")[:160]
        score = row.get("score")
        score_text = f"  score={score:.3f}" if isinstance(score, float) else ""
        print(f"#{index}{score_text}  {row.get('source_file')} [{row.get('section')}]")
        print(f"     {preview}...\n")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company", help="company key, e.g. globifye")
    parser.add_argument("query", help="question to retrieve evidence for")
    parser.add_argument("-k", "--top-k", type=int, default=3)
    parser.add_argument("--score-floor", type=float)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
