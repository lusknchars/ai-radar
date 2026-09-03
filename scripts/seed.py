"""Semeia o acervo de UM escopo, sem piso de data.

NAO e a execucao diaria -- para isso existe `python -m radar.cli`. Este script
existe porque o seed tem tres caracteristicas que o dia a dia nao tem:

1. Um lote de mais de mil papers, que pode passar do prazo de 45 min que a CLI
   usa. `BATCH_TIMEOUT_SECONDS` e orcamento de cron diario; um lote que estoura
   devolve {} e TODO paper vira `sem_julgamento` -- lote pago, seed vazio.
2. Volume de busca no GitHub que merece progresso visivel: ~2,5s por paper com
   GH_TOKEN, entao mil papers sao quase uma hora.
3. Nenhuma re-consulta: o banco esta sendo criado, nao mantido.

GASTA DINHEIRO. Medido em 2026-08-29: US$ 4,36 para 1088 papers de inferencia.
O escopo de agentes tem ~1425 ineditos (sobreposicao medida de 1%), o que da
cerca de US$ 5,70.

Uso:
    set -a; . ~/.config/secrets/personal.env; set +a
    export GH_TOKEN="$(gh auth token)"
    python scripts/seed.py inferencia
    python scripts/seed.py agentes
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from radar.arxiv import USER_AGENT, ArxivClient                    # noqa: E402
from radar.config import (AGENT_SCOPE, DEFAULT_SCOPE, load_database_path,       # noqa: E402
                          load_llm_provider, load_model, load_thresholds)
from radar.github import GitHubClient                              # noqa: E402
from radar.judge import (collect_batch_results, submit_batch,      # noqa: E402
                         wait_for_batch)
from radar.openalex import USER_AGENT as OPENALEX_UA, OpenAlexClient  # noqa: E402
from radar.pipeline import run_day                                 # noqa: E402
from radar.store import Store                                      # noqa: E402

ESCOPOS = {e.name: e for e in (DEFAULT_SCOPE, AGENT_SCOPE)}

# 4h em vez dos 45 min da CLI. Aquele e orcamento de cron diario e nao serve
# aqui: um lote de mil papers pode passar disso, e o que estoura e perdido
# depois de pago. Foi o risco que o seed de 2026-08-29 correu.
PRAZO_LOTE = 4 * 60 * 60


def _arxiv_fetch(url: str) -> str:
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    r.raise_for_status()
    return r.text


def _github_fetch(url: str) -> dict:
    cab = {"User-Agent": "ai-radar/0.1", "Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        cab["Authorization"] = f"Bearer {token}"
    r = httpx.get(url, headers=cab, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _openalex_fetch(url: str) -> dict:
    r = httpx.get(url, headers={"User-Agent": OPENALEX_UA}, timeout=30.0)
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("escopo", choices=sorted(ESCOPOS))
    args = ap.parse_args()
    escopo = ESCOPOS[args.escopo]

    if load_llm_provider() != "anthropic":
        print(
            "[seed] historical backfill uses the Anthropic Batch API; "
            "use the daily pipeline for a Kimi-powered local archive",
            flush=True,
        )
        return 2

    t0 = time.monotonic()
    hoje = datetime.now(timezone.utc).date()
    intervalo = 2.5 if os.environ.get("GH_TOKEN") else 6.0
    print(f"[seed] {escopo.name} | {hoje} | intervalo GitHub {intervalo}s", flush=True)

    store = Store(load_database_path())
    store.init_schema()
    github = GitHubClient(fetch=_github_fetch)
    cliente = anthropic.Anthropic()
    modelo = load_model()
    vistos = {"n": 0}

    def fetch_signal(paper, dia):
        vistos["n"] += 1
        if vistos["n"] % 50 == 0:
            print(f"[seed] sinal {vistos['n']} | {time.monotonic() - t0:.0f}s", flush=True)
        time.sleep(intervalo)
        return github.signal_with_repos(paper, today=dia)

    def judge_all(papers):
        if not papers:
            return {}
        print(f"[seed] submetendo lote de {len(papers)} papers", flush=True)
        lote = submit_batch(cliente, papers, modelo)
        print(f"[seed] lote {lote.id}; prazo {PRAZO_LOTE // 60} min", flush=True)
        if not wait_for_batch(cliente, lote.id, poll_seconds=30,
                              timeout_seconds=PRAZO_LOTE):
            # Sem gravar nada: um seed pela metade e pior que nenhum, porque
            # `known_ids` passaria a esconder os papers que nao foram julgados.
            print("[seed] LOTE NAO CONCLUIU NO PRAZO -- abortando", flush=True)
            raise SystemExit(2)
        r = collect_batch_results(cliente.messages.batches.results(lote.id))
        print(f"[seed] {len(r)} julgamentos de {len(papers)} "
              f"em {time.monotonic() - t0:.0f}s", flush=True)
        return r

    resultado = run_day(
        store=store, scope=escopo, thresholds=load_thresholds(), today=hoje,
        model=modelo, fetch_papers=ArxivClient(fetch=_arxiv_fetch).recent,
        fetch_signal=fetch_signal, judge_all=judge_all,
        fetch_citations=OpenAlexClient(fetch=_openalex_fetch).citations_for,
        # O banco esta sendo criado, nao mantido: nao ha o que re-consultar.
        recheck_limit=0,
    )

    saida = RAIZ / "radar"
    saida.mkdir(parents=True, exist_ok=True)
    (saida / f"{hoje.isoformat()}-{escopo.name}.md").write_text(
        resultado.markdown, encoding="utf-8")

    print(f"[seed] FIM em {(time.monotonic() - t0) / 60:.0f} min", flush=True)
    print(f"[seed] radar={len(resultado.radar)} feed={len(resultado.feed)} "
          f"cortes={resultado.cuts}", flush=True)
    print(f"[seed] papers no banco: {len(store.all_papers())}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
