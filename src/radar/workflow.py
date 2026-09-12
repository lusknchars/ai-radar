"""GitHub Actions entrypoint with a no-cost publication fallback."""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path

from .cli import main as run_radar
from .briefs_english import apply_english_checkpoint
from .config import load_database_path, load_llm_provider
from .public_research_eval import load_evaluation_manifest
from .publish import publish_site
from .research_corpus import prepare_evaluation_database
from .store import Store

EVALUATION_MANIFEST = Path("eval/public-research-corpus.json")
EVALUATION_JUDGMENTS = Path("eval/public-research-judgments.jsonl")
HISTORICAL_DATABASE = Path("data/radar.db")


def actions_main(argv: list[str] | None = None) -> int:
    """Let Actions publish useful partial collections without hiding failures."""
    output = os.environ.get('GITHUB_OUTPUT')
    if not output or (argv and '--dry-run' in argv):
        return main(argv)
    status_path = Path('site/collection.json')
    # The tracked publication may describe a previous run on the same day.
    # Only a status document written by this invocation can unlock publishing.
    status_path.unlink(missing_ok=True)
    result = main(argv)
    outcome = 'unknown'
    if result in (0, 1) and status_path.exists():
        try:
            outcome = json.loads(status_path.read_text())['outcome']
        except (ValueError, KeyError, TypeError):
            pass
    ready = outcome in {'success', 'partial', 'unconfigured'}
    with Path(output).open('a') as stream:
        stream.write(f'publication_ready={str(ready).lower()}\n')
        stream.write(f'collection_outcome={outcome if ready else "unknown"}\n')
    return result


def _credential_name(provider: str) -> str:
    return "KIMI_API_KEY" if provider == "kimi" else "ANTHROPIC_API_KEY"


def main(argv: list[str] | None = None) -> int:
    """Run the paid radar when configured, otherwise publish the fixed corpus."""
    provider = load_llm_provider()
    credential = _credential_name(provider)
    mode = os.environ.get("RADAR_COLLECTION_MODE", "auto")
    if mode not in {"auto", "live", "sample"}:
        raise ValueError("RADAR_COLLECTION_MODE must be auto, live, or sample")
    if mode != "sample" and os.environ.get(credential):
        return run_radar(argv)
    if mode == "live":
        raise ValueError(f"Live collection requires {credential}; stored research was not relabeled.")
    if argv and "--dry-run" in argv:
        print("No live collection configured; dry-run did not change any files.")
        return 0

    database = load_database_path()
    today = datetime.now(timezone.utc).date()
    if not database.exists():
        prepare_evaluation_database(
            load_evaluation_manifest(EVALUATION_MANIFEST),
            source_database=HISTORICAL_DATABASE,
            checkpoint=EVALUATION_JUDGMENTS,
            destination=database,
            as_of=today.isoformat(),
        )
    store = Store(database)
    try:
        store.init_schema()
        if EVALUATION_JUDGMENTS.exists():
            apply_english_checkpoint(store, EVALUATION_JUDGMENTS, today=today.isoformat())
        run_id = store.begin_collection(today.isoformat(), mode="sample")
        store.finish_collection(run_id, "unconfigured")
        publish_site(store, Path("site"), today)
    finally:
        store.close()
    print(
        f"{credential} is not configured or sample mode was selected. "
        "Republished stored research without network requests. "
        "No fresh collection took place."
    )
    return 1 if mode == "live" else 0
