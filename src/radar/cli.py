"""Ponto de entrada. Monta os adaptadores reais e chama o pipeline."""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx

from .arxiv import USER_AGENT, ArxivClient
from .config import DEFAULT_SCOPE, load_model, load_thresholds
from .github import GitHubClient
from .judge import collect_batch_results, submit_batch, wait_for_batch
from .pipeline import run_day
from .store import Store
from .telegram import send

# A busca do GitHub permite 10 req/min sem autenticacao e 30/min com token, e o
# README trata GH_TOKEN como opcional -- entao o intervalo tem que sair da
# presenca do segredo, e nao de um numero fixo. Um valor unico de 2,5 s (24/min)
# so serve para o caso COM token: sem ele, a maioria dos papers toma 403 e cai
# em `sinal_indisponivel`.
GITHUB_SLEEP_WITHOUT_TOKEN = 6.0   # 10 req/min
GITHUB_SLEEP_WITH_TOKEN = 2.5      # 24/min, dentro dos 30/min autenticados


def github_sleep_seconds() -> float:
    return GITHUB_SLEEP_WITH_TOKEN if os.environ.get("GH_TOKEN") else GITHUB_SLEEP_WITHOUT_TOKEN


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

    intervalo = github_sleep_seconds()

    def fetch_signal(paper, day):
        time.sleep(intervalo)
        return github.signal_with_repos(paper, today=day)

    def judge_all(papers):
        if not papers:
            return {}
        batch = submit_batch(client, papers, model)
        if not wait_for_batch(client, batch.id):
            # Degradacao visivel: o dia segue, e todos os papers entram na
            # secao de cortes como `sem_julgamento` em vez de o workflow
            # ficar preso ate o timeout do runner.
            print(f"lote {batch.id} nao concluiu no prazo; o dia segue sem julgamentos",
                  flush=True)
            return {}
        return collect_batch_results(client.messages.batches.results(batch.id))

    result = run_day(
        store=store, scope=DEFAULT_SCOPE, thresholds=load_thresholds(), today=today,
        model=model,
        fetch_papers=arxiv.recent, fetch_signal=fetch_signal, judge_all=judge_all,
        dry_run=args.dry_run,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{today.isoformat()}.md").write_text(result.markdown, encoding="utf-8")
    print(f"radar: {len(result.radar)} · feed: {len(result.feed)} · cortes: {result.cuts}")

    if args.dry_run:
        print("dry-run: push nao enviado, entrega de telegram nao gravada")
        return 0

    try:
        sent = send(result.push,
                    token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                    chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
                    post=_telegram_post)
    except ValueError as exc:
        # Segredo faltando nao pode custar o dia inteiro. Quando isto acontece o
        # markdown ja esta escrito e o lote ja foi pago; deixar a excecao subir
        # matava o processo antes do passo de commit e os dois iam embora com o
        # runner efemero. Reporta e sai nao-zero -- o workflow fica vermelho,
        # que e o sinal correto -- enquanto o commit (if: always()) preserva o
        # que ja foi produzido.
        print(f"push nao enviado: {exc}", flush=True)
        return 1
    print(f"push enviado: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
