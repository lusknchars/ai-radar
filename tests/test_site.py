import pytest

from radar.models import FAMILIAS
from radar.report import DeepReport, EvidenceClaim, ReportDocument
from radar.site import (CORES_FAMILIA, render_about, render_editions,
                        render_report, render_site)
from radar.site_data import Ponto, SiteData


def ponto(**kw):
    base = dict(arxiv_id="2608.11111", titulo="Fused INT4 kernel",
                familia="cache_kv", pratica="adotar", independent_impls=3,
                total_impls=4, stars_total=10, citations=None, idade_dias=12,
                ganho_eixo="velocidade", ganho_fator=2.3, ganho_texto="2.3x",
                resumo="Replaces the FP16 kernel.", publicado="2026-08-01",
                score=1.2, scope="inferencia")
    return Ponto(**{**base, **kw})


@pytest.fixture
def dados():
    return SiteData(pontos=[ponto(), ponto(arxiv_id="2608.22222",
                                           familia="outro", score=0.4)],
                    dia="2026-08-30", cortes={"abaixo_do_piso": 12},
                    rechecked_total=7)


@pytest.fixture
def dados_vazio():
    return SiteData(pontos=[], dia="2026-08-30", cortes={}, rechecked_total=0)


def test_a_pagina_e_html_completo(dados):
    html = render_site(dados)
    assert html.lstrip().startswith("<!doctype html>")
    assert "</html>" in html


def test_publication_shell_uses_english_editorial_copy(dados):
    html = render_site(dados)
    assert '<html lang="en">' in html
    for expected in (
        "Find the AI research", "Research index", "Research signals",
        "Generate deep report", "Exclusions and controls",
    ):
        assert expected in html
    for legacy in (
        "Pesquisa aplicada", "Índice de pesquisa", "Sinais do acervo",
        "gerar relatório", "pular para o conteúdo",
    ):
        assert legacy not in html


def test_a_navegacao_publica_liga_acervo_edicoes_about_e_rss(dados):
    html = render_site(dados)
    for caminho in ("/ai-radar/", "/ai-radar/edicoes/",
                    "/ai-radar/about.html", "/ai-radar/feed.xml"):
        assert caminho in html
    assert 'rel="alternate" type="application/rss+xml"' in html


def test_a_edicao_se_identifica_como_recorte_diario(dados):
    html = render_site(dados, edicao=True)
    assert "archived edition · 2026-08-30" in html
    assert "<title>AI Radar · Edition 2026-08-30</title>" in html


def test_o_indice_de_edicoes_usa_urls_estaveis():
    html = render_editions(["2026-08-29", "2026-08-30"], "2026-08-30")
    assert "/ai-radar/edicoes/2026-08-29/" in html
    assert "/ai-radar/edicoes/2026-08-30/" in html
    assert html.index("2026-08-30") < html.rindex("2026-08-29")


def test_about_declara_o_que_o_radar_nao_mede():
    html = render_about("2026-08-30", papers=12, edicoes=2)
    assert "12 papers across 2 editions" in html
    assert "does not reproduce experimental results" in html
    assert "remote asset request" in html
    assert '<canvas id="fundo" aria-hidden="true"></canvas>' in html
    assert "getContext('2d'" in html


def test_toda_familia_tem_cor_propria():
    """Cor significa familia, e so. Uma familia sem cor cairia em
    `currentColor` e duas familias virariam o mesmo ponto no grafico."""
    assert set(CORES_FAMILIA) == FAMILIAS
    assert len(set(CORES_FAMILIA.values())) == len(FAMILIAS)


def test_a_pagina_nao_faz_requisicao_externa(dados):
    """O unico asset requisitado e versionado e publicado pelo proprio radar.

    Links para arXiv e GitHub sao navegacao do leitor, nao recursos da pagina.
    """
    html = (render_site(dados)
            .replace("https://arxiv.org", "")
            .replace("https://github.com", "")
            # Identificador de namespace, nao URL de recurso nem requisicao.
            .replace('xmlns="http://www.w3.org/2000/svg"', ""))
    for proibido in ("https://", "http://", "//cdn", "@import"):
        assert proibido not in html
    assert html.count('<script src="') == 2
    assert '<script src="/ai-radar/assets/d3-7.9.0.min.js">' in html
    assert '<script src="/ai-radar/assets/observable-plot-0.6.17.min.js">' in html


