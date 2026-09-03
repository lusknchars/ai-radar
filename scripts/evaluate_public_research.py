#!/usr/bin/env python3
"""Evaluate published research pages against the fixed 20-paper corpus."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar.public_research_eval import (
    evaluate_public_research,
    evaluation_json,
    load_evaluation_manifest,
    research_progress_passed,
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
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help=(
            "exit successfully when only unfinished report count and a missing "
            "reader study keep the release gate closed"
        ),
    )
    args = parser.parse_args(argv)

    manifest = load_evaluation_manifest(args.manifest)
    evaluation = evaluate_public_research(
        manifest, args.site_dir,
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
    if evaluation.gate_passed:
        return 0
    if args.allow_incomplete and research_progress_passed(
        evaluation, minimum_reports=manifest.minimum_reports,
    ):
        print(
            "Progress check: PASS. The release gate remains closed until the "
            "corpus and reader study are complete."
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
