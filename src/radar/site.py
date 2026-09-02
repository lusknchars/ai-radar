"""Renderizadores semanticos do acervo, gerados por funcoes puras.

Sem framework, sem passo de build, sem dependencia externa -- nem no servidor
nem no cliente. A pagina e um arquivo, e funciona com JS desligado.

Recebe `SiteData` pronto e NUNCA o `Store`: a coleta mora no banco, o desenho
nao sabe de onde o dado veio. CSS e comportamento do navegador pertencem a
``site_assets``; este modulo decide apenas estrutura, conteudo e links.
"""
from __future__ import annotations

import json
import re
from html import escape
from urllib.parse import urlencode

from .config import load_thresholds
from .formulas import FormulaWalkthrough, TechnicalCore
from .leitura import afirmacoes
from .report import ReportDocument
from .site_assets import BACKGROUND_SCRIPT as _BACKGROUND_JS
from .site_assets import CHART_SCRIPT as _CHART_JS
from .site_assets import REPORT_SCRIPT as _REPORT_JS
from .site_assets import SCRIPT as _JS, STYLES as _CSS
from .site_data import SiteData
from .svg import (METRICAS_X, render_avanco,
                  render_pequenos_multiplos, render_scatter)

# Cor significa familia, e SO. Em nenhum grafico ela codifica outra coisa.
# As matizes agrupam por escopo -- escala de preto para inferencia, framboesa
# para agentes, cinza para o escape -- o que ajuda a leitura sem que a cor passe
# a significar escopo: dentro de cada grupo elas sao distintas e arbitrarias.
CORES_FAMILIA = {
    # inferencia: escala de preto
    "quantizacao":                "#000000",
    "cache_kv":                   "#121212",
    "decodificacao_especulativa": "#242424",
    "esparsidade_e_poda":         "#363636",
    "kernels_e_atencao":          "#484848",
    "serving_e_batching":         "#5a5a5a",
    "arquitetura_eficiente":      "#6c6c6c",
    "destilacao":                 "#7e7e7e",
    "treino_eficiente":           "#909090",
    # agentes: escala de framboesa
    "uso_de_ferramenta":          "#cb2957",
    "memoria_e_contexto":         "#b92450",
    "planejamento_e_decomposicao": "#a82049",
    "orquestracao_multiagente":   "#971c43",
    "avaliacao_de_agente":        "#86183c",
    "recuperacao_de_falha":       "#751436",
    "agentes_de_codigo":          "#641130",
    "seguranca_e_guardrails":     "#d2456c",
    "recuperacao_e_rag":          "#db6683",
    # escape: neutro, e de proposito o menos chamativo da paleta
    "outro":                      "#aaaaaa",
}

ROTULOS_FAMILIA = {
    "quantizacao": "quantização",
    "cache_kv": "cache KV",
    "decodificacao_especulativa": "decodificação especulativa",
    "esparsidade_e_poda": "esparsidade e poda",
    "kernels_e_atencao": "kernels e atenção",
    "serving_e_batching": "serving e batching",
    "arquitetura_eficiente": "arquitetura eficiente",
    "destilacao": "destilação",
    "treino_eficiente": "treino eficiente",
    "uso_de_ferramenta": "uso de ferramenta",
    "memoria_e_contexto": "memória e contexto",
    "planejamento_e_decomposicao": "planejamento e decomposição",
    "orquestracao_multiagente": "orquestração multiagente",
    "avaliacao_de_agente": "avaliação de agente",
    "recuperacao_de_falha": "recuperação de falha",
    "agentes_de_codigo": "agentes de código",
    "seguranca_e_guardrails": "segurança e guardrails",
    "recuperacao_e_rag": "recuperação e RAG",
    "outro": "outro",
}

ROTULOS_PRATICA = {
    "adotar": "adotar",
    "testar": "testar",
    "observar": "observar",
    "nao_aplica": "não se aplica",
}

ROTULOS_INFRA = {
    "api_or_cpu": "API ou CPU",
    "single_gpu_24gb": "1 GPU, até 24 GB",
    "single_gpu_48_80gb": "1 GPU, 48 a 80 GB",
    "multi_gpu": "múltiplas GPUs",
    "cluster": "cluster",
    "custom_hardware": "hardware específico",
    "unknown": "não informado",
}

ROTULOS_BASE_INFRA = {
    "explicit": "declarada no paper",
    "inferred": "inferida dos requisitos",
    "unknown": "não informada",
}

ROTULOS_TREINO = {
    "none": "nenhum",
    "inference_only": "somente inferência",
    "fine_tuning": "fine-tuning",
    "train_from_scratch": "treino do zero",
    "unknown": "não informado",
}

ROTULOS_NUCLEO = {
    "formula": "núcleo formulado",
    "algorithm": "núcleo de algoritmo",
    "system": "núcleo de sistema",
    "evaluation_protocol": "núcleo de protocolo de avaliação",
    "concept": "núcleo conceitual",
    "none": "núcleo ainda não classificado",
}

ROTULOS_PAPEL_FORMULA = {
    "baseline": "baseline",
    "proposed_method": "método proposto",
    "loss": "função de perda",
    "metric": "métrica",
    "complexity": "complexidade",
}

ROTULOS_ESTADO_FORMULA = {
    "concept_only": "conceito identificado, notação não verificada",
    "not_applicable": "o núcleo técnico não depende de uma nova fórmula",
    "extraction_failed": "notação não extraída com segurança",
}

ROTULOS_SETUP = {
    "standard_python": "Python padrão",
    "containerized": "container",
    "custom_runtime": "runtime próprio",
    "custom_cuda_kernel": "kernel CUDA próprio",
    "distributed_stack": "stack distribuída",
    "specialized_simulator": "simulador especializado",
    "unknown": "não informado",
}

