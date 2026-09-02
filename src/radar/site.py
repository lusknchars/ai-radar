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
from .public_labels import (
    AUTHORSHIP_REASON_LABELS, CUT_LABELS, FAMILY_LABELS as ROTULOS_FAMILIA,
    FORMULA_ROLE_LABELS as ROTULOS_PAPEL_FORMULA,
    FORMULA_STATUS_LABELS as ROTULOS_ESTADO_FORMULA,
    GAIN_AXIS_LABELS, INFRASTRUCTURE_BASIS_LABELS as ROTULOS_BASE_INFRA,
    INFRASTRUCTURE_LABELS as ROTULOS_INFRA,
    PRACTICE_LABELS as ROTULOS_PRATICA,
    SOFTWARE_SETUP_LABELS as ROTULOS_SETUP,
    TECHNICAL_CORE_LABELS as ROTULOS_NUCLEO,
    TRAINING_LABELS as ROTULOS_TREINO, public_label,
)
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

# Contrato com o leitor. Escrito a mao e versionado -- nao e gerado, e nao
# muda com o dado do dia.
_ENQUADRAMENTO = (
    "<p>AI Radar tracks one signal: how many <strong>independent "
    "implementations</strong> a paper attracts on GitHub after author-owned "
    "repositories are removed. Independent implementation is a stronger sign "
    "of engineering relevance than attention alone.</p>"
    "<p>It <strong>does not claim</strong> that a method works. AI Radar runs "
    "no reproduction benchmarks. Reported gains remain author claims until "
    "independently tested. Papers above the attention threshold are excluded "
    "because this publication is designed to identify research before "
    "consensus forms.</p>"
)