def test_a_pagina_usa_a_paleta_editorial_da_publicacao(dados):
    html = render_site(dados)
    for color in ("#eeeeee", "#000000", "#dddddd", "#cb2957"):
        assert color in html


def test_a_navegacao_nao_renderiza_o_monograma_antigo(dados):
    html = render_site(dados)
    assert 'content:"AI/R"' not in html
    assert ".nav::before" not in html


def test_a_fonte_e_do_sistema(dados):
    assert "system-ui" in render_site(dados)


def test_acervo_vazio_gera_pagina_valida(dados_vazio):
    """Nao excecao, nao HTML quebrado: a pagina diz que nao ha dado."""
    html = render_site(dados_vazio)
    assert "</html>" in html
    assert "no papers" in html.lower()


def test_o_enquadramento_esta_presente_e_e_fixo(dados):
    """Contrato com o leitor: o que o radar mede e o que ele deliberadamente
    NAO mede. E escrito a mao e versionado, nao gerado."""
    html = render_site(dados)
    assert "independent implementations" in html
    assert "does not claim" in html


def test_o_cabecalho_traz_os_numeros_do_acervo(dados):
    html = render_site(dados)
    assert "2026-08-30" in html
    assert ">2<" in html          # dois papers


def test_o_titulo_da_aba_nomeia_o_projeto_e_o_dia(dados):
    assert "<title>AI Radar · 2026-08-30</title>" in render_site(dados)


def test_o_site_nao_importa_io():
    import radar.site as m
    fonte = open(m.__file__, encoding="utf-8").read()
    for proibido in ("import sqlite3", "import httpx", "import anthropic"):
        assert proibido not in fonte


def test_o_texto_vindo_do_dado_e_escapado(dados):
    """O esqueleto so renderiza o dia; titulo de paper entra na tarefa 7,
    junto da tabela, e ganha o seu proprio teste de escape la.

    Aqui a afirmacao e sobre o caminho: todo texto que vem do dado passa por
    `escape`. Um `&` cru no `<title>` quebraria a pagina em silencio.
    """
    html = render_site(SiteData(pontos=[ponto()], dia="A & B <b>",
                                cortes={}, rechecked_total=0))
    assert "A &amp; B &lt;b&gt;" in html
    # Nao `"<b>" not in html`: o cabecalho usa <b> de verdade nos numeros.
    # A afirmacao e que a string CRUA nao sobreviveu como marcacao.
    assert "A & B <b>" not in html


# --- Tarefa 5: a seção da fronteira ---

def test_a_fronteira_traz_um_svg_por_metrica(dados):
    assert render_site(dados).count('class="scatter"') == 3


def test_os_graficos_formam_um_unico_caderno_de_sinais(dados):
    html = render_site(dados)
    assert 'id="sinais"' in html
    assert 'class="chart-suite"' in html
    assert html.count('class="chart-card') >= 2
    assert "color = research area" in html
    assert 'class="chart-scroll"' in html
    assert '/ai-radar/assets/observable-plot-0.6.17.min.js' in html
    assert 'data-plot-host="frontier"' in html
    assert 'data-plot-host="families"' in html
    assert 'data-chart-data="frontier"' in html


def test_chart_json_cannot_be_closed_by_an_untrusted_paper_title():
    html = render_site(_acervo([ponto(titulo="</script><script>alert(1)</script>")]))
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script>" in html


def test_so_o_primeiro_scatter_comeca_visivel(dados):
    """A pagina funciona com JS desligado: `hidden` no HTML e nao
    `display:none` por CSS, para que o primeiro fique quando o JS nao roda."""
    import re
    html = render_site(dados)
    # Regex e nao `count('class="scatter" hidden')`: aquela forma afirmava uma
    # ORDEM DE ATRIBUTOS, nao o comportamento. Trocar a ordem no gerador
    # quebraria o teste sem quebrar a pagina.
    ocultos = re.findall(r'<svg class="scatter"[^>]*\shidden', html)
    visiveis = re.findall(r'<svg class="scatter"(?:(?!\shidden)[^>])*>', html)
    assert len(ocultos) == 2
    assert len(visiveis) == 1


