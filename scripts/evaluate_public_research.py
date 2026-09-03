#!/usr/bin/env python3
"""Evaluate published research pages against the fixed 20-paper corpus."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar.public_research_eval import (
    evaluate_public_research,
    evaluation_json,
    load_evaluation_manifest,
    render_evaluation_markdown,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("eval/public-research-corpus.json"),
    )
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--reader-study", type=Path, default=Path("eval/reader-study.csv"),
    )
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    evaluation = evaluate_public_research(
        load_evaluation_manifest(args.manifest), args.site_dir,
        reports_root=args.reports_dir,
        reader_study_path=args.reader_study,
    )
    rendered = render_evaluation_markdown(evaluation)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(rendered, encoding="utf-8")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(evaluation_json(evaluation), encoding="utf-8")
    print(rendered, end="")
    return 0 if evaluation.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
