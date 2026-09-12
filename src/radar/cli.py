"""Ponto de entrada. Monta os adaptadores reais e chama o pipeline."""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

import anthropic
import httpx

from .arxiv import USER_AGENT, ArxivClient, parse_abstract_page
from .arxiv_html import fetch_arxiv_html
from .config import (AGENT_SCOPE, DEFAULT_SCOPE, load_kimi_base_url,
                     load_database_path, load_formula_model,
                     load_formula_thinking, load_kimi_request_interval,
                     load_llm_provider, load_model, load_recheck_limit,
                     load_thresholds)
from .equations import collect_equations
from .exa import ExaDiscovery
from .github import GitHubClient
from .judge import (KimiFormulaSelector, KimiJudge, collect_batch_results,
                    submit_batch, wait_for_batch)
from .openalex import USER_AGENT as OPENALEX_UA, OpenAlexClient
from .pipeline import run_day
from .render import compose_day
from .publish import publish_site
from .store import SchemaMigrationRequired, Store
from .telegram import send

# A busca do GitHub permite 10 req/min sem autenticacao e 30/min com token, e o
# README trata GH_TOKEN como opcional -- entao o intervalo tem que sair da
# presenca do segredo, e nao de um numero fixo. Um valor unico de 2,5 s (24/min)
# so serve para o caso COM token: sem ele, a maioria dos papers toma 403 e cai
# em `sinal_indisponivel`.
# Teto por execucao do passo de equacoes: cada paper custa uma chamada ao
# seletor com intervalo de requisicao, e um banco historico com mil papers
# nao pode transformar o run diario em horas.
MAX_EQUATIONS_PER_RUN = 40

GITHUB_SLEEP_WITHOUT_TOKEN = 6.0   # 10 req/min
GITHUB_SLEEP_WITH_TOKEN = 2.5      # 24/min, dentro dos 30/min autenticados


def github_sleep_seconds() -> float:
    return GITHUB_SLEEP_WITH_TOKEN if os.environ.get("GH_TOKEN") else GITHUB_SLEEP_WITHOUT_TOKEN


def _arxiv_fetch(url: str) -> str:
    for attempt in range(3):
        try:
            r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True)
            r.raise_for_status()
            return r.text
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            retryable = not isinstance(error, httpx.HTTPStatusError) or error.response.status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def _exa_search(payload: dict) -> dict:
    response = httpx.post("https://api.exa.ai/search", json=payload,
                          headers={"x-api-key": os.environ["EXA_API_KEY"]}, timeout=30)
    response.raise_for_status()
    return response.json()


