#!/usr/bin/env python3
"""Rebuild and verify the no-cost 20-paper public research baseline."""
from __future__ import annotations

import argparse
import tempfile
from datetime import date
from pathlib import Path

from radar.public_research_eval import (
    evaluate_public_research,
    load_evaluation_manifest,
    render_evaluation_markdown,
)
from radar.publish import publish_site
from radar.research_corpus import prepare_evaluation_database
from radar.store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("eval/public-research-corpus.json"),
    )
    parser.add_argument(
        "--judgments", type=Path,
        default=Path("eval/public-research-judgments.jsonl"),
    )
    parser.add_argument("--source-db", type=Path, default=Path("data/radar.db"))
    parser.add_argument("--as-of", default="2026-09-03")
    args = parser.parse_args(argv)

    manifest = load_evaluation_manifest(args.manifest)
    with tempfile.TemporaryDirectory(prefix="ai-radar-baseline-") as directory:
        root = Path(directory)
        database = root / "evaluation.db"
        site = root / "site"
        prepare_evaluation_database(
            manifest,
            source_database=args.source_db,
            checkpoint=args.judgments,
            destination=database,
            as_of=args.as_of,
        )
        store = Store(database)
        try:
            store.init_schema()
            publish_site(
                store,
                site,
                date.fromisoformat(args.as_of),
                reports_root=root / "reports",
            )
        finally:
            store.close()
        evaluation = evaluate_public_research(manifest, site)

    expected_failures = {
        f"only 0 of {manifest.minimum_reports} required reports exist",
        "reader study results are missing",
    }
    problems = []
    if evaluation.pages_valid != len(manifest.cases):
        problems.append(
            f"only {evaluation.pages_valid}/{len(manifest.cases)} pages are valid"
        )
    if evaluation.reports_evaluated != 0:
        problems.append("the no-cost baseline unexpectedly contains reports")
    if evaluation.evaluated_exposures != 0:
        problems.append("indexed pages unexpectedly claim evaluated exposures")
    if evaluation.exposures_total != len(manifest.cases) * 8:
        problems.append("the exposure map is incomplete")
    if any(
        case.editorial_status != "indexed" for case in evaluation.cases
    ):
        problems.append("the no-cost baseline promoted an indexed paper")
    if set(evaluation.failures) != expected_failures:
        problems.append(
            "baseline failures changed: " + ", ".join(evaluation.failures)
        )

    print(render_evaluation_markdown(evaluation), end="")
    if problems:
        print("Baseline verification: FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("Baseline verification: PASS")
    print("The release gate remains closed until reports and reader data exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