def _nav(atual: str) -> str:
    itens = (
        ("acervo", "/ai-radar/#acervo", "research"),
        ("sinais", "/ai-radar/#sinais", "signals"),
        ("edicoes", "/ai-radar/edicoes/", "editions"),
        ("about", "/ai-radar/about.html", "methodology"),
        ("rss", "/ai-radar/feed.xml", "RSS"),
    )
    links = "".join(
        f'<a href="{href}"'
        f'{" aria-current=\"page\"" if chave == atual else ""}>{rotulo}</a>'
        for chave, href, rotulo in itens
    )
    return f'<nav class="nav" aria-label="Primary navigation">{links}</nav>'


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
    contexto = "archived edition" if edicao else "research intelligence"
    return (
        '<header class="masthead publication-head"><div class="hero-copy">'
        f'<p class="hero-eyebrow">{contexto} · {escape(d.dia)}</p>'
        '<h1><span class="marca">AI Radar · Research Intelligence</span>'
        'Find the AI research<br><em>worth testing.</em></h1>'
        '<p class="hero-deck">Evidence-led paper briefs for engineers deciding '
        'where to spend compute, budget, and reading time. Each brief separates '
        'the method, the independent adoption signal, and the practical cost '
        'of validation.</p>'
        f'{_sheen_link("Explore the research", "#acervo")}</div>'
        '<dl class="edition-ledger" aria-label="Edition summary">'
        f'<div><dt>edition</dt><dd>{escape(d.dia)}</dd></div>'
        f'<div><dt>{"brief" if len(d.pontos) == 1 else "briefs"}</dt>'
        f'<dd>{len(d.pontos)}</dd></div>'
        f'<div><dt>{"research area" if len(d.familias_presentes) == 1 else "research areas"}</dt>'
        f'<dd>{len(d.familias_presentes)}</dd></div>'
        f'<div><dt>{"independent implementation" if impls == 1 else "independent implementations"}</dt>'
        f'<dd>{impls}</dd></div>'
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
            "gain_axis": public_label(GAIN_AXIS_LABELS, p.ganho_eixo),
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
    nota = (f'<p class="nota">Papers above {lim.broke_out_stars} stars or '
            f"{lim.broke_out_citations} citations are not scored. They have "
            f"already broken through the attention threshold, while AI Radar "
            f"is designed to identify earlier signals.</p>")
    return botoes and (
        f'<div class="eixos chart-controls" aria-label="Horizontal axis">'
        f'<span>compare by</span>{botoes}</div>'
        f'<div class="chart-scroll" data-plot-panel="frontier" tabindex="0" '
        f'aria-label="Research frontier chart; scroll horizontally to explore">'
        '<div class="plot-enhancement" data-plot-host="frontier" hidden></div>'
        f'<div class="plot-fallback">{graficos}</div></div>'
        f'{_chart_payload("frontier", _point_chart_data(d))}{nota}'
    )


# Abaixo disso a secao de avanco nao e construida: grafico sobre dado ralo e
# pior que grafico ausente. Ver spec do jornal, secao 3.4.
COBERTURA_MINIMA = 0.35

ROTULO_ALEGACAO = "reported by the authors; not independently verified"
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
    paper_label = "paper" if len(d.pontos) == 1 else "papers"
    report_verb = "reports" if com == 1 else "report"
    return (
        '<div class="chart-scroll" data-plot-panel="gain" tabindex="0" '
        'aria-label="Reported gain chart; scroll horizontally to explore">'
        '<div class="plot-enhancement" data-plot-host="gain" hidden></div>'
        f'<div class="plot-fallback">{render_avanco(d.pontos, CORES_FAMILIA)}</div>'
        '</div>'
        f'{_chart_payload("gain", _point_chart_data(d))}'
        f'<p class="nota">{com} of {len(d.pontos)} {paper_label} {report_verb} a quantified '
        f'gain. The scale is logarithmic; a research-area trend line appears '
        f'only with at least five papers in the quarter.</p>'
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
        'aria-label="Research areas over time; scroll horizontally to explore">'
        '<div class="plot-enhancement" data-plot-host="families" hidden></div>'
        f'<div class="plot-fallback">{grafico}</div></div>'
        f'{_chart_payload("families", values)}'
        '<p class="nota">Every panel uses the same calendar and vertical scale. '
        'An empty column means no papers were recorded.</p>'
    )


def _secao_graficos(d: SiteData) -> str:
    """Um único caderno visual, com uma legenda e ordem de leitura explícita."""
    cartoes = [
        _cartao_grafico(
            "01 · attention × adoption", "The research frontier",
            "Look to the upper left for independent implementation before mass attention.",
            _secao_fronteira(d), classe="chart-card--frontier",
        ),
        _cartao_grafico(
            "02 · cadence", "Research areas over time",
            "Compare monthly publication volume on a shared scale and calendar.",
            _secao_familias(d), classe="chart-card--families",
        ),
    ]
    avanco = _secao_avanco(d)
    if avanco:
        cartoes.append(_cartao_grafico(
            "03 · reported results", "Claimed performance gains",
            f"Gains stated in the abstract: {ROTULO_ALEGACAO}.",
            avanco, classe="chart-card--gain",
        ))
    return (
        '<div class="chart-suite">'
        '<div class="chart-shared-legend"><span>color = research area</span>'
        f'{_legenda(d)}</div>{"".join(cartoes)}</div>'
    )


def _opcoes(valores: list[str], rotulos: dict[str, str] | None = None) -> str:
    rotulos = rotulos or {}
    return '<option value="">all</option>' + "".join(
        f'<option value="{escape(v)}">{escape(rotulos.get(v, v))}</option>'
        for v in valores)


def _report_action(p, has_report: bool) -> str:
    if has_report:
        return _sheen_link(
            "Read deep report", f"/ai-radar/reports/{p.arxiv_id}/",
            classes="report-action", aria_label=f"Read deep report for {p.titulo}",
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
        "Generate deep report",
        f"https://github.com/{REPORT_REPOSITORY}/issues/new?{query}",
        classes="report-action secondary",
        aria_label=f"Generate deep report for {p.titulo}",
        rel="nofollow",
    )


MESES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
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
        '<div class="evidence-fingerprint" aria-label="Evidence signal">'
        '<span class="fingerprint-label">observed signal</span>'
        f'<div><b>{p.independent_impls}</b><span>impl.</span></div>'
        f'<div><b>{p.stars_total}</b><span>stars</span></div>'
        f'<div><b>{cit}</b><span>citations</span></div>'
        f'<div><b>{ganho}</b><span>gain</span></div></div>'
        f'<div class="entry-action">{_report_action(p, has_report)}'
        f'<a class="source-link" href="https://arxiv.org/abs/{escape(p.arxiv_id)}" '
        'target="_blank" rel="noopener noreferrer">Original paper ↗</a></div>'
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
        f'data-mostrar-todos>{_sheen_content(f"Show all {len(d.pontos)} papers")}'
        '</button>'
        if len(d.pontos) > BRIEF_INITIAL_LIMIT else ""
    )
    return (
        '<div class="filtros">'
        f'<div><label for="f-pratica">recommendation</label>'
        f'<select id="f-pratica" data-filtro="pratica">'
        f'{_opcoes(praticas, ROTULOS_PRATICA)}'
        f"</select></div>"
        f'<div><label for="f-familia">research area</label>'
        f'<select id="f-familia" data-filtro="familia">'
        f"{_opcoes(d.familias_presentes, ROTULOS_FAMILIA)}</select></div>"
        '<div><label for="f-busca">search</label>'
        '<input id="f-busca" type="search" data-busca '
        'placeholder="quantization, agent, cache..."></div>'
        f'<div class="contagem"><label>showing</label>'
        f'<span id="contador">{inicial} of {len(d.pontos)}</span></div>'
        "</div>"
        '<div class="index-sort" aria-label="Sort research index">'
        '<span>sort by</span>'
        '<button type="button" data-ordenar="score">signal</button>'
        '<button type="button" data-ordenar="impls">implementations</button>'
        '<button type="button" data-ordenar="estrelas">stars</button>'
        '<button type="button" data-ordenar="citacoes">citations</button>'
        '<button type="button" data-ordenar="ganho">gain</button></div>'
        '<div class="research-index"><div class="index-head" aria-hidden="true">'
        '<span>published</span><span>paper and brief</span>'
        '<span>signal</span><span>analysis</span></div>'
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
        return '<p class="vazio">No papers are available yet.</p>'

    if d.repos_do_destaque:
        itens = []
        for r in d.repos_do_destaque:
            if r["is_author"]:
                reason = r["is_author_reason"] or "rule not recorded"
                quem = f'author: {escape(public_label(AUTHORSHIP_REASON_LABELS, reason))}'
                classe = "quem"
            else:
                quem, classe = "independent", "indep"
            stars = "star" if r["stars"] == 1 else "stars"
            itens.append(
                f'<li><a href="https://github.com/{escape(r["full_name"])}">'
                f'{escape(r["full_name"])}</a>'
                f'<span class="num">{r["stars"]} {stars}</span>'
                f'<span class="{classe}">{quem}</span></li>'
            )
        repos = f'<ul class="repos">{"".join(itens)}</ul>'
    else:
        repos = '<p class="nota">No repositories are recorded for this paper.</p>'

    ganho = ""
    if p.ganho_fator is not None:
        gain_axis = public_label(GAIN_AXIS_LABELS, p.ganho_eixo)
        ganho = (f' · {p.ganho_fator:g}x gain in {escape(gain_axis)} '
                 f"({ROTULO_ALEGACAO})")
    implementations = "implementation" if p.total_impls == 1 else "implementations"
    independent_verb = "is" if p.independent_impls == 1 else "are"
    return (
        f'<div class="destaque"><h3>'
        f'<a href="https://arxiv.org/abs/{escape(p.arxiv_id)}">'
        f"{escape(p.titulo)}</a></h3>"
        f'<div class="meta">{escape(ROTULOS_FAMILIA.get(p.familia, p.familia))} · '
        f'{escape(ROTULOS_PRATICA.get(p.pratica, p.pratica))} · '
        f"{p.independent_impls} of {p.total_impls} {implementations} {independent_verb} "
        f"independent{ganho}</div>"
        f'<p class="resumo">{escape(p.resumo)}</p>{repos}</div>'
    )


def _secao_cortes(d: SiteData) -> str:
    """Todo corte contado chega ao leitor -- restricao global do projeto.

    A secao aparece mesmo vazia: um dia sem cortes e informacao, e some-la
    faria parecer que a contabilidade nao foi feita.
    """
    if d.cortes is None:
        lista = '<p class="nota">Exclusion counts were not recorded for this edition.</p>'
    elif d.cortes:
        itens = "".join(
            f"<li><span>{escape(public_label(CUT_LABELS, motivo))}</span>"
            f"<b>{n}</b></li>"
            for motivo, n in sorted(d.cortes.items(), key=lambda kv: -kv[1])
        )
        lista = f'<ul class="cortes">{itens}</ul>'
    else:
        lista = '<p class="nota">No papers were excluded today.</p>'
    papers = "paper" if d.rechecked_total == 1 else "papers"
    verb = "was" if d.rechecked_total == 1 else "were"
    return (lista + f'<p class="nota">{d.rechecked_total} previously indexed {papers} '
                    f"{verb} rechecked in this run.</p>")


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
        corpo = '<p class="vazio">No papers are available yet.</p>'
    else:
        corpo = "".join((
            _secao("Research index",
                   "The 30 strongest signals lead this edition. Each entry "
                   "provides a decision-ready brief, the original paper, and "
                   "an on-demand deep report when the evidence justifies it.",
                   _secao_tabela(dados, report_ids), section_id="acervo"),
            _secao("Research signals",
                   "Three views of the same evidence: adoption against "
                   "attention, publication cadence by research area, and "
                   "reported gains when coverage is sufficient.",
                   _secao_graficos(dados), section_id="sinais"),
            _secao("Method under scrutiny",
                   "Inspect the highest-ranked paper, every repository behind "
                   "its signal, and the rule used to classify each one.",
                   _secao_destaque(dados)),
            _secao("Exclusions and controls",
                   "Every exclusion is counted and published.",
                   _secao_cortes(dados)),
        ))

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        '<link rel="alternate" type="application/rss+xml" title="ai-radar" '
        'href="/ai-radar/feed.xml">'
        f"<title>AI Radar · {'Edition ' if edicao else ''}{escape(dados.dia)}</title>"
        f"<style>{_CSS}</style></head><body>"
        '<canvas id="fundo" aria-hidden="true"></canvas>'
        '<a class="pular" href="#conteudo">Skip to content</a>'
        '<div class="envelope">'
        f"{_nav('edicoes' if edicao else 'acervo')}"
        f"{_cabecalho(dados, edicao=edicao)}"
        f'<main id="conteudo">'
        f"{_secao_leitura(dados)}"
        f"{corpo}"
        f'<section id="metodo" class="enquadramento">{_ENQUADRAMENTO}</section>'
        "</main>"
        "<footer>Generated by the AI Radar pipeline. No framework, build step, "
        "or remote asset request.</footer>"
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
        f'<a class="back-link" href="{escape(back_href)}">← Back to research index</a>'
        if back_href else ""
    )
    header_class = "static-masthead article-masthead" if deck else "static-masthead"
    main_class = "pagina article-page" if deck else "pagina"
    header_deck = f'<p class="article-deck">{escape(deck)}</p>' if deck else ""
    enhancement = f'<script>{extra_script}</script>' if extra_script else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="alternate" type="application/rss+xml" title="ai-radar" '
        'href="/ai-radar/feed.xml">'
        f'<title>{escape(titulo)}</title><style>{_CSS}</style></head><body>'
        '<canvas id="fundo" aria-hidden="true"></canvas>'
        '<a class="pular" href="#conteudo">Skip to content</a>'
        f'<div class="envelope">{_nav(atual)}'
        f'<header class="{header_class}">{back}'
        f'<p class="hero-eyebrow">{escape(kicker or f"Updated {dia}")}</p>'
        f'<h1>{escape(heading or titulo)}</h1>{header_deck}</header>'
        f'<main id="conteudo" class="{main_class}">{corpo}</main>'
        '<footer>Generated by the AI Radar pipeline. No framework, build step, '
        f'or remote asset request.</footer></div><script>{_BACKGROUND_JS}</script>'
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
        lista = '<p class="vazio">No editions have been published yet.</p>'
    corpo = (
        '<section><h2>Daily editions</h2>'
        '<p>Each permanent URL preserves the papers published on that date. '
        'The main index always reflects the latest observation.</p>'
        f'{lista}</section>'
    )
    return _pagina_estatica("Editions · AI Radar", "edicoes", dia, corpo)


