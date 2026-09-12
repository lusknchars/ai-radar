#!/usr/bin/env python3
"""Build the public archive for a root domain, without collection or model calls."""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from radar.config import DEFAULT_REPOSITORY, PublicConfig
from radar.community import load_community_config
from radar.publish import publish_site
from radar.store import Store

ROOT = Path(__file__).resolve().parents[1]


def production_url() -> str:
    value = os.environ.get("RADAR_SITE_URL", "").strip()
    if not value:
        host = (os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
                or os.environ.get("VERCEL_URL", "")).strip()
        value = f"https://{host}" if host else ""
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("Set RADAR_SITE_URL to the site's root URL, e.g. https://radar.example.com")
    return value.rstrip("/")


def build(*, database: Path, output: Path, reports: Path, as_of: date) -> None:
    config = PublicConfig(
        repository=os.environ.get("RADAR_REPOSITORY", DEFAULT_REPOSITORY),
        base_path="",
        site_url=production_url(),
        subscribe_url=os.environ.get("RADAR_SUBSCRIBE_URL", ""),
        community=load_community_config(os.environ.get("RADAR_REPOSITORY", DEFAULT_REPOSITORY)),
    )
    if not database.is_file():
        raise FileNotFoundError(f"Publication database is missing: {database}")
    # Rendering may run schema migrations. Work on a snapshot and leave the
    # checked-in publication state untouched, including on failed builds.
    with tempfile.TemporaryDirectory(prefix="ai-radar-vercel-") as directory:
        snapshot = Path(directory) / "publication.db"
        source = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        store = Store(snapshot)
        generated = Path(directory) / "site"
        try:
            store.init_schema()
            publish_site(store, generated, as_of, reports_root=reports,
                         public_config=config)
        finally:
            store.close()
        if os.environ.get("VERCEL_ENV") == "preview":
            (generated / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
            for page in generated.rglob("*.html"):
                page.write_text(page.read_text(encoding="utf-8").replace(
                    "</head>", '<meta name="robots" content="noindex, nofollow"></head>', 1),
                    encoding="utf-8")
        # Only replace the dedicated build directory after rendering succeeds.
        if output.resolve() != (ROOT / "dist").resolve():
            raise ValueError("Build output must be the project's dist directory")
        if output.is_symlink():
            raise ValueError("Build output must not be a symbolic link")
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(generated, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat,
                        default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    build(database=ROOT / "data" / "radar-state.db", output=ROOT / "dist",
          reports=ROOT / "reports", as_of=args.as_of)
    print(f"Built static archive in {ROOT / 'dist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