def test_ha_um_botao_por_metrica(dados):
    html = render_site(dados)
    for rotulo in ("GitHub stars", "days since publication",
                   "total implementations"):
        assert rotulo in html


def test_o_portao_de_estouro_esta_rotulado(dados):
    """Quem olha precisa entender por que um paper muito citado nao aparece,
    sem ler documentacao."""
    html = render_site(dados)
    assert "1000" in html
    assert "attention threshold" in html.lower()


def test_a_legenda_lista_so_as_familias_presentes(dados):
    html = render_site(dados)
    assert "cache_kv" in html
    assert "destilacao" not in html      # ausente do acervo de teste


def test_o_js_do_produto_e_inline_e_a_biblioteca_e_local(dados):
    html = render_site(dados)
    assert "<script>" in html
    assert '<script src="/ai-radar/assets/d3-7.9.0.min.js">' in html
    assert '<script src="/ai-radar/assets/observable-plot-0.6.17.min.js">' in html


# --- Tarefa 6: a seção de avanço na página ---

def _acervo(pontos, **kw):
    base = dict(dia="2026-08-30", cortes={}, rechecked_total=0)
    return SiteData(pontos=list(pontos), **{**base, **kw})


@pytest.fixture
def dados_ganho_ralo():
    # 1 de 10 tem fator: 10%, bem abaixo do piso de 35%.
    com = [ponto(ganho_fator=2.0)]
    sem = [ponto(arxiv_id=f"26{i}", ganho_fator=None, ganho_eixo="nenhum")
           for i in range(9)]
    return _acervo(com + sem)


def test_todo_ganho_visivel_carrega_o_rotulo(dados):
    """Inegociavel: numero de abstract apresentado como medicao e exatamente
    o hype de que este projeto existe para fugir. Se nao couber o rotulo,
    corta-se o grafico, nao o rotulo."""
    assert "reported by the authors; not independently verified" in render_site(dados)


def test_a_secao_some_com_cobertura_abaixo_de_35_por_cento(dados_ganho_ralo):
    """Grafico sobre dado ralo e pior que grafico ausente."""
    assert dados_ganho_ralo.cobertura_de_ganho < 0.35
    assert "claimed performance gains" not in render_site(dados_ganho_ralo).lower()


def test_nenhum_ganho_aparece_sem_o_rotulo(dados_ganho_ralo):
    """A regra e "todo ganho carrega o rotulo", nao "o rotulo so existe na
    secao de avanco".

    A versao anterior deste teste afirmava a segunda coisa, e passou a falhar
    quando o destaque -- que mostra ganho com rotulo -- foi implementado na
    tarefa 8. O teste estava errado, nao o codigo: um ganho no destaque com o
    rotulo ao lado cumpre a regra da spec.
    """
    import re
    html = render_site(dados_ganho_ralo)
    # A secao de avanco nao existe (cobertura < 35%), mas o destaque pode
    # mostrar ganho -- e sempre que mostrar, o rotulo tem que estar junto.
    ganhos = re.findall(r"[\d.]+x gain in", html)
    if ganhos:
        assert html.count("reported by the authors; not independently verified") >= len(ganhos)


def test_com_cobertura_suficiente_a_secao_aparece(dados):
    assert dados.cobertura_de_ganho >= 0.35
    assert "claimed performance gains" in render_site(dados).lower()


# --- Tarefa 7: famílias no tempo, e o índice editorial ---

def test_o_indice_traz_uma_entrada_por_paper(dados):
    assert render_site(dados).count('class="linha paper-entry"') == len(dados.pontos)


