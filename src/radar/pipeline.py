"""Orquestracao. Unico modulo que conhece todas as pecas ao mesmo tempo.

Todos os servicos externos entram por injecao (fetch_papers, fetch_signal,
judge_all), o que torna o fluxo inteiro testavel offline.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Callable

from .config import PUSH_CAP, ScopeConfig, Thresholds
from .models import Discovery, Judgment, Paper, RepoClassification, Signal
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
    fetch_papers: Callable[[ScopeConfig], Discovery],
    fetch_signal: Callable[[Paper, date], tuple[Signal, list[RepoClassification]]],
    judge_all: Callable[[list[Paper]], dict[str, Judgment]],
    dry_run: bool = False,
    recheck_limit: int = 0,
) -> DayResult:
    day = today.isoformat()
    discovery = fetch_papers(scope)
    discovered = discovery.papers

    # Os cortes da descoberta (fora de escopo, termo que falhou) ja vem
    # contados e entram na mesma conta que os cortes deste modulo.
    cuts: Counter[str] = Counter(discovery.cuts)

    # Spec secao 3: "Papers ja presentes no banco nao reentram como novidade."
    # O Feed responde "o que saiu hoje" -- um paper que ja esta no banco nao
    # saiu hoje, entao nao entra nem no radar nem no feed do dia; vira corte
    # contado. Sem este filtro o dia 2 re-descobre e RE-JULGA quase tudo do dia
    # 1: custo do lote multiplicado e o mesmo feed republicado todo dia.
    # (A re-consulta de sinal desses papers e outra funcionalidade, ainda nao
    # construida -- ver spec secao 6.)
    conhecidos = store.known_ids()
    papers = [p for p in discovered if p.arxiv_id not in conhecidos]
    if len(discovered) != len(papers):
        cuts["ja_conhecido"] += len(discovered) - len(papers)

    judgments = judge_all(papers) if papers else {}

    # Lista de trabalho: (paper, julgamento, e_novo). Papers novos trazem o
    # julgamento do LLM; re-consultados trarao o julgamento lido do banco.
    # `e_novo` controla tres coisas e so tres: o motivo de corte quando falta
    # julgamento, quais gravacoes acontecem, e se o item pode chegar ao feed.
    trabalho: list[tuple[Paper, Judgment | None, bool]] = [
        (p, judgments.get(p.arxiv_id), True) for p in papers
    ]

    # Re-consulta (spec da re-consulta, secao 3): entra DEPOIS dos novos, que
    # tem prioridade de orcamento, e e a primeira coisa cortada quando o
    # orcamento acaba. Julgamento vem do banco -- re-consulta nao gasta token.
    if recheck_limit > 0:
        novos_ids = {p.arxiv_id for p in papers}
        for antigo in store.papers_to_recheck(limit=recheck_limit):
            # HOJE ESTA GUARDA E INALCANCAVEL, e isso e proposital documentar.
            # `known_ids()` acima ja removeu de `papers` tudo que esta no banco,
            # e `papers_to_recheck` le exatamente o banco -- os dois conjuntos
            # sao disjuntos por construcao. Ela fica como cinto e suspensorio:
            # se um dia `upsert_paper` subir para antes desta consulta, ou o
            # filtro de conhecidos afrouxar, ela passa a ser o unico obstaculo
            # contra buscar o sinal do mesmo paper duas vezes no mesmo dia.
            # Mesmo tratamento que a guarda `was_delivered` recebeu enquanto
            # esteve inalcancavel.
            if antigo.arxiv_id in novos_ids:
                continue
            trabalho.append((antigo, store.latest_judgment(antigo.arxiv_id), False))

    candidates: list[tuple[RadarItem, bool, bool]] = []   # (item, elegivel, e_novo)
    repos_by_paper: dict[str, list[dict]] = {}

    for paper, judgment, e_novo in trabalho:
        if judgment is None:
            cuts["sem_julgamento" if e_novo else "reconsulta_sem_julgamento"] += 1
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
            if not e_novo:
                # A rotacao precisa avancar mesmo quando a busca falha, ou
                # `stalest_papers` devolve os mesmos trinta para sempre.
                store.touch_checked(paper.arxiv_id, at=day)
            continue

        result = evaluate(signal, thresholds)

        if e_novo:
            store.upsert_paper(paper, seen_at=day)
            store.record_judgment(paper.arxiv_id, judgment, model=model, judged_at=day)
        store.record_signal(paper.arxiv_id, signal, score=result.value, checked_at=day)
        store.record_repos(paper.arxiv_id, classifications)
        store.touch_checked(paper.arxiv_id, at=day)
        repos_by_paper[paper.arxiv_id] = store.repos_for(paper.arxiv_id)

        item = RadarItem(paper=paper, judgment=judgment, signal=signal,
                         score=result.value or 0.0,
                         delta=store.signal_delta(paper.arxiv_id))

        # Todo paper novo no escopo chega ao markdown, inclusive o cortado do
        # radar: ou entre os tres, ou entre os demais.
        if result.gated_by is not None:
            cuts["ja_estourou"] += 1
            candidates.append((item, False, e_novo))
        # `<=`, nao `<`, e a escolha e deliberada. O piso e o ultimo valor
        # REJEITADO, nao o primeiro aceito. Com o piso documentado em 0.0 e a
        # formula da spec, score == 0.0 acontece exatamente quando
        # independent_impls == 0 (log1p(0) = 0): um paper que ninguem de fora
        # implementou. Com `<` esse paper passa e pode tomar uma das tres vagas
        # num dia magro -- constrangedor para um produto cuja tese e que
        # implementacao independente E o sinal. Silencio e resultado valido; a
        # vaga vazia diz a verdade, o paper sem implementacao nao.
        elif result.value <= thresholds.score_floor:
            cuts["abaixo_do_piso"] += 1
            candidates.append((item, False, e_novo))
        # Guarda de cinto e suspensorio (spec secao 6: "Nenhum paper e entregue
        # duas vezes no Telegram"). Hoje o filtro de `ja_conhecido` acima ja
        # barra qualquer paper que tenha sido entregue -- entregar exige estar
        # no banco. A guarda fica porque a re-consulta (spec secao 6, ainda nao
        # construida) reintroduz papers antigos neste laco, e ai ela volta a ser
        # o unico obstaculo entre um paper antigo e uma segunda entrega.
        elif store.was_delivered(paper.arxiv_id, channel="telegram"):
            cuts["ja_entregue"] += 1
            candidates.append((item, False, e_novo))
        else:
            candidates.append((item, True, e_novo))

    # Ordem: executavel na 3090 primeiro, score depois. Sem isso, um paper que
    # depende de FP8 -- inexecutavel em Ampere por definicao -- consome uma das
    # tres vagas competindo de igual para igual com o que voce pode testar hoje.
    # Rebaixar preserva a visao periferica sem deixar o inexecutavel disputar
    # espaco com o acionavel. Afeta o push apenas; o markdown leva todos.
    eligible = sorted(
        (i for i, ok, _ in candidates if ok),
        key=lambda i: (i.judgment.runs_on_3090 != "nao", i.score),
        reverse=True,
    )
    # Fatiado por PUSH_CAP, a mesma constante que o render usa como guarda.
    # Expressar o teto duas vezes deixava um Thresholds diferente produzir
    # quatro itens e quebrar no render, DEPOIS de mark_delivered ter rodado.
    radar = eligible[:PUSH_CAP]

    # Spec secao 7: o markdown e (1) os tres do radar e (2) todos os DEMAIS
    # candidatos. Calculado depois do corte para nao repetir os tres itens nas
    # duas secoes.
    #
    # Spec da re-consulta, secao 4: re-consultado entra no radar, nunca no
    # feed. O feed responde "o que saiu hoje", e um paper de 2022 nao saiu
    # hoje. Restricao do codigo, nao consequencia acidental.
    feed = [item for item, _, e_novo in candidates if e_novo and item not in radar]

    if not dry_run:
        # dry_run existe para ensaiar o dia sem consequencia. Gravar entrega de
        # telegram aqui queimaria os tres melhores itens do dia para sempre: a
        # primeira execucao de verdade os cortaria como ja_entregue.
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
