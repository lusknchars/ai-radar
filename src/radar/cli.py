"""Ponto de entrada. Monta os adaptadores reais e chama o pipeline."""
from __future__ import annotations

import argparse
import os
import time
from datetime import date, timezone, datetime
from pathlib import Path

import anthropic
import httpx

from .arxiv import USER_AGENT, ArxivClient
from .config import DEFAULT_SCOPE, load_model, load_thresholds
from .github import GitHubClient
from .judge import Judge, collect_batch_results, submit_batch
from .pipeline import run_day
from .store import Store
from .telegram import send

GITHUB_SLEEP_SECONDS = 2.5   # 10 req/min sem token; com token da folga


def _arxiv_fetch(url: str) -> str:
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    r.raise_for_status()
    return r.text


def _github_fetch(url: str) -> dict:
    headers = {"User-Agent": "ai-radar/0.1", "Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.get(url, headers=headers, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _telegram_post(url: str, json: dict) -> dict:
    r = httpx.post(url, json=json, timeout=30.0)
    r.raise_for_status()
    return r.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar")
    parser.add_argument("--db", type=Path, default=Path("data/radar.db"))
    parser.add_argument("--out", type=Path, default=Path("radar"))
    parser.add_argument("--dry-run", action="store_true",
                        help="nao envia o push nem grava entregas de telegram")
    args = parser.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    store = Store(args.db)
    store.init_schema()

    arxiv = ArxivClient(fetch=_arxiv_fetch)
    github = GitHubClient(fetch=_github_fetch)
    client = anthropic.Anthropic()
    model = load_model()

    def fetch_signal(paper, day):
        time.sleep(GITHUB_SLEEP_SECONDS)
        return github.signal_with_repos(paper, today=day)

    def judge_all(papers):
        if not papers:
            return {}
        batch = submit_batch(client, papers, model)
        while True:
            status = client.messages.batches.retrieve(batch.id).processing_status
            if status == "ended":
                break
            time.sleep(30)
        return collect_batch_results(client.messages.batches.results(batch.id))

    result = run_day(
        store=store, scope=DEFAULT_SCOPE, thresholds=load_thresholds(), today=today,
        model=model,
        fetch_papers=arxiv.recent, fetch_signal=fetch_signal, judge_all=judge_all,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{today.isoformat()}.md").write_text(result.markdown, encoding="utf-8")
    print(f"radar: {len(result.radar)} · feed: {len(result.feed)} · cortes: {result.cuts}")

    if not args.dry_run:
        sent = send(result.push,
                    token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                    chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
                    post=_telegram_post)
        print(f"push enviado: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