def test_citacao_desconhecida_vira_travessao_e_nao_zero():
    """Nao-resolvido nao e zero: ~8% dos papers nao tem DOI no OpenAlex.
    Renderizar 0 ali seria o mesmo defeito que as tarefas 2, 3 e 8 do plano
    anterior consertaram, reintroduzido pela camada de apresentacao."""
    import re
    # Nao `"—" in html`: o travessao tambem aparece na coluna de ganho, entao
    # aquela forma passava mesmo com a citacao virando zero. Verificado por
    # mutacao em 2026-08-30. A afirmacao precisa ser sobre A CELULA.
    html = render_site(_acervo([ponto(citations=None, ganho_fator=2.0)]))
    entrada = re.search(
        r'<article class="linha paper-entry".*?</article>', html, re.S).group(0)
    valores = re.findall(r'<div><b>([^<]*)</b><span>[^<]*</span></div>', entrada)
    assert valores[2] == "—"        # impls, estrelas, CITACOES, ganho
    assert valores[3] == "2x"       # o ganho tem numero, provando que nao e ele


def test_citacao_zero_e_renderizada_como_zero():
    html = render_site(_acervo([ponto(citations=0, arxiv_id="2608.33333")]))
    import re
    entrada = re.search(
        r'<article class="linha paper-entry".*?</article>', html, re.S).group(0)
    assert "<b>0</b><span>citations</span>" in entrada


def test_cada_linha_tem_link_de_arxiv_resolvivel(dados):
    html = render_site(dados)
    for p in dados.pontos:
        assert f"https://arxiv.org/abs/{p.arxiv_id}" in html


def test_a_linha_carrega_familia_e_pratica_como_atributo(dados):
    """E o que o filtro le. Sem isso o JS teria que parsear texto visivel."""
    html = render_site(dados)
    assert 'data-familia="cache_kv"' in html
    assert 'data-pratica="adotar"' in html


def test_a_tabela_vem_ordenada_por_score():
    """A fixture entra em ordem CRESCENTE de score, de proposito.

    A versao anterior usava pontos que ja chegavam em ordem decrescente, entao
    remover o `sorted` do gerador nao mudava nada e o teste passava pelo motivo
    errado. Verificado por mutacao em 2026-08-30.
    """
    pontos = [ponto(arxiv_id="baixo", score=0.1),
              ponto(arxiv_id="meio", score=0.5),
              ponto(arxiv_id="alto", score=9.9)]
    html = render_site(_acervo(pontos))
    assert (html.index('data-id="alto"') < html.index('data-id="meio"')
            < html.index('data-id="baixo"'))


def test_ha_filtro_por_pratica_e_por_familia(dados):
    html = render_site(dados)
    assert 'data-filtro="pratica"' in html
    assert 'data-filtro="familia"' in html


def test_o_titulo_do_paper_e_escapado():
    """A divida que a tarefa 4 deixou anotada: o esqueleto nao renderizava
    titulo, entao o escape dele so pode ser testado aqui."""
    html = render_site(_acervo([ponto(titulo="A & B <script>x</script>")]))
    assert "&amp;" in html
    assert "<script>x</script>" not in html


def test_a_secao_de_familias_traz_os_pequenos_multiplos(dados):
    assert 'class="multiplos"' in render_site(dados)


def test_os_pequenos_multiplos_cobrem_so_as_familias_presentes(dados):
    import re
    html = render_site(dados)
    svg = re.search(r'<svg class="multiplos".*?</svg>', html, re.S).group(0)
    assert svg.count('<g class="painel"') == len(dados.familias_presentes)


# --- Tarefa 8: ponta a ponta, e os cortes ---

REPOS = [
    {"full_name": "tridao/flash-attn", "owner": "tridao", "stars": 3200,
     "is_author": 1, "is_author_reason": "mais_antigo_e_mais_estrelado"},
    {"full_name": "acme/fa-triton", "owner": "acme", "stars": 41,
     "is_author": 0, "is_author_reason": None},
]


def test_o_destaque_e_o_de_maior_score():
    d = _acervo([ponto(arxiv_id="baixo", score=0.1, resumo="RESUMO-BAIXO"),
                 ponto(arxiv_id="alto", score=9.9, resumo="RESUMO-ALTO")])
    html = render_site(d)
    assert "RESUMO-ALTO" in html