# Contrato com o leitor. Escrito a mao e versionado -- nao e gerado, e nao
# muda com o dado do dia.
_ENQUADRAMENTO = (
    "<p>Este radar mede uma coisa só: quantas <strong>implementações "
    "independentes</strong> um paper atraiu no GitHub, descontando os "
    "repositórios dos próprios autores. A hipótese é que gente reimplementando "
    "por conta própria diz mais sobre uma técnica do que citação ou estrela.</p>"
    "<p>Ele <strong>não mede</strong> se a técnica funciona. Nada aqui foi "
    "reproduzido, não há benchmark, e todo número de ganho que aparecer é "
    "alegação dos autores extraída do resumo — nunca resultado verificado. "
    "Papers que já estouraram em atenção são cortados de propósito: o radar "
    "existe para achar o que ainda não foi olhado.</p>"
)


def _nav(atual: str) -> str:
    itens = (
        ("acervo", "/ai-radar/#acervo", "pesquisa"),
        ("sinais", "/ai-radar/#sinais", "sinais"),
        ("edicoes", "/ai-radar/edicoes/", "edições"),
        ("about", "/ai-radar/about.html", "método"),
        ("rss", "/ai-radar/feed.xml", "RSS"),
    )
    links = "".join(
        f'<a href="{href}"'
        f'{" aria-current=\"page\"" if chave == atual else ""}>{rotulo}</a>'
        for chave, href, rotulo in itens
    )
    return f'<nav class="nav" aria-label="principal">{links}</nav>'


def _sheen_content(label: str) -> str:
    return (
        '<span class="sheen-sweep" aria-hidden="true"></span>'
        '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
        'stroke-linejoin="round"><path d="M7 17 17 7M9 7h8v8"></path></svg>'
        f'<span class="sheen-label">{escape(label)}</span>'
    )


def _sheen_link(label: str, href: str, *, classes: str = "",
                aria_label: str | None = None, rel: str = "") -> str:
    aria = f' aria-label="{escape(aria_label)}"' if aria_label else ""
    relationship = f' rel="{escape(rel)}"' if rel else ""
    return (
        f'<a class="sheen-button {classes}" href="{escape(href)}"'
        f'{aria}{relationship}>'
        f'{_sheen_content(label)}</a>'
    )


def _cabecalho(d: SiteData, edicao: bool = False) -> str:
    impls = sum(p.independent_impls for p in d.pontos)
    contexto = "edição preservada" if edicao else "caderno de pesquisa"
    return (
        '<header class="masthead publication-head"><div class="hero-copy">'
        f'<p class="hero-eyebrow">{contexto} · {escape(d.dia)}</p>'
        '<h1><span class="marca">ai-radar · research notes</span>'
        'Pesquisa aplicada.<br><em>Antes do hype.</em></h1>'
        '<p class="hero-deck">Uma publicação sobre papers de AI que podem '
        'mudar o trabalho de engenharia. Cada nota separa a ideia, o sinal '
        'independente e o custo real de testar.</p>'
        f'{_sheen_link("abrir o índice", "#acervo")}</div>'
        '<dl class="edition-ledger" aria-label="resumo desta edição">'
        f'<div><dt>edição</dt><dd>{escape(d.dia)}</dd></div>'
        f'<div><dt>briefs</dt><dd>{len(d.pontos)}</dd></div>'
        f'<div><dt>famílias</dt><dd>{len(d.familias_presentes)}</dd></div>'
        f'<div><dt>implementações independentes</dt><dd>{impls}</dd></div>'
        '</dl></header>'
    )


def _secao(titulo: str, sub: str, corpo: str, *, section_id: str = "") -> str:
    identificador = f' id="{escape(section_id)}"' if section_id else ""
    return (
        f'<section{identificador}><div class="section-head">'
        f'<h2>{titulo}</h2><p class="sub">{sub}</p></div>{corpo}</section>'
    )


def _legenda(d: SiteData) -> str:
    """So as familias PRESENTES no acervo.

    Listar as dezenove sempre encheria a legenda de cor que nao aparece em
    ponto nenhum, e a legenda existe para decodificar o grafico, nao para
    catalogar a taxonomia.
    """
    itens = "".join(
        f'<button type="button" data-legenda="{escape(f)}">'
        f'<i style="background:{CORES_FAMILIA[f]}"></i>'
        f'{escape(ROTULOS_FAMILIA[f])}</button>'
        for f in d.familias_presentes
    )
    return f'<div class="legenda">{itens}</div>'


def _cartao_grafico(numero: str, titulo: str, descricao: str, corpo: str,
                    *, classe: str = "") -> str:
    modificador = f" {escape(classe)}" if classe else ""
    return (
        f'<article class="chart-card{modificador}">'
        '<header class="chart-card-head">'
        f'<p class="chart-kicker">{escape(numero)}</p>'
        f'<div><h3>{escape(titulo)}</h3><p>{escape(descricao)}</p></div>'
        f'</header><div class="chart-card-body">{corpo}</div></article>'
    )


def _chart_payload(kind: str, values: list[dict]) -> str:
    """Serializa dado inerte sem permitir que um titulo feche a tag script."""
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("&", "\\u0026")
    return (
        f'<script type="application/json" data-chart-data="{escape(kind)}">'
        f'{payload}</script>'
    )


def _point_chart_data(d: SiteData) -> list[dict]:
    return [
        {
            "arxiv_id": p.arxiv_id,
            "title": p.titulo,
            "family": p.familia,
            "family_label": ROTULOS_FAMILIA[p.familia],
            "color": CORES_FAMILIA[p.familia],
            "independent_impls": p.independent_impls,
            "total_impls": p.total_impls,
            "stars_total": p.stars_total,
            "idade_dias": p.idade_dias,
            "gain": p.ganho_fator,
            "gain_axis": p.ganho_eixo,
            "published": p.publicado,
            "month": p.publicado[:7],
            "url": f"https://arxiv.org/abs/{p.arxiv_id}",
        }
        for p in d.pontos
    ]


