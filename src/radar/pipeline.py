"""Orquestracao. Unico modulo que conhece todas as pecas ao mesmo tempo.

Todos os servicos externos entram por injecao (fetch_papers, fetch_signal,
judge_all), o que torna o fluxo inteiro testavel offline.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from .config import ScopeConfig, Thresholds
from .models import Judgment, Paper, RepoClassification, Signal
from .render import RadarItem, render_markdown, render_telegram
from .scoring import evaluate
from .store import Store


@dataclass
class DayResult:
    radar: list[RadarItem]
    feed: list[RadarItem]
    cuts: dict[str, int]
    markdown: str
    push: str


def run_day(
    store: Store,
    scope: ScopeConfig,
    thresholds: Thresholds,
    today: date,
    model: str,
    fetch_papers: Callable[[ScopeConfig], list[Paper]],
    fetch_signal: Callable[[Paper, date], tuple[Signal, list[RepoClassification]]],
    judge_all: Callable[[list[Paper]], dict[str, Judgment]],
) -> DayResult:
    day = today.isoformat()
    papers = fetch_papers(scope)
    judgments = judge_all(papers) if papers else {}

    cuts: Counter[str] = Counter()
    candidates: list[tuple[RadarItem, bool]] = []   # (item, elegivel_para_push)
    repos_by_paper: dict[str, list[dict]] = {}

    for paper in papers:
        judgment = judgments.get(paper.arxiv_id)
        if judgment is None:
            cuts["sem_julgamento"] += 1
            continue

        try:
            signal, classifications = fetch_signal(paper, today)
        except Exception:
            # Falha de sinal num paper nao derruba o digest do dia inteiro.
            # `parse_search` levanta de proposito quando a resposta do GitHub e
            # de erro ou vem marcada como incompleta -- melhor pular o paper e
            # pega-lo na re-consulta de amanha do que gravar um zero falso que
            # significaria "ninguem implementou isto". Mesma licao da Tarefa 4.
            cuts["sinal_indisponivel"] += 1
            continue

        result = evaluate(signal, thresholds)

        store.upsert_paper(paper, seen_at=day)
        store.record_signal(paper.arxiv_id, signal, score=result.value, checked_at=day)
        store.record_repos(paper.arxiv_id, classifications)
        store.record_judgment(paper.arxiv_id, judgment, model=model, judged_at=day)
        store.touch_checked(paper.arxiv_id, at=day)
        repos_by_paper[paper.arxiv_id] = store.repos_for(paper.arxiv_id)

        item = RadarItem(paper=paper, judgment=judgment, signal=signal,
                         score=result.value or 0.0,
                         delta=store.signal_delta(paper.arxiv_id))

        # Todo paper no escopo vai para o feed, inclusive o cortado do radar.
        if result.gated_by is not None:
            cuts["ja_estourou"] += 1
            candidates.append((item, False))
        elif result.value < thresholds.score_floor:
            cuts["abaixo_do_piso"] += 1
            candidates.append((item, False))
        elif store.was_delivered(paper.arxiv_id, channel="telegram"):
            cuts["ja_entregue"] += 1
            candidates.append((item, False))
        else:
            candidates.append((item, True))

    feed = [item for item, _ in candidates]

    # Ordem: executavel na 3090 primeiro, score depois. Sem isso, um paper que
    # depende de FP8 -- inexecutavel em Ampere por definicao -- consome uma das
    # tres vagas competindo de igual para igual com o que voce pode testar hoje.
    # Rebaixar preserva a visao periferica sem deixar o inexecutavel disputar
    # espaco com o acionavel. Afeta o push apenas; o feed leva tudo.
    eligible = sorted(
        (i for i, ok in candidates if ok),
        key=lambda i: (i.judgment.runs_on_3090 != "nao", i.score),
        reverse=True,
    )
    radar = eligible[:thresholds.push_cap]

    for rank, item in enumerate(radar, start=1):
        store.mark_delivered(item.paper.arxiv_id, channel="telegram", at=day, rank=rank)
    for item in feed:
        store.mark_delivered(item.paper.arxiv_id, channel="markdown", at=day, rank=None)

    return DayResult(
        radar=radar,
        feed=feed,
        cuts=dict(cuts),
        markdown=render_markdown(day, radar=radar, feed=feed,
                                 cuts=dict(cuts), repos=repos_by_paper),
        push=render_telegram(radar),
    )