def test_o_destaque_mostra_a_regra_de_autoria_de_cada_repo():
    """Sem isto, "3 implementacoes independentes" e fe.

    E a secao que torna o numero auditavel: mostra os repositorios, o dono, as
    estrelas, e QUAL REGRA classificou cada um.
    """
    d = SiteData(pontos=[ponto()], dia="2026-08-30", cortes={},
                 rechecked_total=0, repos_do_destaque=REPOS)
    html = render_site(d)
    assert "oldest and most-starred repository" in html
    assert "tridao/flash-attn" in html
    assert "acme/fa-triton" in html


def test_o_destaque_separa_autor_de_independente():
    d = SiteData(pontos=[ponto()], dia="2026-08-30", cortes={},
                 rechecked_total=0, repos_do_destaque=REPOS)
    html = render_site(d)
    assert "independent" in html
    assert "author" in html


def test_destaque_sem_repos_diz_isso_em_vez_de_sumir():
    html = render_site(_acervo([ponto()]))
    assert "no repositories" in html.lower()


def test_todos_os_cortes_do_dia_aparecem_com_contagem(dados):
    """Restricao global do projeto: todo corte e contado e chega ao leitor."""
    html = render_site(dados)
    for motivo, n in dados.cortes.items():
        # Renderizado legivel: `abaixo do piso`, nao `abaixo_do_piso`. O que a
        # restricao global exige e que o corte CHEGUE ao leitor, com contagem.
        assert "below the signal threshold" in html
        assert f"<b>{n}</b>" in html


def test_dia_sem_corte_nenhum_ainda_mostra_a_secao():
    html = render_site(_acervo([ponto()]))
    assert "exclusions and controls" in html.lower()
    assert "no papers were excluded" in html.lower()


def test_edicao_sem_contabilidade_nao_afirma_que_nao_houve_corte():
    html = render_site(_acervo([ponto()], cortes=None), edicao=True)
    assert "were not recorded" in html
    assert "no papers were excluded" not in html.lower()


def test_o_total_re_consultado_aparece(dados):
    assert "7" in render_site(dados)


def test_acervo_sem_destaque_nao_explode(dados_vazio):
    assert "</html>" in render_site(dados_vazio)


# --- Manipulabilidade: ordenar, buscar, contar, cruzar ---

def test_toda_coluna_numerica_e_ordenavel(dados):
    """Ordenar por coluna e o que permite ao leitor fazer a pergunta que EU
    nao antecipei -- "os mais implementados que ninguem olhou", por exemplo."""
    html = render_site(dados)
    for chave in ("impls", "estrelas", "citacoes", "ganho", "score"):
        assert f'data-ordenar="{chave}"' in html


def test_cada_linha_carrega_os_valores_de_ordenacao(dados):
    """O JS ordena por atributo, nao parseando texto visivel: `1.2k` e `—`
    nao sao numeros, e um parser de texto quebraria em silencio nos dois."""
    html = render_site(dados)
    assert 'data-impls="3"' in html
    assert 'data-score="1.2"' in html


def test_citacao_desconhecida_ordena_como_menos_um(dados):
    """`None` precisa de valor ordenavel proprio. Mandar zero faria
    desconhecido empatar com "ninguem citou" -- a mesma confusao que o
    pipeline inteiro existe para evitar."""
    html = render_site(_acervo([ponto(citations=None)]))
    assert 'data-citacoes="-1"' in html


def test_ha_busca_em_texto_livre(dados):
    html = render_site(dados)
    assert 'data-busca' in html
    assert 'type="search"' in html


def test_a_linha_carrega_o_texto_de_busca_em_caixa_baixa(dados):
    """Buscar sem normalizar faria "Quantization" nao casar com "quantization",
    e o leitor concluiria que nao ha nada sobre o assunto."""
    html = render_site(_acervo([ponto(titulo="Fused INT4 KERNELS")]))
    assert 'data-texto="fused int4 kernels' in html


def test_ha_contador_vivo_de_linhas(dados):
    """Sem contagem, um filtro que devolve pouco e indistinguivel de um
    filtro quebrado."""
    html = render_site(dados)
    assert 'id="contador"' in html
    assert f"of {len(dados.pontos)}" in html


