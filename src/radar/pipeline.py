"""Orquestracao. Unico modulo que conhece todas as pecas ao mesmo tempo.

Todos os servicos externos entram por injecao (fetch_papers, fetch_signal,
judge_all), o que torna o fluxo inteiro testavel offline.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from typing import Callable

from .config import PUSH_CAP, ScopeConfig, Thresholds
from .models import ACIONAVEIS, Discovery, Judgment, Paper, RepoClassification, Signal
from .render import RadarItem, render_markdown, render_telegram
from .scoring import evaluate
from .store import Store


def _motivo(base: str, e_novo: bool) -> str:
    """Motivo de corte prefixado pela trilha que o produziu.

    Em producao a re-consulta traz ~30 papers por dia contra 10-40 novos, entao
    contadores compartilhados fazem a secao de cortes -- que existe justamente
    para provar que o radar cobriu tudo -- ser dominada pela trilha que ela nao
    nomeia. Pior, as duas trilhas tem causas e consertos diferentes: um
    `abaixo_do_piso` de paper novo e calibracao de limiar; o mesmo numero na
    re-consulta e um paper guardado que ainda nao ressuscitou. Conflar os dois
    produz um numero que nao diz o que fazer -- o mesmo argumento que a spec da
    re-consulta ja fez para `reconsulta_sem_julgamento`.
    """
    return base if e_novo else f"reconsulta_{base}"


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
    # Default None mantem todo teste existente valido: sem buscador, ninguem
    # ganha citacao e todos ficam desconhecidos -- que e a resposta honesta
    # quando nao se perguntou. Quem liga e a CLI, explicitamente.
    fetch_citations: Callable[[list[str]], dict[str, int | None]] | None = None,
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
    # (A re-consulta de sinal desses papers e outra funcionalidade, construida
    # logo abaixo -- ver spec da re-consulta, secao 3.)
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
            # esteve inalcancavel -- aquela agora e alcancavel pela re-consulta,
            # esta ainda nao.
            if antigo.arxiv_id in novos_ids:
                continue
            trabalho.append((antigo, store.latest_judgment(antigo.arxiv_id), False))

    # TENTATIVAS de re-consulta, nao sobreviventes, e por isso contadas aqui e
    # nao sobre `candidates`. Um re-consultado cortado por falta de julgamento
    # ou por falha de sinal gastou a vaga da rotacao e a chamada de rate limit
    # exatamente como os que sobreviveram. Contar so os sobreviventes faz a
    # secao anunciar menos trabalho do que foi feito e, num dia em que todos
    # falham, some com a secao inteira -- o silencio ambiguo que a spec da
    # re-consulta, secao 7, proibiu.
    total_reconsultado = sum(1 for _, _, e_novo in trabalho if not e_novo)

    # (item, elegivel, e_novo, mexeu)
    # Uma requisicao para o dia inteiro: 40 ids cabem no lote de 50 do
    # OpenAlex. O GitHub nao carrega este dado -- ele mede GitHub. O pipeline
    # e quem compoe as duas fontes.
    citacoes: dict[str, int | None] = {}
    if fetch_citations is not None:
        citacoes = fetch_citations([p.arxiv_id for p, _, _ in trabalho])

    candidates: list[tuple[RadarItem, bool, bool, bool]] = []
    repos_by_paper: dict[str, list[dict]] = {}

    for paper, judgment, e_novo in trabalho:
        if judgment is None:
            cuts[_motivo("sem_julgamento", e_novo)] += 1
            if not e_novo:
                # Espelha o ramo de falha de sinal abaixo: a rotacao avanca em
                # TODO paper re-consultado (spec da re-consulta, secao 6). Sem
                # isto o paper fica com `last_checked` NULL, e como
                # `stalest_papers` ordena NULL primeiro ele volta na frente da
                # fila todos os dias, para sempre, consumindo a vaga e travando
                # a rotacao antes que ela alcance qualquer paper saudavel. Nao
                # se cura sozinho: o unico caminho que destravaria era este.
                store.touch_checked(paper.arxiv_id, at=day)
            continue

        try:
            signal, classifications = fetch_signal(paper, today)
        except Exception:
            # Falha de sinal num paper nao derruba o digest do dia inteiro.
            # `parse_search` levanta de proposito quando a resposta do GitHub e
            # de erro ou vem marcada como incompleta -- melhor perder o paper de
            # hoje do que gravar um zero falso que significaria "ninguem
            # implementou isto". Mesma licao da Tarefa 4.
            # Quando o paper volta depende da trilha: o RE-CONSULTADO volta na
            # proxima volta da rotacao, e o `touch_checked` abaixo e o que a faz
            # avancar. O paper NOVO nao volta pela re-consulta -- ele nunca
            # chegou a ser gravado, entao `stalest_papers` nao o conhece; ele so
            # retorna se o arXiv o re-descobrir.
            cuts[_motivo("sinal_indisponivel", e_novo)] += 1
            if not e_novo:
                # A rotacao precisa avancar mesmo quando a busca falha, ou
                # `stalest_papers` devolve os mesmos trinta para sempre.
                store.touch_checked(paper.arxiv_id, at=day)
            continue

        # `.get` sem default: ausente do dicionario vira None, nunca 0. Um
        # paper que o OpenAlex nao resolveu e desconhecido, nao inedito.
        signal = replace(signal, citations=citacoes.get(paper.arxiv_id))

        result = evaluate(signal, thresholds)

        if e_novo:
            store.upsert_paper(paper, seen_at=day, scope=scope.name)
            store.record_judgment(paper.arxiv_id, judgment, model=model, judged_at=day)

        # "Movimento" e ter mudado desde a observacao ANTERIOR -- por isso a
        # leitura acontece antes do insert de hoje, que seria a ultima linha.
        # Nao da para derivar isto de `signal_delta`: aquele compara a PRIMEIRA
        # com a ULTIMA observacao, o acumulado desde a descoberta, que e o que a
        # redacao do push quer ("2 -> 9 impls independentes em 1396 dias") e
        # exatamente o que um predicado de "mudou desde a ultima vez" nao pode
        # usar. Com o delta no lugar do predicado, um paper que subiu uma unica
        # vez entra na lista em toda re-consulta dali em diante, e em poucas
        # voltas a secao vira as trinta linhas de "nada de novo" que o teto de
        # legibilidade existe para evitar.
        # Descarta uma observacao do proprio dia: `record_signal` usa
        # INSERT OR REPLACE em (arxiv_id, checked_at), entao uma linha de hoje
        # sera SUBSTITUIDA por esta. Comparar com ela e comparar com uma linha
        # que nao vai existir -- produzia `mexeu` verdadeiro enquanto
        # `signal_delta` (que le o historico DEPOIS da escrita) devolvia None,
        # e o markdown saia com "None -> None impls independentes em None
        # dias". Filtrando aqui, `mexeu` e o delta concordam por construcao:
        # sem observacao anterior sobrevivente nao ha movimento a afirmar.
        anterior = [r for r in store.signal_history(paper.arxiv_id)
                    if r["checked_at"] != day]
        mexeu = (bool(anterior)
                 and anterior[-1]["independent_impls"] != signal.independent_impls)

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
            cuts[_motivo("ja_estourou", e_novo)] += 1
            candidates.append((item, False, e_novo, mexeu))
        # `<=`, nao `<`, e a escolha e deliberada. O piso e o ultimo valor
        # REJEITADO, nao o primeiro aceito. Com o piso documentado em 0.0 e a
        # formula da spec, score == 0.0 acontece exatamente quando
        # independent_impls == 0 (log1p(0) = 0): um paper que ninguem de fora
        # implementou. Com `<` esse paper passa e pode tomar uma das tres vagas
        # num dia magro -- constrangedor para um produto cuja tese e que
        # implementacao independente E o sinal. Silencio e resultado valido; a
        # vaga vazia diz a verdade, o paper sem implementacao nao.
        elif result.value <= thresholds.score_floor:
            cuts[_motivo("abaixo_do_piso", e_novo)] += 1
            candidates.append((item, False, e_novo, mexeu))
        # Guarda VIVA de entrega unica (spec secao 6: "Nenhum paper e entregue
        # duas vezes no Telegram"). Na trilha dos NOVOS ela e redundante: o
        # filtro de `ja_conhecido` acima ja barra qualquer paper que tenha sido
        # entregue, porque entregar exige estar no banco. Na trilha da
        # RE-CONSULTA ela e a regra viva -- papers antigos ja entregues reentram
        # neste laco todos os dias, e esta e a unica coisa entre eles e uma
        # segunda entrega. Apaga-la por parecer codigo morto quebra a garantia
        # central do produto.
        elif store.was_delivered(paper.arxiv_id, channel="telegram"):
            cuts[_motivo("ja_entregue", e_novo)] += 1
            candidates.append((item, False, e_novo, mexeu))
        else:
            candidates.append((item, True, e_novo, mexeu))

    # Ordem: executavel na 3090 primeiro, score depois. Sem isso, um paper que
    # Traducao da regra "executavel primeiro" da spec original, que ordenava
    # por `runs_on_3090 != "nao"`. Com o eixo de hardware removido, acionavel
    # passa a ser `adotar` + `testar`: o que o leitor pode usar hoje com infra
    # pequena. `observar` exige escala que ele nao tem e `nao_aplica` esta fora
    # do que ele faz -- os dois consumiriam uma das tres vagas competindo de
    # igual para igual com o acionavel.
    #
    # A ordenacao continua BINARIA de proposito: o score decide dentro do
    # nivel, como decidia antes. Uma ordem de quatro niveis faria um `testar`
    # de score alto perder para um `adotar` de score baixo, que e mudanca de
    # comportamento e nao traducao. Afeta o push apenas; o markdown leva todos.
    eligible = sorted(
        (i for i, ok, _, _ in candidates if ok),
        key=lambda i: (i.judgment.pratica in ACIONAVEIS, i.score),
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
    feed = [item for item, _, e_novo, _ in candidates if e_novo and item not in radar]

    # Re-consultado elegivel que nao coube no top 3 nao pode evaporar. O paper
    # NOVO que perde a corrida cai no feed; o re-consultado e barrado do feed
    # por desenho, entao sem este motivo ele nao entra no radar, nao entra no
    # feed e nao vira corte -- some do dia, que e o truncamento silencioso que a
    # restricao global proibe. Basta quatro papers guardados passarem do piso no
    # mesmo dia, provavel nas primeiras execucoes. Com ele a trilha particiona:
    # todo re-consultado termina no radar ou num motivo `reconsulta_*`.
    for candidato, elegivel, veio_de_hoje, _ in candidates:
        if not veio_de_hoje and elegivel and candidato not in radar:
            cuts["reconsulta_fora_do_top3"] += 1

    # Lista so quem se moveu desde a observacao anterior; os demais contam no
    # total e ficam calados. Trinta linhas de "nada mudou" sao ruido, e o teto
    # de legibilidade e a restricao de produto mais forte deste projeto.
    reconsultados_com_movimento = [
        item for item, _, e_novo, mexeu in candidates if not e_novo and mexeu
    ]

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
                                 cuts=dict(cuts), repos=repos_by_paper,
                                 rechecked=reconsultados_com_movimento,
                                 rechecked_total=total_reconsultado),
        push=render_telegram(radar),
    )
