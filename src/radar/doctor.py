"""Fast, non-networking checks for a local AI Radar installation."""
from __future__ import annotations

import argparse
import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

from .config import (load_database_path, load_llm_provider,
                     load_pdf_extractor, load_public_config)
from .store import EXPECTED_JUDGMENT_COLUMNS, SchemaMigrationRequired, Store

REQUIRED_TABLES = {"papers", "signals", "repos", "judgments", "deliveries"}


def _inspect_database(path: Path) -> str | None:
    """Return a problem without creating or changing the SQLite database."""
    if not path.exists():
        return f"database does not exist: {path} (run with --init)"
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(judgments)")
        }
        if "judgments" in tables and columns != EXPECTED_JUDGMENT_COLUMNS:
            return (
                "database schema is incompatible; run "
                "python scripts/migrar_e_rejulgar.py for the historical archive"
            )
        missing = REQUIRED_TABLES - tables
        if missing:
            return f"database is missing tables: {', '.join(sorted(missing))}"
    finally:
        connection.close()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ai-radar doctor",
        description="Validate local configuration without making network calls.",
    )
    parser.add_argument(
        "--init", action="store_true",
        help="create the configured local database when it does not exist",
    )
    args = parser.parse_args(argv)
    errors: list[str] = []

    if sys.version_info < (3, 12):
        errors.append("Python 3.12 or newer is required")
    else:
        print(f"ok  Python {sys.version_info.major}.{sys.version_info.minor}")

    try:
        provider = load_llm_provider()
        key_name = "KIMI_API_KEY" if provider == "kimi" else "ANTHROPIC_API_KEY"
        if os.environ.get(key_name):
            print(f"ok  {provider} credentials are configured")
        else:
            errors.append(f"{key_name} is required for provider {provider}")
    except ValueError as exc:
        errors.append(str(exc))

    try:
        extractor = load_pdf_extractor()
        if extractor == "docling" and importlib.util.find_spec("docling") is None:
            errors.append(
                "RADAR_PDF_EXTRACTOR=docling requires pip install -e '.[documents]'"
            )
        else:
            print(f"ok  PDF extractor: {extractor}")
    except ValueError as exc:
        errors.append(str(exc))

    try:
        public = load_public_config()
        print(f"ok  public site: {public.site_url}")
    except ValueError as exc:
        errors.append(str(exc))

    database = load_database_path()
    if args.init:
        try:
            Store(database).init_schema()
            print(f"ok  initialized database: {database}")
        except (OSError, SchemaMigrationRequired, sqlite3.Error) as exc:
            errors.append(str(exc))
    else:
        try:
            problem = _inspect_database(database)
        except (OSError, sqlite3.Error) as exc:
            problem = f"cannot read database {database}: {exc}"
        if problem:
            errors.append(problem)
        else:
            print(f"ok  database: {database}")

    telegram_token = bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
    telegram_chat = bool(os.environ.get("TELEGRAM_CHAT_ID"))
    if telegram_token != telegram_chat:
        errors.append(
            "Telegram is partially configured; set both TELEGRAM_BOT_TOKEN "
            "and TELEGRAM_CHAT_ID, or neither"
        )
    elif telegram_token:
        print("ok  Telegram delivery is configured")
    else:
        print("ok  Telegram delivery is optional and disabled")

    if errors:
        for error in errors:
            print(f"error  {error}")
        return 1
    print("\nAI Radar is ready. No network requests were made.")
    return 0