def test_a_legenda_e_clicavel_e_carrega_a_familia(dados):
    html = render_site(dados)
    assert 'data-legenda="cache_kv"' in html


# --- Tarefa 8 do bloco de leitura ---

def test_o_bloco_aparece_acima_do_grafico(dados):
    html = render_site(dados)
    assert html.index('class="leitura"') < html.index('class="scatter"')


def test_o_bloco_vem_prosa_e_nao_cartoes(dados):
    """Cartão convida à leitura por varredura, e varredura é o modo em que
    número sem contexto vira impressão."""
    html = render_site(dados)
    assert '<p class="frase"' in html
    assert 'class="cartao"' not in html


def test_a_frase_com_filtro_vira_link_aplicavel(dados):
    assert "data-aplicar=" in render_site(dados)


def test_frase_sem_filtro_nao_vira_link(dados):
    """A de escassez não tem filtro: ela é o denominador, não um recorte."""
    import re
    html = render_site(dados)
    frase = re.search(
        r'<p class="frase"[^>]*>.*?no independent implementation.*?</p>',
        html, re.S,
    )
    assert frase and "data-aplicar" not in frase.group(0)


def test_acervo_vazio_nao_desenha_o_bloco(dados_vazio):
    assert 'class="leitura"' not in render_site(dados_vazio)


def test_os_numeros_do_bloco_ganham_destaque(dados):
    """Prosa com número destacado: o olho acha o número sem o cartão."""
    assert '<b class="n">' in render_site(dados)


def test_destaque_numerico_nao_quebra_entidade_de_aspa(dados):
    html = render_site(dados)
    assert "&#x<b" not in html
    assert "&#x27;other&#x27;" in html


# --- Identidade editorial ---

def test_a_tipografia_usa_electrolize_embutida_sem_fonte_remota(dados):
    """Display usa Electrolize; texto e dados conservam fallbacks locais."""
    html = render_site(dados)
    assert "Electrolize" in html
    assert "data:font/woff2;base64" in html
    assert "Switzer" in html
    assert "system-ui" in html
    assert "ui-monospace" in html
    assert "fonts.gstatic.com" not in html


def test_os_dados_ficam_em_sem_serifa_com_algarismo_tabular(dados):
    html = render_site(dados)
    assert "tabular-nums" in html


def test_ha_fundo_dither_sem_interacao_de_ponteiro(dados):
    html = render_site(dados)
    assert '<canvas id="fundo" aria-hidden="true"></canvas>' in html
    assert "pointermove" not in html


def test_o_fundo_respeita_reducao_de_movimento(dados):
    """Fundo que se move sem checar `prefers-reduced-motion` é gatilho
    vestibular, não decoração."""
    html = render_site(dados)
    assert "prefers-reduced-motion" in html


def test_o_fundo_nao_intercepta_clique(dados):
    """Camada decorativa que come clique é bug de acessibilidade que só
    aparece quando alguém não consegue usar a página."""
    import re
    html = render_site(dados)
    bloco = re.search(r"#fundo\{[^}]*\}", html).group(0)
    assert "pointer-events:none" in bloco


def test_o_fundo_e_escondido_de_leitor_de_tela(dados):
    assert 'id="fundo" aria-hidden="true"' in render_site(dados)


def test_todo_elemento_focavel_tem_indicador_visivel(dados):
    """A skill de UI/UX apontou a lacuna: sem `:focus-visible` a navegação
    por teclado é invisível e a página fica inutilizável sem mouse."""
    assert ":focus-visible" in render_site(dados)


def test_ha_link_de_pular_para_o_conteudo(dados):
    html = render_site(dados)
    assert 'class="pular"' in html
    assert 'href="#conteudo"' in html


def test_o_cabecalho_tem_estrutura_de_masthead(dados):
    html = render_site(dados)
    assert 'class="masthead publication-head"' in html
    assert 'class="hero-eyebrow"' in html
    assert "Find the AI research" in html