def _secao_fronteira(d: SiteData) -> str:
    lim = load_thresholds()
    botoes = "".join(
        f'<button type="button" data-eixo="{m}" '
        f'aria-pressed="{"true" if i == 0 else "false"}">{rotulo}</button>'
        for i, (m, rotulo) in enumerate(METRICAS_X.items())
    )
    graficos = "".join(
        render_scatter(d.pontos, m, CORES_FAMILIA)
        .replace('<svg class="scatter"',
                 f'<svg class="scatter" data-eixo="{m}"'
                 + ("" if i == 0 else " hidden"))
        for i, m in enumerate(METRICAS_X)
    )
    nota = (f'<p class="nota">Papers acima de {lim.broke_out_stars} estrelas ou '
            f"{lim.broke_out_citations} citações não são pontuados: já "
            f"estourou em atenção, e o radar existe para o que ainda não "
            f"estourou.</p>")
    return botoes and (
        f'<div class="eixos chart-controls" aria-label="eixo horizontal">'
        f'<span>comparar por</span>{botoes}</div>'
        f'<div class="chart-scroll" data-plot-panel="frontier" tabindex="0" '
        f'aria-label="gráfico da fronteira; role horizontalmente para explorar">'
        '<div class="plot-enhancement" data-plot-host="frontier" hidden></div>'
        f'<div class="plot-fallback">{graficos}</div></div>'
        f'{_chart_payload("frontier", _point_chart_data(d))}{nota}'
    )


# Abaixo disso a secao de avanco nao e construida: grafico sobre dado ralo e
# pior que grafico ausente. Ver spec do jornal, secao 3.4.
COBERTURA_MINIMA = 0.35

ROTULO_ALEGACAO = "alegado pelos autores, não verificado"
BRIEF_INITIAL_LIMIT = 30
REPORT_REPOSITORY = "lusknchars/ai-radar"


def _secao_avanco(d: SiteData) -> str:
    """Devolve string vazia quando o dado nao sustenta o grafico.

    O chamador precisa omitir a SECAO INTEIRA nesse caso -- titulo e subtitulo
    incluidos -- para nao sobrar rotulo orfao nem promessa vazia.
    """
    if d.cobertura_de_ganho < COBERTURA_MINIMA:
        return ""
    com = sum(1 for p in d.pontos if p.ganho_fator is not None)
    return (
        '<div class="chart-scroll" data-plot-panel="gain" tabindex="0" '
        'aria-label="gráfico de ganho alegado; role horizontalmente para explorar">'
        '<div class="plot-enhancement" data-plot-host="gain" hidden></div>'
        f'<div class="plot-fallback">{render_avanco(d.pontos, CORES_FAMILIA)}</div>'
        '</div>'
        f'{_chart_payload("gain", _point_chart_data(d))}'
        f'<p class="nota">{com} de {len(d.pontos)} papers declaram ganho '
        f'quantificado. Escala logarítmica; a linha por família só aparece '
        f'com pelo menos cinco papers no trimestre.</p>'
    )


def _destacar_numeros(texto: str) -> str:
    """Escapa cada trecho e envolve apenas numeros do texto original.

    Aplicar a regex depois de `escape()` tambem pegava o 27 de `&#x27;`,
    quebrando aspas em `&#x<b>27</b>;` e exibindo a entidade no navegador.
    """
    numero = re.compile(r"^\d[\d.,]*%?$")
    partes = re.split(r"(\d[\d.,]*%?)", texto)
    return "".join(
        f'<b class="n">{escape(parte)}</b>' if numero.fullmatch(parte)
        else escape(parte)
        for parte in partes
    )


def _secao_leitura(d: SiteData) -> str:
    """Prosa, nao cartoes de metrica.

    Cartao convida a leitura por varredura, e varredura e o modo em que numero
    sem contexto vira impressao. As frases entram em paragrafo, com os numeros
    em destaque tipografico.

    Frase com filtro vira botao que aplica o recorte na tabela abaixo -- e o
    que separa esta secao de um resumo gerado. Uma afirmacao conferivel em
    dois cliques e verificavel; uma que so pode ser aceita e autoridade.
    """
    afs = afirmacoes(d)
    if not afs:
        return ""
    partes = []
    for a in afs:
        corpo = _destacar_numeros(a.texto)
        if a.filtro:
            chave, valor = next(iter(a.filtro.items()))
            partes.append(
                f'<button type="button" class="frase" '
                f'data-aplicar="{escape(chave)}" '
                f'data-valor="{escape(str(valor))}">{corpo}</button>'
            )
        else:
            partes.append(f'<p class="frase">{corpo}</p>')
    return f'<section class="leitura">{"".join(partes)}</section>'


def _secao_familias(d: SiteData) -> str:
    series: dict[str, dict[str, int]] = {}
    for p in d.pontos:
        series.setdefault(p.familia, {}).setdefault(p.publicado[:7], 0)
        series[p.familia][p.publicado[:7]] += 1
    grafico = render_pequenos_multiplos(
        series, d.familias_presentes, CORES_FAMILIA, ROTULOS_FAMILIA)
    months = sorted({month for values in series.values() for month in values})
    values = [
        {
            "family": family,
            "family_label": ROTULOS_FAMILIA[family],
            "color": CORES_FAMILIA[family],
            "month": month,
            "count": series.get(family, {}).get(month, 0),
        }
        for family in d.familias_presentes
        for month in months
    ]
    return (
        '<div class="chart-scroll" data-plot-panel="families" tabindex="0" '
        'aria-label="gráfico das famílias no tempo; role horizontalmente para explorar">'
        '<div class="plot-enhancement" data-plot-host="families" hidden></div>'
        f'<div class="plot-fallback">{grafico}</div></div>'
        f'{_chart_payload("families", values)}'
        '<p class="nota">Todos os painéis compartilham o mesmo calendário e '
        'a mesma escala vertical; uma coluna vazia significa zero papers.</p>'
    )


