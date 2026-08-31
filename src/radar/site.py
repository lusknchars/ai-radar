"""Renderizadores semanticos do acervo, gerados por funcoes puras.

Sem framework, sem passo de build, sem dependencia externa -- nem no servidor
nem no cliente. A pagina e um arquivo, e funciona com JS desligado.

Recebe `SiteData` pronto e NUNCA o `Store`: a coleta mora no banco, o desenho
nao sabe de onde o dado veio. CSS e comportamento do navegador pertencem a
``site_assets``; este modulo decide apenas estrutura, conteudo e links.
"""
from __future__ import annotations

import re
from html import escape
from urllib.parse import urlencode

from .config import load_thresholds
from .leitura import afirmacoes
from .report import ReportDocument
from .site_assets import SCRIPT as _JS, STYLES as _CSS
from .site_data import SiteData
from .svg import (METRICAS_X, render_avanco,
                  render_pequenos_multiplos, render_scatter)

# Cor significa familia, e SO. Em nenhum grafico ela codifica outra coisa.
# As matizes agrupam por escopo -- frios para inferencia, quentes para
# agentes, neutro para o escape -- o que ajuda a leitura sem que a cor passe
# a significar escopo: dentro de cada grupo elas sao distintas e arbitrarias.
CORES_FAMILIA = {
    # inferencia: frios
    "quantizacao":                "#2563eb",
    "cache_kv":                   "#0891b2",
    "decodificacao_especulativa": "#0d9488",
    "esparsidade_e_poda":         "#4f46e5",
    "kernels_e_atencao":          "#7c3aed",
    "serving_e_batching":         "#1d4ed8",
    "arquitetura_eficiente":      "#0369a1",
    "destilacao":                 "#155e75",
    "treino_eficiente":           "#3730a3",
    # agentes: quentes
    "uso_de_ferramenta":          "#ea580c",
    "memoria_e_contexto":         "#d97706",
    "planejamento_e_decomposicao": "#dc2626",
    "orquestracao_multiagente":   "#b91c1c",
    "avaliacao_de_agente":        "#a16207",
    "recuperacao_de_falha":       "#c2410c",
    "agentes_de_codigo":          "#be123c",
    "seguranca_e_guardrails":     "#9f1239",
    "recuperacao_e_rag":          "#92400e",
    # escape: neutro, e de proposito o menos chamativo da paleta
    "outro":                      "#6b7280",
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
        ("acervo", "/ai-radar/#acervo", "papers"),
        ("sinais", "/ai-radar/#sinais", "sinais"),
        ("edicoes", "/ai-radar/edicoes/", "edições"),
        ("about", "/ai-radar/about.html", "sobre"),
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
    contexto = "edição preservada" if edicao else "fila de leitura"
    return (
        '<header class="masthead"><div class="hero-copy">'
        f'<p class="hero-eyebrow">{contexto} · {escape(d.dia)}</p>'
        '<h1><span class="marca">ai-radar</span>Leia menos.<br>'
        '<em>Teste melhor.</em></h1>'
        '<p class="hero-deck">Papers de AI classificados por implementação '
        'independente. Briefs para decidir rápido, relatórios completos apenas '
        'quando uma técnica merece o seu tempo.</p>'
        f'{_sheen_link("ver os briefs", "#acervo")}</div>'
        f'<div class="numeros" aria-label="resumo do acervo">'
        f'<div class="numero"><b>{len(d.pontos)}</b><span>papers</span></div>'
        f'<div class="numero"><b>{len(d.familias_presentes)}</b>'
        f"<span>famílias</span></div>"
        f'<div class="numero"><b>{impls}</b>'
        f"<span>implementações independentes</span></div>"
        f"</div></header>"
    )


def _secao(titulo: str, sub: str, corpo: str, *, section_id: str = "") -> str:
    identificador = f' id="{escape(section_id)}"' if section_id else ""
    return (f"<section{identificador}><h2>{titulo}</h2><p class=\"sub\">{sub}</p>"
            f"{corpo}</section>")


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
    return botoes and f'<div class="eixos">{botoes}</div>{graficos}{_legenda(d)}{nota}'


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
    return (render_avanco(d.pontos, CORES_FAMILIA) + _legenda(d)
            + f'<p class="nota">{com} de {len(d.pontos)} papers declaram ganho '
              f"quantificado. Escala logarítmica; a linha por família só "
              f"aparece com pelo menos cinco papers no trimestre.</p>")


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
    return render_pequenos_multiplos(
        series, d.familias_presentes, CORES_FAMILIA, ROTULOS_FAMILIA)


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
    texto = f"{p.titulo} {p.familia} {p.pratica} {p.arxiv_id}".lower()
    estado_inicial = ' data-inicial="oculta" hidden' if initial_hidden else ""
    return (
        f'<tr class="linha" data-id="{escape(p.arxiv_id)}" '
        f'data-familia="{escape(p.familia)}" data-pratica="{escape(p.pratica)}" '
        f'data-texto="{escape(texto)}" '
        f'data-impls="{p.independent_impls}" data-estrelas="{p.stars_total}" '
        f'data-citacoes="{ord_cit}" data-ganho="{ord_ganho:g}" '
        f'data-score="{p.score:g}"{estado_inicial}>'
        f'<td data-label="paper"><a href="https://arxiv.org/abs/{escape(p.arxiv_id)}">'
        f'{escape(p.titulo)}</a><span class="paper-brief">'
        f'{escape(p.resumo)}</span></td>'
        f'<td data-label="família"><span class="pt" style="background:{cor}"></span>'
        f"{escape(ROTULOS_FAMILIA.get(p.familia, p.familia))}</td>"
        f'<td data-label="prática"><span class="tag {escape(p.pratica)}">'
        f'{escape(ROTULOS_PRATICA.get(p.pratica, p.pratica))}</span></td>'
        f'<td class="num" data-label="impls">{p.independent_impls}</td>'
        f'<td class="num" data-label="estrelas">{p.stars_total}</td>'
        f'<td class="num" data-label="citações">{cit}</td>'
        f'<td class="num" data-label="ganho">{ganho}</td>'
        f'<td class="acao" data-label="relatório">{_report_action(p, has_report)}</td>'
        f"</tr>"
    )


def _secao_tabela(d: SiteData, report_ids: set[str]) -> str:
    """Filtro por pratica e por familia, sem estado e sem URL.

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
        '<div class="rolagem"><table><thead><tr>'
        '<th><button type="button" data-ordenar="score">técnica</button></th>'
        "<th>família</th><th>prática</th>"
        '<th class="num"><button type="button" data-ordenar="impls">impls</button></th>'
        '<th class="num"><button type="button" data-ordenar="estrelas">estrelas</button></th>'
        '<th class="num"><button type="button" data-ordenar="citacoes">citações</button></th>'
        '<th class="num"><button type="button" data-ordenar="ganho">ganho</button></th>'
        '<th>relatório</th>'
        f"</tr></thead><tbody>{linhas}</tbody></table></div>{mostrar}"
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
            _secao("Papers para decidir agora",
                   "Os 30 maiores sinais aparecem primeiro. Busque e filtre "
                   "o acervo inteiro sem gastar outra chamada de modelo.",
                   _secao_tabela(dados, report_ids), section_id="acervo"),
            _secao("A fronteira",
                   "Implementações independentes contra o quanto o paper já "
                   "foi olhado. A região interessante é o alto à esquerda: "
                   "muita gente construindo, pouca gente olhando.",
                   _secao_fronteira(dados), section_id="sinais"),
            (_secao("O avanço alegado",
                    "Ganho declarado no resumo, por família, ao longo do tempo "
                    f"— {ROTULO_ALEGACAO}.",
                    avanco) if (avanco := _secao_avanco(dados)) else ""),
            _secao("As famílias no tempo",
                   "Volume por família, mês a mês, em escala compartilhada.",
                   _secao_familias(dados)),
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
        '<div id="fundo" aria-hidden="true"></div>'
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
        f"</div><script>{_JS}</script></body></html>"
    )


def _pagina_estatica(titulo: str, atual: str, dia: str, corpo: str,
                     *, heading: str | None = None) -> str:
    """Casca das paginas de distribuicao.

    Compartilha a tipografia e a navegacao do acervo, mas nao carrega o JS da
    tabela. Links e texto continuam funcionando com qualquer bloqueador de
    script, e a pagina nao faz requisicao externa.
    """
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="alternate" type="application/rss+xml" title="ai-radar" '
        'href="/ai-radar/feed.xml">'
        f'<title>{escape(titulo)}</title><style>{_CSS}</style></head><body>'
        '<div id="fundo" aria-hidden="true"></div>'
        '<a class="pular" href="#conteudo">pular para o conteúdo</a>'
        f'<div class="envelope">{_nav(atual)}'
        '<header class="static-masthead">'
        f'<p class="hero-eyebrow">atualizado em {escape(dia)}</p>'
        f'<h1>{escape(heading or titulo)}</h1></header>'
        f'<main id="conteudo" class="pagina">{corpo}</main>'
        '<footer>Gerado pelo próprio pipeline. Sem framework, sem build, '
        'sem requisição externa.</footer></div></body></html>'
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


def render_report(document: ReportDocument) -> str:
    r = document.report
    evidence = "".join(
        '<li><strong>' + escape(item.claim) + '</strong>'
        + (f'<span>resultado: {escape(item.result)}</span>' if item.result else "")
        + (f'<span>baseline: {escape(item.baseline)}</span>' if item.baseline else "")
        + (f'<span>condições: {escape(item.conditions)}</span>' if item.conditions else "")
        + "</li>"
        for item in r.evidence
    ) or '<li>Nenhuma evidência quantificada foi localizada.</li>'
    setup = ", ".join(ROTULOS_SETUP[value] for value in r.software_setup)
    corpo = (
        '<article class="report">'
        f'<p class="report-kicker">relatório sob demanda · arXiv '
        f'{escape(document.arxiv_id)}</p>'
        f'<p class="report-lead">{escape(r.one_sentence)}</p>'
        '<div class="infra-grid">'
        f'<div><span>teste mínimo</span><b>{escape(ROTULOS_INFRA[r.validation_tier])}</b></div>'
        f'<div><span>experimento do paper</span><b>{escape(ROTULOS_INFRA[r.evidence_tier])}</b></div>'
        f'<div><span>base da classificação</span><b>{escape(ROTULOS_BASE_INFRA[r.infrastructure_basis])}</b></div>'
        f'<div><span>treino</span><b>{escape(ROTULOS_TREINO[r.training_required])}</b></div>'
        '</div>'
        '<section><h2>Problema</h2>' + f'<p>{escape(r.problem)}</p></section>'
        '<section><h2>Como funciona</h2>' + f'<p>{escape(r.mechanism)}</p>'
        f'<p class="nota">Setup: {escape(setup)}</p></section>'
        '<section><h2>Evidência relatada</h2>'
        f'<ul class="evidence">{evidence}</ul></section>'
        '<section><h2>Menor teste útil</h2>'
        + _lista_report(r.minimum_test, ordered=True) + '</section>'
        '<section><h2>Matemática que merece leitura</h2>'
        + _lista_report(r.math_to_understand) + '</section>'
        '<section><h2>Riscos</h2>' + _lista_report(r.main_risks) + '</section>'
        '<section><h2>Antes de adotar, descubra</h2>'
        + _lista_report(r.unanswered_questions) + '</section>'
        '<p class="report-source">Gerado de '
        f'<a href="{escape(document.source_url)}">PDF do arXiv</a> com '
        f'{escape(document.model)} em {escape(document.generated_at[:10])}. '
        'Este relatório não reproduz o experimento.</p>'
        '</article>'
    )
    return _pagina_estatica(
        f"{document.title} — relatório — ai-radar", "acervo",
        document.generated_at[:10], corpo, heading=document.title,
    )