def test_o_indice_tem_hierarquia_de_publicacao_e_sinal_auditavel(dados):
    html = render_site(dados)
    assert 'class="research-index"' in html
    assert "published" in html
    assert "paper and brief" in html
    assert 'class="evidence-fingerprint"' in html
    assert "observed signal" in html
    assert "Original paper" in html


def test_a_hierarquia_de_titulos_e_logica(dados):
    """h1 uma vez, e nenhum h3 sem h2 antes."""
    import re
    html = render_site(dados)
    assert html.count("<h1") == 1
    titulos = re.findall(r"<h([1-6])", html)
    assert "3" not in titulos or "2" in titulos[:titulos.index("3")]


def test_o_link_de_pular_tem_destino_que_existe(dados):
    """Link de pulo apontando para lugar nenhum é pior que nenhum: ele
    promete a quem navega por teclado um atalho que não funciona."""
    html = render_site(dados)
    assert 'href="#conteudo"' in html
    assert 'id="conteudo"' in html


# --- Briefs e relatorios sob demanda ---

def test_o_acervo_mostra_trinta_briefs_antes_de_pedir_expansao():
    pontos = [ponto(arxiv_id=f"2608.{10000 + i}", score=float(i))
              for i in range(31)]
    html = render_site(_acervo(pontos))
    assert html.count('data-inicial="oculta" hidden') == 1
    assert '<span id="contador">30 of 31</span>' in html
    assert 'data-mostrar-todos' in html
    assert 'Show all 31 papers' in html


def test_busca_e_filtro_podem_sair_do_recorte_inicial():
    html = render_site(_acervo([ponto()]))
    assert "recorteAtivo" in html
    assert "mostrarTodos" in html


def test_cada_brief_tem_acao_segura_para_pedir_relatorio():
    html = render_site(_acervo([ponto()]))
    assert 'class="paper-brief"' in html
    assert 'github.com/lusknchars/ai-radar/issues/new?' in html
    assert 'title=%5Breport%5D+2608.11111' in html
    assert 'Generate deep report' in html
    assert 'min-height:44px' in html


def test_acao_porta_o_sheen_button_do_frontend_lab():
    html = render_site(_acervo([ponto()]))
    assert 'class="sheen-sweep"' in html
    assert "color-mix(in oklab,var(--acc)" in html
    assert "translateX(105%)" in html
    assert "prefers-reduced-motion:reduce" in html


def test_fila_de_papers_aparece_antes_dos_graficos(dados):
    html = render_site(dados)
    assert html.index('id="acervo"') < html.index('class="scatter"')


def test_relatorio_existente_troca_a_acao_por_link_de_leitura():
    html = render_site(_acervo([ponto()]), report_ids={"2608.11111"})
    assert '/ai-radar/reports/2608.11111/' in html
    assert 'Read deep report' in html
    assert 'issues/new?' not in html


def _report_document() -> ReportDocument:
    from radar.formulas import (FormulaVariable, FormulaWalkthrough,
                                TechnicalCore, WorkedExample)
    return ReportDocument(
        arxiv_id="2608.11111", title="Fast <Attention>",
        generated_at="2026-08-31T18:00:00+00:00", provider="kimi",
        model="kimi-k3", source_url="https://arxiv.org/pdf/2608.11111",
        source_sha256="a" * 64,
        report=DeepReport(
            one_sentence="Replaces dense attention with selected blocks.",
            problem="Long contexts consume excessive memory.",
            mechanism="Selects blocks before the attention kernel.",
            technical_core=TechnicalCore(
                kind="formula",
                summary="Scaling stabilizes the query-key product.",
                walkthroughs=[FormulaWalkthrough(
                    status="exact", role="proposed_method",
                    latex=r"S = QK^T / \sqrt{d}", source_page=6,
                    source_excerpt=(
                        "We divide the query key product by the square root of "
                        "the head dimension."
                    ),
                    plain_language=(
                        "Divides the product by a scale that grows with dimension."
                    ),
                    variables=[FormulaVariable(
                        symbol="d", meaning="attention head dimension")],
                    derivation_steps=["Compute QK^T.", "Divide by sqrt(d)."],
                    worked_example=WorkedExample(
                        inputs={"d": 64}, expression="sqrt(64)", result="8",
                        explanation="With d=64, the illustrative divisor is 8."),
                    assumptions=["Q and K use the same internal dimension."],
                )],
            ),
            evidence=[EvidenceClaim(
                claim="Reduces memory", result="2x", baseline="dense attention",
                conditions="7B model", source_page=7,
                source_excerpt="Peak memory falls by half against dense attention.",
            )],
            validation_tier="single_gpu_24gb", evidence_tier="multi_gpu",
            infrastructure_basis="explicit",
            software_setup=["custom_cuda_kernel"],
            training_required="inference_only",
            minimum_test=["Compare on the same workload"],
            main_risks=["Incompatible kernel"],
            unanswered_questions=["What is the quality loss?"],
        ),
    )