def _secao_graficos(d: SiteData) -> str:
    """Um único caderno visual, com uma legenda e ordem de leitura explícita."""
    cartoes = [
        _cartao_grafico(
            "01 · atenção × adoção", "A fronteira",
            "Procure o alto à esquerda: implementação independente antes de atenção massiva.",
            _secao_fronteira(d), classe="chart-card--frontier",
        ),
        _cartao_grafico(
            "02 · cadência", "As famílias no tempo",
            "Compare o volume mensal sem trocar a régua ou deslocar o calendário.",
            _secao_familias(d), classe="chart-card--families",
        ),
    ]
    avanco = _secao_avanco(d)
    if avanco:
        cartoes.append(_cartao_grafico(
            "03 · alegação", "O avanço alegado",
            f"Ganho declarado no resumo — {ROTULO_ALEGACAO}.",
            avanco, classe="chart-card--gain",
        ))
    return (
        '<div class="chart-suite">'
        '<div class="chart-shared-legend"><span>cor = família</span>'
        f'{_legenda(d)}</div>{"".join(cartoes)}</div>'
    )


def _opcoes(valores: list[str], rotulos: dict[str, str] | None = None) -> str:
    rotulos = rotulos or {}
    return '<option value="">todas</option>' + "".join(
        f'<option value="{escape(v)}">{escape(rotulos.get(v, v))}</option>'
        for v in valores)


def _report_action(p, has_report: bool) -> str:
    if has_report:
        return _sheen_link(
            "ler relatório", f"/ai-radar/reports/{p.arxiv_id}/",
            classes="report-action", aria_label=f"ler relatório de {p.titulo}",
        )
    query = urlencode({
        "title": f"[report] {p.arxiv_id}",
        "body": (
            f"Generate a deep report for arXiv {p.arxiv_id}.\n\n"
            f"Paper: {p.titulo}\n\n"
            "Requested from the ai-radar archive.\n\n"
            "Credit protection: generation runs only when the repository "
            "owner opens this issue."
        ),
    })
    return _sheen_link(
        "gerar relatório",
        f"https://github.com/{REPORT_REPOSITORY}/issues/new?{query}",
        classes="report-action secondary",
        aria_label=f"gerar relatório de {p.titulo}",
        rel="nofollow",
    )


MESES = {
    "01": "jan", "02": "fev", "03": "mar", "04": "abr",
    "05": "mai", "06": "jun", "07": "jul", "08": "ago",
    "09": "set", "10": "out", "11": "nov", "12": "dez",
}


def _data_editorial(publicado: str) -> str:
    ano, mes, _ = publicado.split("-", 2)
    return f"{MESES.get(mes, mes)} {ano}"


def _linha(p, *, has_report: bool = False, initial_hidden: bool = False) -> str:
    cor = CORES_FAMILIA.get(p.familia, "currentColor")
    # `None` e desconhecido e vira travessao. Renderizar 0 aqui reintroduziria,
    # pela camada de apresentacao, o mesmo defeito que o pipeline consertou.
    cit = "—" if p.citations is None else str(p.citations)
    ganho = (f"{p.ganho_fator:g}x" if p.ganho_fator is not None else "—")
    # Valores de ordenacao viajam como ATRIBUTO, nao no texto visivel: a
    # celula mostra "—" e "2.3x", que nao sao numeros, e um JS que parseasse
    # o texto quebraria em silencio nos dois casos.
    #
    # Citacao desconhecida ordena como -1 e nao 0: mandar zero faria
    # "nao perguntamos" empatar com "ninguem citou", que e exatamente a
    # confusao que o pipeline inteiro existe para evitar.
    ord_cit = -1 if p.citations is None else p.citations
    ord_ganho = p.ganho_fator if p.ganho_fator is not None else -1
    texto = (
        f"{p.titulo} {p.resumo} {p.familia} {p.pratica} {p.arxiv_id}"
    ).lower()
    estado_inicial = ' data-inicial="oculta" hidden' if initial_hidden else ""
    return (
        f'<article class="linha paper-entry" data-id="{escape(p.arxiv_id)}" '
        f'data-familia="{escape(p.familia)}" data-pratica="{escape(p.pratica)}" '
        f'data-texto="{escape(texto)}" '
        f'data-impls="{p.independent_impls}" data-estrelas="{p.stars_total}" '
        f'data-citacoes="{ord_cit}" data-ganho="{ord_ganho:g}" '
        f'data-score="{p.score:g}"{estado_inicial}>'
        '<div class="entry-date">'
        f'<time datetime="{escape(p.publicado)}">{escape(_data_editorial(p.publicado))}</time>'
        f'<span>arXiv {escape(p.arxiv_id)}</span></div>'
        '<div class="entry-main">'
        '<div class="entry-taxonomy">'
        f'<span><i class="pt" style="background:{cor}"></i>'
        f'{escape(ROTULOS_FAMILIA.get(p.familia, p.familia))}</span>'
        f'<span class="tag {escape(p.pratica)}">'
        f'{escape(ROTULOS_PRATICA.get(p.pratica, p.pratica))}</span></div>'
        f'<h3><a href="https://arxiv.org/abs/{escape(p.arxiv_id)}" '
        'target="_blank" rel="noopener noreferrer">'
        f'{escape(p.titulo)}</a></h3>'
        f'<p class="paper-brief">{escape(p.resumo)}</p></div>'
        '<div class="evidence-fingerprint" aria-label="sinal de evidência">'
        '<span class="fingerprint-label">sinal observado</span>'
        f'<div><b>{p.independent_impls}</b><span>impl.</span></div>'
        f'<div><b>{p.stars_total}</b><span>estrelas</span></div>'
        f'<div><b>{cit}</b><span>citações</span></div>'
        f'<div><b>{ganho}</b><span>ganho</span></div></div>'
        f'<div class="entry-action">{_report_action(p, has_report)}'
        f'<a class="source-link" href="https://arxiv.org/abs/{escape(p.arxiv_id)}" '
        'target="_blank" rel="noopener noreferrer">paper original ↗</a></div>'
        '</article>'
    )