def render_about(dia: str, *, papers: int, edicoes: int) -> str:
    corpo = (
        '<section><h2>What AI Radar measures</h2>'
        '<p>AI Radar tracks research in efficient inference and AI agents, then '
        'counts the independent repositories that implement each paper. '
        'Author-owned repositories are separated using a published heuristic.</p>'
        '<p>The score rewards independent implementation before mass attention. '
        'Papers above 1,000 stars or 200 citations are excluded because they no '
        'longer represent an early research signal.</p></section>'
        '<section><h2>What it does not measure</h2>'
        '<p>AI Radar does not reproduce experimental results. Performance gains '
        'come from the paper and are labeled as author-reported. The system does '
        'not explain why implementations appear or predict which papers will grow.</p>'
        '</section><section><h2>Archive status</h2>'
        f'<p>{papers} papers across {edicoes} editions. The database, scoring '
        'code, and exclusion rules are versioned in the same repository.</p></section>'
    )
    return _pagina_estatica("Methodology · AI Radar", "about", dia, corpo)


def _lista_report(items: list[str], *, ordered: bool = False) -> str:
    if not items:
        return '<p class="nota">Not reported in the paper.</p>'
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
        '<div class="formula-assumptions"><span>example assumptions</span>'
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
            '<figcaption>AI Radar worked example</figcaption>'
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
        f'Open formula on page {item.source_page} of the PDF</a>'
    )
    return (
        f'<article class="formula-card" id="formula-{index}">'
        f'<span class="exhibit-number">formula {index:02d} · {escape(role)}</span>'
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
                f'aria-label="Open page {item.source_page} of the PDF">'
                f'Open page {item.source_page} in the PDF</a>'
            )
        else:
            source = (
                '<span class="evidence-missing">Source not located '
                'automatically in the PDF</span>'
            )
        facts = "".join((
            (f'<div><dt>result</dt><dd>{escape(item.result)}</dd></div>'
             if item.result else ""),
            (f'<div><dt>baseline</dt><dd>{escape(item.baseline)}</dd></div>'
             if item.baseline else ""),
            (f'<div><dt>conditions</dt><dd>{escape(item.conditions)}</dd></div>'
             if item.conditions else ""),
        ))
        evidence_items.append(
            f'<li class="evidence-exhibit" id="evidencia-{index}">'
            f'<span class="exhibit-number">evidence {index:02d}</span>'
            f'<h3>{escape(item.claim)}</h3>'
            f'<dl class="evidence-facts">{facts}</dl>{source}</li>'
        )
    evidence = "".join(evidence_items) or (
        '<li class="evidence-exhibit empty-evidence">'
        'No quantified evidence was located.</li>'
    )
    setup = ", ".join(ROTULOS_SETUP[value] for value in r.software_setup)
    setup = setup or "not reported"
    toc_entries = (
        ("infra", "Infrastructure"),
        ("problema", "Problem"),
        ("mecanismo", "Mechanism"),
        ("evidencia", "Evidence"),
        ("teste", "Minimum test"),
        ("nucleo", "From equation to test"),
        ("riscos", "Failure modes"),
        ("perguntas", "Open questions"),
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
        '<aside class="report-toc" aria-label="In this analysis">'
        '<p>in this analysis</p>'
        f'<nav data-report-toc>{toc}</nav></aside>'
        '<article class="report">'
        '<div class="report-bar">'
        '<div class="report-provenance">'
        f'<span>analysis generated with {escape(document.model)}</span>'
        f'<b>{escape(document.generated_at[:10])} · 5 min read</b></div>'
        '<div class="report-links">'
        f'<a href="https://arxiv.org/abs/{escape(document.arxiv_id)}" '
        'target="_blank" rel="noopener noreferrer">Open paper page ↗</a>'
        f'<a href="{escape(document.source_url)}" target="_blank" '
        'rel="noopener noreferrer">Open full PDF ↗</a></div></div>'
        '<details class="report-toc-mobile" open><summary>in this analysis</summary>'
        f'<nav data-report-toc>{toc}</nav></details>'
        '<figure id="infra" class="report-section infra-exhibit">'
        + section_heading(1, "Cost before commitment", "execution profile")
        + '<p class="report-section-deck">The minimum test is designed to '
        'disprove the method on your workload. The original experiment column '
        'describes the infrastructure behind the published evidence, not a '
        'recommendation.</p>'
        '<div class="infra-grid">'
        f'<div><span>minimum useful test</span><b>{escape(ROTULOS_INFRA[r.validation_tier])}</b></div>'
        f'<div><span>original experiment</span><b>{escape(ROTULOS_INFRA[r.evidence_tier])}</b></div>'
        f'<div><span>classification basis</span><b>{escape(ROTULOS_BASE_INFRA[r.infrastructure_basis])}</b></div>'
        f'<div><span>training requirement</span><b>{escape(ROTULOS_TREINO[r.training_required])}</b></div>'
        '</div><figcaption><span>exhibit 01</span> Validation tier compared with '
        'the evidence tier supporting the paper\'s claims.</figcaption></figure>'
        '<section id="problema" class="report-section">'
        + section_heading(2, "The problem", "what needs to change")
        + f'<p>{escape(r.problem)}</p></section>'
        '<section id="mecanismo" class="report-section">'
        + section_heading(3, "How it works", "the technical change")
        + f'<p>{escape(r.mechanism)}</p>'
        f'<p class="setup-note"><span>setup</span>{escape(setup)}</p></section>'
        '<section id="evidencia" class="report-section">'
        + section_heading(4, "Published evidence", "what the PDF supports")
        + f'<ol class="evidence">{evidence}</ol></section>'
        '<section id="teste" class="report-section">'
        + section_heading(5, "Minimum useful test", "how to try to disprove it")
        + _lista_report(r.minimum_test, ordered=True) + '</section>'
        '<section id="nucleo" class="report-section">'
        + section_heading(6, "From equation to test", "source-grounded technical core")
        + _render_technical_core(r.technical_core, document.source_url) + '</section>'
        '<section id="riscos" class="report-section">'
        + section_heading(7, "Failure modes", "adoption and validation risk")
        + _lista_report(r.main_risks) + '</section>'
        '<section id="perguntas" class="report-section">'
        + section_heading(8, "Questions before adoption", "what remains unresolved")
        + _lista_report(r.unanswered_questions) + '</section>'
        '<p class="report-source">Generated from the '
        f'<a href="{escape(document.source_url)}">arXiv PDF</a> with '
        f'{escape(document.model)} on {escape(document.generated_at[:10])}. '
        'AI Radar did not reproduce this experiment.</p>'
        '</article></div>'
        '<a class="report-to-top" data-report-top href="#conteudo" '
        'aria-label="Back to the start of the analysis">↑</a>'
    )
    return _pagina_estatica(
        f"{document.title} · Deep report · AI Radar", "acervo",
        document.generated_at[:10], corpo, heading=document.title,
        kicker=(f"deep report · arXiv {document.arxiv_id} · "
                f"{document.generated_at[:10]}"),
        deck=r.one_sentence, back_href="/ai-radar/#acervo",
        extra_script=_REPORT_JS,
    )