def test_pagina_de_relatorio_separa_teste_minimo_de_experimento():
    html = render_report(_report_document())
    assert "1 GPU, up to 24 GB" in html
    assert "multiple GPUs" in html
    assert "minimum useful test" in html
    assert "original experiment" in html
    assert "AI Radar did not reproduce this experiment" in html


def test_report_shell_uses_english_editorial_copy():
    html = render_report(_report_document())
    assert '<html lang="en">' in html
    for expected in (
        "Cost before commitment", "Published evidence",
        "Minimum useful test", "Questions before adoption",
    ):
        assert expected in html
    for legacy in (
        "O custo antes da leitura", "Evidência relatada",
        "Menor teste útil", "Perguntas abertas", "abrir PDF completo",
    ):
        assert legacy not in html


def test_relatorio_tem_hierarquia_de_artigo_e_volta_ao_indice():
    html = render_report(_report_document())
    assert 'class="static-masthead article-masthead"' in html
    assert 'class="article-deck"' in html
    assert 'class="report-layout"' in html
    assert 'class="report-toc" aria-label="In this analysis"' in html
    assert 'href="#infra"' in html
    assert 'href="#evidencia"' in html
    assert 'data-report-progress' in html
    assert "IntersectionObserver" in html
    assert 'href="/ai-radar/#acervo"' in html
    assert "deep report · arXiv 2608.11111" in html


def test_relatorio_abre_com_custo_e_origem_da_analise():
    html = render_report(_report_document())
    assert 'id="infra" class="report-section infra-exhibit"' in html
    assert "Cost before commitment" in html
    assert "exhibit 01" in html
    assert "analysis generated with kimi-k3" in html
    assert "5 min read" in html


def test_evidencia_liga_direto_para_a_pagina_do_pdf():
    html = render_report(_report_document())
    assert 'href="https://arxiv.org/pdf/2608.11111#page=7"' in html
    assert "Open page 7 in the PDF" in html
    assert "Peak memory falls by half" in html
    assert "Open paper page" in html


def test_nucleo_tecnico_mostra_formula_explicacao_e_origem_da_conta():
    html = render_report(_report_document())
    assert "From equation to test" in html
    assert r"S = QK^T / \sqrt{d}" in html
    assert "attention head dimension" in html
    assert "AI Radar worked example" in html
    assert "With d=64, the illustrative divisor is 8." in html
    assert 'href="https://arxiv.org/pdf/2608.11111#page=6"' in html


def test_nucleo_sem_formula_explica_qual_mecanismo_importa():
    from radar.formulas import TechnicalCore
    document = _report_document()
    report = document.report.model_copy(update={
        "technical_core": TechnicalCore(
            kind="system",
            summary="The gain comes from scheduling, not a new equation.",
            walkthroughs=[],
        )
    })
    html = render_report(document.model_copy(update={"report": report}))
    assert "system-level core" in html
    assert "The gain comes from scheduling" in html
    assert "AI Radar worked example" not in html


def test_rotulos_publicos_nao_expoem_os_enums_internos(dados):
    html = render_site(dados)
    assert "KV cache" in html
    assert 'data-familia="cache_kv"' in html
    assert ">cache_kv<" not in html


def test_pagina_de_relatorio_escapa_texto_do_modelo():
    html = render_report(_report_document())
    assert "Fast &lt;Attention&gt;" in html
    assert "Fast <Attention>" not in html