def _secao_tabela(d: SiteData, report_ids: set[str]) -> str:
    """Indice editorial com filtro por pratica e por familia.

    O de PRATICA e o primario: e ele que responde "o que eu adoto", que e a
    pergunta pela qual o leitor abriu a pagina. O de familia serve para
    navegar a literatura, nao para decidir.
    """
    praticas = sorted({p.pratica for p in d.pontos})
    ordenados = sorted(d.pontos, key=lambda p: -p.score)
    linhas = "".join(
        _linha(p, has_report=p.arxiv_id in report_ids,
               initial_hidden=index >= BRIEF_INITIAL_LIMIT)
        for index, p in enumerate(ordenados)
    )
    inicial = min(len(d.pontos), BRIEF_INITIAL_LIMIT)
    mostrar = (
        '<button type="button" class="sheen-button secondary show-all" '
        f'data-mostrar-todos>{_sheen_content(f"mostrar todos os {len(d.pontos)} papers")}'
        '</button>'
        if len(d.pontos) > BRIEF_INITIAL_LIMIT else ""
    )
    return (
        '<div class="filtros">'
        f'<div><label for="f-pratica">o que fazer</label>'
        f'<select id="f-pratica" data-filtro="pratica">'
        f'{_opcoes(praticas, ROTULOS_PRATICA)}'
        f"</select></div>"
        f'<div><label for="f-familia">família</label>'
        f'<select id="f-familia" data-filtro="familia">'
        f"{_opcoes(d.familias_presentes, ROTULOS_FAMILIA)}</select></div>"
        '<div><label for="f-busca">buscar</label>'
        '<input id="f-busca" type="search" data-busca '
        'placeholder="quantization, agent, cache..."></div>'
        f'<div class="contagem"><label>mostrando</label>'
        f'<span id="contador">{inicial} de {len(d.pontos)}</span></div>'
        "</div>"
        '<div class="index-sort" aria-label="ordenar índice">'
        '<span>ordenar por</span>'
        '<button type="button" data-ordenar="score">sinal</button>'
        '<button type="button" data-ordenar="impls">implementações</button>'
        '<button type="button" data-ordenar="estrelas">estrelas</button>'
        '<button type="button" data-ordenar="citacoes">citações</button>'
        '<button type="button" data-ordenar="ganho">ganho</button></div>'
        '<div class="research-index"><div class="index-head" aria-hidden="true">'
        '<span>publicado</span><span>paper e brief</span>'
        '<span>sinal</span><span>leitura</span></div>'
        f'<div class="paper-list" data-paper-list>{linhas}</div></div>{mostrar}'
    )


def _secao_destaque(d: SiteData) -> str:
    """O paper de maior score, aberto.

    Existe para tornar o numero auditavel: sem ver os repositorios e a regra
    que classificou cada um, "3 implementacoes independentes" e fe. E a
    heuristica de autoria e heuristica -- ela precisa poder ser conferida.
    """
    p = d.destaque
    if p is None:
        return '<p class="vazio">Nada no acervo ainda.</p>'

    if d.repos_do_destaque:
        itens = []
        for r in d.repos_do_destaque:
            if r["is_author"]:
                quem = f'autor — {escape(r["is_author_reason"] or "regra não registrada")}'
                classe = "quem"
            else:
                quem, classe = "independente", "indep"
            itens.append(
                f'<li><a href="https://github.com/{escape(r["full_name"])}">'
                f'{escape(r["full_name"])}</a>'
                f'<span class="num">{r["stars"]} estrelas</span>'
                f'<span class="{classe}">{quem}</span></li>'
            )
        repos = f'<ul class="repos">{"".join(itens)}</ul>'
    else:
        repos = ('<p class="nota">Nenhum repositório registrado para este '
                 "paper.</p>")

    ganho = ""
    if p.ganho_fator is not None:
        ganho = (f' · ganho {p.ganho_fator:g}x em {escape(p.ganho_eixo)} '
                 f"({ROTULO_ALEGACAO})")
    return (
        f'<div class="destaque"><h3>'
        f'<a href="https://arxiv.org/abs/{escape(p.arxiv_id)}">'
        f"{escape(p.titulo)}</a></h3>"
        f'<div class="meta">{escape(ROTULOS_FAMILIA.get(p.familia, p.familia))} · '
        f'{escape(ROTULOS_PRATICA.get(p.pratica, p.pratica))} · '
        f"{p.independent_impls} de {p.total_impls} implementações "
        f"independentes{ganho}</div>"
        f'<p class="resumo">{escape(p.resumo)}</p>{repos}</div>'
    )


def _secao_cortes(d: SiteData) -> str:
    """Todo corte contado chega ao leitor -- restricao global do projeto.

    A secao aparece mesmo vazia: um dia sem cortes e informacao, e some-la
    faria parecer que a contabilidade nao foi feita.
    """
    if d.cortes is None:
        lista = ('<p class="nota">A contagem de cortes não foi registrada '
                 'para esta edição.</p>')
    elif d.cortes:
        itens = "".join(
            f"<li><span>{escape(motivo.replace('_', ' '))}</span>"
            f"<b>{n}</b></li>"
            for motivo, n in sorted(d.cortes.items(), key=lambda kv: -kv[1])
        )
        lista = f'<ul class="cortes">{itens}</ul>'
    else:
        lista = '<p class="nota">Nenhum corte hoje.</p>'
    return (lista + f'<p class="nota">{d.rechecked_total} papers antigos '
                    f"foram re-consultados nesta execução.</p>")


