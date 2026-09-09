#!/usr/bin/env python3
"""Rewrite Portuguese paper briefs in English, keeping every classification.

Requires KIMI_API_KEY unless --dry-run. Idempotent: briefs that already read
as English are skipped, so the script can run again after a partial failure.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from radar.briefs_english import rewrite_portuguese_briefs
from radar.config import (load_database_path, load_kimi_base_url,
                          load_kimi_request_interval, load_model)
from radar.judge import KimiJudge
from radar.publish import publish_site
from radar.store import Store


def main(argv: list[str] | None = None, *, judge=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=load_database_path())
    parser.add_argument("--checkpoint", type=Path,
                        default=Path("eval/public-research-judgments.jsonl"))
    parser.add_argument("--arxiv-id", action="append", default=[])
    parser.add_argument("--today", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--dry-run", action="store_true",
                        help="list the briefs that would be rewritten; no model call")
    parser.add_argument("--publish", action="store_true",
                        help="regenerate site/ from the database afterwards")
    args = parser.parse_args(argv)

    model = load_model()
    if judge is None and not args.dry_run:
        api_key = os.environ.get("KIMI_API_KEY", "")
        if not api_key:
            print("KIMI_API_KEY is required unless --dry-run", file=sys.stderr)
            return 2
        judge = KimiJudge(
            api_key, model, request_interval=load_kimi_request_interval(),
            base_url=load_kimi_base_url())

    store = Store(args.db)
    try:
        store.init_schema()
        outcome = rewrite_portuguese_briefs(
            store, judge=judge, today=args.today, model=model,
            checkpoint=args.checkpoint, arxiv_ids=args.arxiv_id or None,
            dry_run=args.dry_run,
            wait=getattr(judge, "wait_between_requests", lambda: None),
        )
        print(f"briefs: {dict(outcome)}")
        if args.publish and not args.dry_run:
            publish_site(store, Path("site"), date.fromisoformat(args.today))
            print("published site/")
    finally:
        store.close()
        if judge is not None and hasattr(judge, "close"):
            judge.close()
    return 1 if outcome.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