def _openalex_fetch(url: str) -> dict:
    r = httpx.get(url, headers={"User-Agent": OPENALEX_UA}, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _github_fetch(url: str) -> dict:
    headers = {"User-Agent": "ai-radar/0.1", "Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.get(url, headers=headers, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _arxiv_html_fetch(arxiv_id: str):
    return fetch_arxiv_html(arxiv_id, get=httpx.get)


def _telegram_post(url: str, json: dict) -> dict:
    r = httpx.post(url, json=json, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _executar(args, db_path: Path, today) -> int:
    """O trabalho do dia. Separado de `main` para que a limpeza do diretorio de
    ensaio caiba num `finally` sem reindentar o corpo inteiro."""
    store = Store(db_path)
    try:
        store.init_schema()
        run_id = store.begin_collection(today.isoformat())
        try:
            return _collect(args, store, today, run_id)
        except Exception:
            store.finish_collection(run_id, "failed")
            if not args.dry_run:
                try:
                    publish_site(store, args.out.parent / "site", today)
                except Exception:
                    print("Could not publish the failed-collection notice", flush=True)
            raise
    finally:
        store.close()


def _collect(args, store: Store, today: date, run_id: int) -> int:
    new_limit = int(os.environ.get("RADAR_MAX_NEW_PER_SCOPE", "20"))
    if not 1 <= new_limit <= 100:
        raise ValueError("RADAR_MAX_NEW_PER_SCOPE must be between 1 and 100")
    equation_limit = int(os.environ.get("RADAR_MAX_EQUATIONS_PER_RUN", str(min(5, MAX_EQUATIONS_PER_RUN))))
    if not 0 <= equation_limit <= MAX_EQUATIONS_PER_RUN:
        raise ValueError(f"RADAR_MAX_EQUATIONS_PER_RUN must be between 0 and {MAX_EQUATIONS_PER_RUN}")
    arxiv = ArxivClient(fetch=_arxiv_fetch)
    discovery = arxiv
    exa_mode = os.environ.get("RADAR_EXA_MODE", "daily")
    if exa_mode not in {"off", "weekly", "daily"}:
        raise ValueError("RADAR_EXA_MODE must be off, weekly, or daily")
    if os.environ.get("EXA_API_KEY") and (exa_mode == "daily" or (exa_mode == "weekly" and today.weekday() == 0)):
        discovery = ExaDiscovery(arxiv, search=_exa_search, fetch=_arxiv_fetch,
                                 fetch_one=lambda paper_id: parse_abstract_page(
                                     _arxiv_fetch(f'https://arxiv.org/abs/{paper_id}'), paper_id),
                                 today=today, results=int(os.environ.get("RADAR_EXA_RESULTS", "10")),
                                 queries=int(os.environ.get("RADAR_EXA_QUERIES", "1")),
                                 lookback_days=int(os.environ.get("RADAR_EXA_LOOKBACK_DAYS", "30")))
    github = GitHubClient(fetch=_github_fetch)
    provider = load_llm_provider()
    model = load_model()

    if provider == "kimi":
        kimi = KimiJudge(
            os.environ.get("KIMI_API_KEY", ""), model,
            request_interval=load_kimi_request_interval(),
            base_url=load_kimi_base_url(),
        )

        def judge_all(papers):
            return kimi.judge_all(papers)
    else:
        client = anthropic.Anthropic()

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

    intervalo = github_sleep_seconds()

    def fetch_signal(paper, day):
        time.sleep(intervalo)
        return github.signal_with_repos(paper, today=day)

    openalex = OpenAlexClient(fetch=_openalex_fetch)
    limiares = load_thresholds()
    resultados: dict[str, object] = {}
    cortes_do_dia: Counter[str] = Counter()

    for i, escopo in enumerate((DEFAULT_SCOPE, AGENT_SCOPE)):
        print(f"Collecting {escopo.name}: up to {new_limit} new briefs", flush=True)
        r = run_day(
            store=store, scope=escopo, thresholds=limiares, today=today,
            model=model,
            fetch_papers=discovery.recent, fetch_signal=fetch_signal,
            judge_all=judge_all, fetch_citations=openalex.citations_for,
            dry_run=args.dry_run,
            new_paper_limit=new_limit,
            # A re-consulta e global e roda UMA VEZ SO: ela varre `papers`
            # inteira e nao conhece escopo. Ligar nas duas passadas gastaria
            # o dobro do orcamento re-consultando exatamente os mesmos papers.
            recheck_limit=load_recheck_limit() if i == 0 else 0,
        )
        resultados[escopo.name] = r
        cortes_do_dia.update(r.cuts)
        print(f"{escopo.name}: radar {len(r.radar)} · feed {len(r.feed)} "
              f"· cortes {r.cuts}")

    incomplete = any(
        count and any(reason in key for reason in
                      ("termo_falhou", "sem_julgamento", "sinal_indisponivel", "exa_search_failed", "exa_metadata_missing", "exa_metadata_failed"))
        for key, count in cortes_do_dia.items()
    )
    store.finish_collection(
        run_id, "partial" if incomplete else "success",
        discovered=sum(r.discovered_count for r in resultados.values()),
        indexed=sum(r.indexed_count for r in resultados.values()),
    )

    if not args.dry_run and provider == "kimi":
        # Equacoes centrais do HTML do arXiv para todo paper que ainda nao tem
        # estado gravado: os de hoje e qualquer um que uma falha de rede tenha
        # deixado para tras. Corre depois do julgamento e antes do jornal; uma
        # falha vira estado por paper, nunca uma excecao que derrube o dia.
        pendentes = store.papers_without_equations()[:min(equation_limit, MAX_EQUATIONS_PER_RUN)]
        if pendentes:
            selector = KimiFormulaSelector(
                os.environ.get("KIMI_API_KEY", ""), load_formula_model(),
                thinking=load_formula_thinking(),
                request_interval=load_kimi_request_interval(),
                base_url=load_kimi_base_url(),
            )
            outcome = collect_equations(
                store, pendentes, fetch_html=_arxiv_html_fetch,
                selector=selector, today=today.isoformat(),
                selector_model=load_formula_model(),
            )
            print(f"equacoes: {dict(outcome)}", flush=True)

    markdown = compose_day(today.isoformat(), resultados)
    push = "\n\n".join(r.push for r in resultados.values() if r.push)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{today.isoformat()}.md").write_text(markdown, encoding="utf-8")

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    destination = sha256(telegram_chat.encode()).hexdigest()
    if not args.dry_run and telegram_token and telegram_chat and push.strip():
        store.queue_delivery(
            today.isoformat(), "telegram", destination, push,
            [item.paper.arxiv_id for result in resultados.values() for item in result.radar],
        )

    if not args.dry_run:
        # O jornal e o acervo INTEIRO, nao o dia: por isso ele le do banco em
        # vez de usar os DayResult acima. E por isso tambem que o ensaio a
        # seco nao o escreve -- ele nao gravou nada no banco de verdade.
        pagina = args.out.parent / "site"
        publish_site(store, pagina, today, cuts=dict(cortes_do_dia))
        print(f"jornal: {pagina / 'index.html'}")

    if args.dry_run:
        print("dry-run: push nao enviado, nada gravado no banco de verdade")
        return 0

    if not telegram_token and not telegram_chat:
        print("push skipped: Telegram is not configured", flush=True)
        return 1 if incomplete else 0

    if not telegram_token or not telegram_chat:
        print("push nao enviado: configure both Telegram credentials", flush=True)
        return 1
    for message in store.pending_deliveries("telegram", destination):
        if not send(message['body'], token=telegram_token, chat_id=telegram_chat,
                    post=_telegram_post):
            print("push nao enviado: queued for retry", flush=True)
            return 1
        store.acknowledge_delivery(message['id'], today.isoformat())
        print("push enviado: True", flush=True)
    return 1 if incomplete else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-radar")
    parser.add_argument("--db", type=Path, default=load_database_path())
    parser.add_argument("--out", type=Path, default=Path("radar"))
    parser.add_argument("--dry-run", action="store_true",
                        help="escreve o markdown do dia, mas nao envia o push "
                             "e nao deixa nada gravado no banco de verdade")
    args = parser.parse_args(argv)

    today = datetime.now(timezone.utc).date()

    # No ensaio o banco e uma copia descartavel. Pular so a entrega de telegram
    # nao basta: `run_day` tambem grava o paper em `papers`, e desde que papers
    # ja conhecidos deixaram de reentrar como novidade, um paper gravado no
    # ensaio e cortado como `ja_conhecido` na primeira execucao de verdade --
    # a mesma queima de antes, por outra porta. O passo de commit do workflow
    # nao distingue dry-run, entao a garantia tem de ser que o ensaio nao
    # produza estado duravel nenhum.
    db_path = args.db
    ensaio = None
    if args.dry_run:
        ensaio = tempfile.mkdtemp(prefix="radar-dry-run-")
        db_path = Path(ensaio) / "radar.db"
        if args.db.exists():
            shutil.copy2(args.db, db_path)   # le o estado real, escreve na copia

    try:
        try:
            return _executar(args, db_path, today)
        except SchemaMigrationRequired as exc:
            print(f"pipeline bloqueado: {exc}", flush=True)
            return 2
    finally:
        # `finally`, nao o caminho feliz: qualquer excecao entre o mkdtemp e o
        # fim -- arXiv fora do ar, submit do lote falhando, disco cheio ao
        # escrever o markdown -- vazava um radar-dry-run-* com uma copia do
        # banco dentro, e a conexao sqlite nunca era fechada.
        if ensaio is not None:
            shutil.rmtree(ensaio, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