def _pendente(qual: str) -> str:
    """Marcador das secoes que as tarefas 5 a 8 preenchem.

    A tarefa 4 entrega a pagina inteira com as secoes vazias de proposito:
    ajustar identidade visual com elas vazias custa uma fracao de ajustar
    depois de preenchidas.
    """
    return f'<p class="futuro">{qual}</p>'


def render_site(
    dados: SiteData, *, edicao: bool = False,
    report_ids: set[str] | None = None,
) -> str:
    report_ids = report_ids or set()
    if not dados.pontos:
        corpo = '<p class="vazio">Nenhum paper no acervo ainda.</p>'
    else:
        corpo = "".join((
            _secao("Índice de pesquisa",
                   "Os 30 sinais mais fortes abrem esta edição. Cada entrada "
                   "traz um brief, o paper original e o caminho para uma "
                   "análise completa quando ela merecer o custo.",
                   _secao_tabela(dados, report_ids), section_id="acervo"),
            _secao("Sinais do acervo",
                   "Três leituras do mesmo conjunto: adoção contra atenção, "
                   "cadência por família e, quando a cobertura permite, o "
                   "ganho que os próprios autores declaram.",
                   _secao_graficos(dados), section_id="sinais"),
            _secao("Uma técnica, de ponta a ponta",
                   "O paper de maior score, aberto: os repositórios "
                   "encontrados e a regra que classificou cada um.",
                   _secao_destaque(dados)),
            _secao("O que ficou de fora",
                   "Todo corte é contado e chega ao leitor.",
                   _secao_cortes(dados)),
        ))

    return (
        "<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        '<link rel="alternate" type="application/rss+xml" title="ai-radar" '
        'href="/ai-radar/feed.xml">'
        f"<title>ai-radar — {'edição ' if edicao else ''}{escape(dados.dia)}</title>"
        f"<style>{_CSS}</style></head><body>"
        '<canvas id="fundo" aria-hidden="true"></canvas>'
        '<a class="pular" href="#conteudo">pular para o conteúdo</a>'
        '<div class="envelope">'
        f"{_nav('edicoes' if edicao else 'acervo')}"
        f"{_cabecalho(dados, edicao=edicao)}"
        f'<main id="conteudo">'
        f"{_secao_leitura(dados)}"
        f"{corpo}"
        f'<section id="metodo" class="enquadramento">{_ENQUADRAMENTO}</section>'
        "</main>"
        "<footer>Gerado pelo próprio pipeline. Sem framework, sem build, "
        "sem requisição externa.</footer>"
        '</div><script src="/ai-radar/assets/d3-7.9.0.min.js"></script>'
        '<script src="/ai-radar/assets/observable-plot-0.6.17.min.js">'
        f'</script><script>{_BACKGROUND_JS}</script><script>{_JS}</script>'
        f'<script>{_CHART_JS}</script></body></html>'
    )


def _pagina_estatica(titulo: str, atual: str, dia: str, corpo: str,
                     *, heading: str | None = None, kicker: str | None = None,
                     deck: str | None = None, back_href: str | None = None,
                     extra_script: str = "") -> str:
    """Casca das paginas de distribuicao.

    Compartilha a tipografia e a navegacao do acervo, mas nao carrega o JS da
    tabela. Links e texto continuam funcionando com qualquer bloqueador de
    script. Relatorios podem receber aprimoramento local, sem requisicao
    externa, para progresso de leitura e sumario ativo.
    """
    back = (
        f'<a class="back-link" href="{escape(back_href)}">← voltar ao índice</a>'
        if back_href else ""
    )
    header_class = "static-masthead article-masthead" if deck else "static-masthead"
    main_class = "pagina article-page" if deck else "pagina"
    header_deck = f'<p class="article-deck">{escape(deck)}</p>' if deck else ""
    enhancement = f'<script>{extra_script}</script>' if extra_script else ""
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="alternate" type="application/rss+xml" title="ai-radar" '
        'href="/ai-radar/feed.xml">'
        f'<title>{escape(titulo)}</title><style>{_CSS}</style></head><body>'
        '<canvas id="fundo" aria-hidden="true"></canvas>'
        '<a class="pular" href="#conteudo">pular para o conteúdo</a>'
        f'<div class="envelope">{_nav(atual)}'
        f'<header class="{header_class}">{back}'
        f'<p class="hero-eyebrow">{escape(kicker or f"atualizado em {dia}")}</p>'
        f'<h1>{escape(heading or titulo)}</h1>{header_deck}</header>'
        f'<main id="conteudo" class="{main_class}">{corpo}</main>'
        '<footer>Gerado pelo próprio pipeline. Sem framework, sem build, '
        f'sem requisição externa.</footer></div><script>{_BACKGROUND_JS}</script>'
        f'{enhancement}</body></html>'
    )


def render_editions(dias: list[str], dia: str) -> str:
    if dias:
        itens = "".join(
            f'<li><a href="/ai-radar/edicoes/{escape(d)}/">'
            f'<time datetime="{escape(d)}">{escape(d)}</time></a></li>'
            for d in sorted(dias, reverse=True)
        )
        lista = f'<ol class="edicoes">{itens}</ol>'
    else:
        lista = '<p class="vazio">Nenhuma edição publicada ainda.</p>'
    corpo = (
        '<section><h2>Edições diárias</h2>'
        '<p>Cada URL preserva o recorte de papers entregue naquele dia. O '
        'acervo principal continua mostrando a observação mais recente.</p>'
        f'{lista}</section>'
    )
    return _pagina_estatica("edições — ai-radar", "edicoes", dia, corpo)


