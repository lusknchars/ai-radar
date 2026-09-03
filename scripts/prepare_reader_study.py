#!/usr/bin/env python3
"""Create a balanced five-reader study sheet from the evaluation corpus."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar.public_research_eval import load_evaluation_manifest
from radar.reader_study import (
    build_reader_study_assignments,
    render_reader_study_csv,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("eval/public-research-corpus.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("eval/reader-study.csv"),
    )
    parser.add_argument("--participants", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if args.output.exists() and not args.force:
        raise SystemExit(
            f"study sheet already exists: {args.output}; use --force to replace it"
        )
    assignments = build_reader_study_assignments(
        load_evaluation_manifest(args.manifest),
        participant_count=args.participants,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_reader_study_csv(assignments), encoding="utf-8",
    )
    print(
        f"prepared {len(assignments)} observations for "
        f"{args.participants} readers: {args.output}"
    )
    print("Fill every result column, then run evaluate_public_research.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
