#!/usr/bin/env python3
"""Publish the current research corpus without network or model calls."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from radar.publish import publish_site
from radar.store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/public-research-eval.db"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=datetime.now(timezone.utc).date(),
        help="publication date in YYYY-MM-DD format",
    )
    args = parser.parse_args(argv)

    store = Store(args.db)
    try:
        store.init_schema()
        publish_site(
            store,
            args.site_dir,
            args.as_of,
            reports_root=args.reports_dir,
        )
    finally:
        store.close()
    print(f"published research site: {args.site_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