def render_about(dia: str, *, papers: int, edicoes: int) -> str:
    corpo = (
        '<section><h2>O que este radar mede</h2>'
        '<p>O ai-radar procura papers de inferência eficiente e de agentes e '
        'conta quantos repositórios independentes os implementam. Repositórios '
        'dos autores são separados por uma heurística publicada junto do dado.</p>'
        '<p>O score favorece implementação independente com pouca atenção. '
        'Papers acima de 1000 estrelas ou 200 citações ficam fora porque já '
        'deixaram de ser material de radar.</p></section>'
        '<section><h2>O que ele não mede</h2>'
        '<p>Nenhum resultado foi reproduzido. Ganhos vêm do resumo do paper e '
        'aparecem rotulados como alegação dos autores. O radar também não '
        'explica por que uma técnica recebeu implementações e não prevê quais '
        'papers vão crescer.</p></section>'
        '<section><h2>Estado do acervo</h2>'
        f'<p>{papers} papers em {edicoes} edições. O banco, o código do score '
        'e as regras de corte ficam versionados no mesmo repositório.</p></section>'
    )
    return _pagina_estatica("sobre — ai-radar", "about", dia, corpo)


def _lista_report(items: list[str], *, ordered: bool = False) -> str:
    if not items:
        return '<p class="nota">Não informado no paper.</p>'
    tag = "ol" if ordered else "ul"
    return f'<{tag}>' + "".join(f'<li>{escape(item)}</li>' for item in items) + f'</{tag}>'


def _render_formula_walkthrough(
    item: FormulaWalkthrough, source_url: str, index: int,
) -> str:
    if item.status != "exact":
        return (
            '<article class="formula-state">'
            f'<span>{escape(ROTULOS_ESTADO_FORMULA[item.status])}</span>'
            f'<p>{escape(item.plain_language)}</p></article>'
        )

    role = ROTULOS_PAPEL_FORMULA[item.role]
    variables = "".join(
        '<div>'
        f'<dt><code>{escape(variable.symbol)}</code></dt>'
        f'<dd>{escape(variable.meaning)}'
        + (f' <span>{escape(variable.unit)}</span>' if variable.unit else "")
        + '</dd></div>'
        for variable in item.variables
    )
    glossary = (
        f'<dl class="formula-variables">{variables}</dl>' if variables else ""
    )
    steps = (
        '<ol class="formula-steps">'
        + "".join(f'<li>{escape(step)}</li>' for step in item.derivation_steps)
        + '</ol>'
        if item.derivation_steps else ""
    )
    assumptions = (
        '<div class="formula-assumptions"><span>hipóteses do exemplo</span>'
        + _lista_report(item.assumptions) + '</div>'
        if item.assumptions else ""
    )
    worked = ""
    if item.worked_example is not None:
        inputs = ", ".join(
            f"{name}={value:g}" for name, value in item.worked_example.inputs.items()
        )
        worked = (
            '<figure class="worked-example">'
            '<figcaption>cálculo ilustrativo do AI Radar</figcaption>'
            + (f'<code>{escape(inputs)}</code>' if inputs else "")
            + f'<p>{escape(item.worked_example.explanation)}</p>'
            f'<samp>{escape(item.worked_example.expression)} = '
            f'{escape(item.worked_example.result)}</samp></figure>'
        )
    source = (
        '<blockquote class="formula-source">'
        f'{escape(item.source_excerpt)}</blockquote>'
        f'<a class="evidence-link" href="{escape(source_url)}#page={item.source_page}" '
        'target="_blank" rel="noopener noreferrer">'
        f'abrir fórmula na página {item.source_page} do PDF</a>'
    )
    return (
        f'<article class="formula-card" id="formula-{index}">'
        f'<span class="exhibit-number">fórmula {index:02d} · {escape(role)}</span>'
        f'<pre class="formula-latex"><code>{escape(item.latex)}</code></pre>'
        f'<p class="formula-meaning">{escape(item.plain_language)}</p>'
        f'{glossary}{steps}{worked}{assumptions}{source}</article>'
    )


def _render_technical_core(core: TechnicalCore, source_url: str) -> str:
    walkthroughs = "".join(
        _render_formula_walkthrough(item, source_url, index)
        for index, item in enumerate(core.walkthroughs, 1)
    )
    return (
        '<div class="technical-core-summary">'
        f'<span>{escape(ROTULOS_NUCLEO[core.kind])}</span>'
        f'<p>{escape(core.summary)}</p></div>'
        f'<div class="formula-stack">{walkthroughs}</div>'
    )


