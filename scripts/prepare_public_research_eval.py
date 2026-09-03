#!/usr/bin/env python3
"""Prepare the 20-paper evaluation database without network or model calls."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar.public_research_eval import load_evaluation_manifest
from radar.research_corpus import prepare_evaluation_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("eval/public-research-corpus.json"),
    )
    parser.add_argument("--source-db", type=Path, default=Path("data/radar.db"))
    parser.add_argument(
        "--checkpoint", type=Path,
        default=Path("eval/public-research-judgments.jsonl"),
    )
    parser.add_argument(
        "--output-db", type=Path,
        default=Path("data/public-research-eval.db"),
    )
    parser.add_argument("--as-of", default="2026-09-03")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    result = prepare_evaluation_database(
        load_evaluation_manifest(args.manifest),
        source_database=args.source_db,
        checkpoint=args.checkpoint,
        destination=args.output_db,
        as_of=args.as_of,
        replace=args.force,
    )
    print(f"prepared {result.papers} papers: {result.destination}")
    print(f"judgments: {result.provider}/{result.model}")
    print("network calls: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
