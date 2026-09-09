#!/usr/bin/env python3
"""Collect central equations for papers that never had the step run.

Requires KIMI_API_KEY for the selector. Safe to re-run: only papers without an
equation_sources row are processed unless --arxiv-id forces one.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from radar.arxiv_html import fetch_arxiv_html
from radar.config import (load_database_path, load_formula_model,
                          load_formula_thinking, load_kimi_base_url,
                          load_kimi_request_interval)
from radar.equations import collect_equations
from radar.judge import KimiFormulaSelector
from radar.store import Store


def main(argv: list[str] | None = None, *, selector=None, fetch_html=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=load_database_path())
    parser.add_argument("--arxiv-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--today", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args(argv)

    store = Store(args.db)
    try:
        store.init_schema()
        if args.arxiv_id:
            papers = [p for p in (store.get_paper(i) for i in args.arxiv_id) if p]
        else:
            papers = store.papers_without_equations()[:args.limit]
        if not papers:
            print("nothing to backfill")
            return 0
        if selector is None:
            api_key = os.environ.get("KIMI_API_KEY", "")
            if not api_key:
                print("KIMI_API_KEY is required for the selector", file=sys.stderr)
                return 2
            selector = KimiFormulaSelector(
                api_key, load_formula_model(), thinking=load_formula_thinking(),
                request_interval=load_kimi_request_interval(),
                base_url=load_kimi_base_url())
        outcome = collect_equations(
            store, papers,
            fetch_html=fetch_html or (lambda i: fetch_arxiv_html(i, get=httpx.get)),
            selector=selector, today=args.today, selector_model=load_formula_model())
        print(f"backfilled {len(papers)} papers: {dict(outcome)}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