def render_report(document: ReportDocument) -> str:
    r = document.report
    evidence_items = []
    for index, item in enumerate(r.evidence, 1):
        if item.source_page is not None and item.source_excerpt:
            source = (
                f'<blockquote>{escape(item.source_excerpt)}</blockquote>'
                f'<a class="evidence-link" href="{escape(document.source_url)}'
                f'#page={item.source_page}" target="_blank" rel="noopener noreferrer" '
                f'aria-label="Abrir página {item.source_page} do PDF">'
                f'abrir página {item.source_page} no PDF</a>'
            )
        else:
            source = (
                '<span class="evidence-missing">fonte não localizada '
                'automaticamente no PDF</span>'
            )
        facts = "".join((
            (f'<div><dt>resultado</dt><dd>{escape(item.result)}</dd></div>'
             if item.result else ""),
            (f'<div><dt>baseline</dt><dd>{escape(item.baseline)}</dd></div>'
             if item.baseline else ""),
            (f'<div><dt>condições</dt><dd>{escape(item.conditions)}</dd></div>'
             if item.conditions else ""),
        ))
        evidence_items.append(
            f'<li class="evidence-exhibit" id="evidencia-{index}">'
            f'<span class="exhibit-number">evidência {index:02d}</span>'
            f'<h3>{escape(item.claim)}</h3>'
            f'<dl class="evidence-facts">{facts}</dl>{source}</li>'
        )
    evidence = "".join(evidence_items) or (
        '<li class="evidence-exhibit empty-evidence">'
        'Nenhuma evidência quantificada foi localizada.</li>'
    )
    setup = ", ".join(ROTULOS_SETUP[value] for value in r.software_setup)
    setup = setup or "não informado"
    toc_entries = (
        ("infra", "Infra para testar"),
        ("problema", "Problema"),
        ("mecanismo", "Mecanismo"),
        ("evidencia", "Evidência"),
        ("teste", "Menor teste"),
        ("nucleo", "Da equação ao teste"),
        ("riscos", "Riscos"),
        ("perguntas", "Perguntas abertas"),
    )
    toc = "".join(
        f'<a href="#{section_id}">{escape(label)}</a>'
        for section_id, label in toc_entries
    )

    def section_heading(number: int, title: str, label: str) -> str:
        return (
            '<div class="report-section-head">'
            f'<span>{number:02d}</span><div><p>{escape(label)}</p>'
            f'<h2>{escape(title)}</h2></div></div>'
        )

    corpo = (
        '<div class="report-progress" aria-hidden="true">'
        '<span data-report-progress></span></div>'
        '<div class="report-layout">'
        '<aside class="report-toc" aria-label="Nesta análise">'
        '<p>nesta análise</p>'
        f'<nav data-report-toc>{toc}</nav></aside>'
        '<article class="report">'
        '<div class="report-bar">'
        '<div class="report-provenance">'
        f'<span>análise gerada com {escape(document.model)}</span>'
        f'<b>{escape(document.generated_at[:10])} · leitura de 5 min</b></div>'
        '<div class="report-links">'
        f'<a href="https://arxiv.org/abs/{escape(document.arxiv_id)}" '
        'target="_blank" rel="noopener noreferrer">abrir página do paper ↗</a>'
        f'<a href="{escape(document.source_url)}" target="_blank" '
        'rel="noopener noreferrer">abrir PDF completo ↗</a></div></div>'
        '<details class="report-toc-mobile" open><summary>nesta análise</summary>'
        f'<nav data-report-toc>{toc}</nav></details>'
        '<figure id="infra" class="report-section infra-exhibit">'
        + section_heading(1, "O custo antes da leitura", "mapa de execução")
        + '<p class="report-section-deck">O teste mínimo procura invalidar a '
        'ideia no seu workload. A coluna do experimento descreve a infraestrutura '
        'por trás da evidência publicada; ela não é uma recomendação.</p>'
        '<div class="infra-grid">'
        f'<div><span>teste mínimo</span><b>{escape(ROTULOS_INFRA[r.validation_tier])}</b></div>'
        f'<div><span>experimento do paper</span><b>{escape(ROTULOS_INFRA[r.evidence_tier])}</b></div>'
        f'<div><span>base da classificação</span><b>{escape(ROTULOS_BASE_INFRA[r.infrastructure_basis])}</b></div>'
        f'<div><span>treino</span><b>{escape(ROTULOS_TREINO[r.training_required])}</b></div>'
        '</div><figcaption><span>exhibit 01</span> Infra do menor teste útil '
        'comparada com a infra que sustenta as alegações do paper.</figcaption></figure>'
        '<section id="problema" class="report-section">'
        + section_heading(2, "O problema", "o que precisa mudar")
        + f'<p>{escape(r.problem)}</p></section>'
        '<section id="mecanismo" class="report-section">'
        + section_heading(3, "Como funciona", "a troca técnica")
        + f'<p>{escape(r.mechanism)}</p>'
        f'<p class="setup-note"><span>setup</span>{escape(setup)}</p></section>'
        '<section id="evidencia" class="report-section">'
        + section_heading(4, "Evidência relatada", "o que o PDF sustenta")
        + f'<ol class="evidence">{evidence}</ol></section>'
        '<section id="teste" class="report-section">'
        + section_heading(5, "Menor teste útil", "como tentar refutar")
        + _lista_report(r.minimum_test, ordered=True) + '</section>'
        '<section id="nucleo" class="report-section">'
        + section_heading(6, "Da equação ao teste", "núcleo técnico verificável")
        + _render_technical_core(r.technical_core, document.source_url) + '</section>'
        '<section id="riscos" class="report-section">'
        + section_heading(7, "Onde pode quebrar", "riscos do teste e da adoção")
        + _lista_report(r.main_risks) + '</section>'
        '<section id="perguntas" class="report-section">'
        + section_heading(8, "Antes de adotar, descubra", "perguntas abertas")
        + _lista_report(r.unanswered_questions) + '</section>'
        '<p class="report-source">Gerado de '
        f'<a href="{escape(document.source_url)}">PDF do arXiv</a> com '
        f'{escape(document.model)} em {escape(document.generated_at[:10])}. '
        'Este relatório não reproduz o experimento.</p>'
        '</article></div>'
        '<a class="report-to-top" data-report-top href="#conteudo" '
        'aria-label="Voltar ao início da análise">↑</a>'
    )
    return _pagina_estatica(
        f"{document.title} — relatório — ai-radar", "acervo",
        document.generated_at[:10], corpo, heading=document.title,
        kicker=(f"deep report · arXiv {document.arxiv_id} · "
                f"{document.generated_at[:10]}"),
        deck=r.one_sentence, back_href="/ai-radar/#acervo",
        extra_script=_REPORT_JS,
    )
