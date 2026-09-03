#!/usr/bin/env python3
"""Compare PDF adapters against local page-grounded paper fixtures."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from radar.extraction_eval import (ExpectedExcerpt, ExtractionFixture,
                                   evaluate_extractor)
from radar.fulltext import DoclingPdfExtractor, PyPdfExtractor


def _load_manifest(path: Path) -> tuple[ExtractionFixture, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        ExtractionFixture(
            arxiv_id=item["arxiv_id"],
            expected_pages=item["expected_pages"],
            required_excerpts=tuple(
                ExpectedExcerpt(page=excerpt["page"], text=excerpt["text"])
                for excerpt in item.get("required_excerpts", [])
            ),
        )
        for item in payload
    )


def _summary(results) -> dict:
    by_extractor = {}
    for name in sorted({item.extractor for item in results}):
        selected = [item for item in results if item.extractor == name]
        found = sum(item.excerpts_found for item in selected)
        total = sum(item.excerpts_total for item in selected)
        durations = sorted(item.duration_ms for item in selected)
        percentile_index = max(0, (95 * len(durations) + 99) // 100 - 1)
        by_extractor[name] = {
            "papers": len(selected),
            "successful": sum(item.status == "ok" for item in selected),
            "page_count_matches": sum(item.page_count_matches for item in selected),
            "excerpt_recall": found / total if total else 1.0,
            "p95_duration_ms": durations[percentile_index] if durations else None,
        }
    return by_extractor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--extractor", action="append", choices=("pypdf", "docling"),
        help="adapter to run; repeat to compare, defaults to both",
    )
    args = parser.parse_args(argv)

    factories = {
        "pypdf": PyPdfExtractor,
        "docling": DoclingPdfExtractor,
    }
    names = args.extractor or ["pypdf", "docling"]
    fixtures = _load_manifest(args.manifest)
    results = []
    for fixture in fixtures:
        pdf_path = args.pdf_dir / f"{fixture.arxiv_id}.pdf"
        if not pdf_path.is_file():
            raise SystemExit(f"missing fixture PDF: {pdf_path}")
        content = pdf_path.read_bytes()
        for name in names:
            results.append(evaluate_extractor(
                fixture, content, factories[name]()))

    payload = {
        "schema_version": 1,
        "results": [
            {**asdict(item),
             "page_count_matches": item.page_count_matches,
             "excerpt_recall": item.excerpt_recall}
            for item in results
        ],
        "summary": _summary(results),
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if any(item.status != "ok" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
