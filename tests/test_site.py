import pytest

from radar.models import FAMILIAS
from radar.site import CORES_FAMILIA, render_site
from radar.site_data import Ponto, SiteData


def ponto(**kw):
    base = dict(arxiv_id="2608.11111", titulo="Kernel INT4 fundido",
                familia="cache_kv", pratica="adotar", independent_impls=3,
                total_impls=4, stars_total=10, citations=None, idade_dias=12,
                ganho_eixo="velocidade", ganho_fator=2.3, ganho_texto="2.3x",
                resumo="Troca o kernel FP16.", publicado="2026-08-01",
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


def test_toda_familia_tem_cor_propria():
    """Cor significa familia, e so. Uma familia sem cor cairia em
    `currentColor` e duas familias virariam o mesmo ponto no grafico."""
    assert set(CORES_FAMILIA) == FAMILIAS
    assert len(set(CORES_FAMILIA.values())) == len(FAMILIAS)


def test_a_pagina_nao_faz_requisicao_externa(dados):
    """"Sem dependencia externa" e literal: nada de CDN, nada de fonte
    remota, nenhuma requisicao saindo da pagina. Links para o arXiv sao
    navegacao do leitor, nao carregamento de recurso."""
    html = render_site(dados).replace("https://arxiv.org", "")
    for proibido in ("https://", "http://", "//cdn", "@import", "<script src"):
        assert proibido not in html


def test_a_pagina_define_tema_claro_e_escuro(dados):
    html = render_site(dados)
    assert "prefers-color-scheme: dark" in html
    assert ":root" in html


def test_a_fonte_e_do_sistema(dados):
    assert "system-ui" in render_site(dados)


def test_acervo_vazio_gera_pagina_valida(dados_vazio):
    """Nao excecao, nao HTML quebrado: a pagina diz que nao ha dado."""
    html = render_site(dados_vazio)
    assert "</html>" in html
    assert "nenhum paper" in html.lower()


def test_o_enquadramento_esta_presente_e_e_fixo(dados):
    """Contrato com o leitor: o que o radar mede e o que ele deliberadamente
    NAO mede. E escrito a mao e versionado, nao gerado."""
    html = render_site(dados)
    assert "implementações independentes" in html
    assert "não mede" in html


def test_o_cabecalho_traz_os_numeros_do_acervo(dados):
    html = render_site(dados)
    assert "2026-08-30" in html
    assert ">2<" in html          # dois papers


def test_o_titulo_da_aba_nomeia_o_projeto_e_o_dia(dados):
    assert "<title>ai-radar — 2026-08-30</title>" in render_site(dados)


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
    for rotulo in ("estrelas no GitHub", "dias desde a publicação",
                   "implementações totais"):
        assert rotulo in html


def test_o_portao_de_estouro_esta_rotulado(dados):
    """Quem olha precisa entender por que um paper muito citado nao aparece,
    sem ler documentacao."""
    html = render_site(dados)
    assert "1000" in html
    assert "estourou" in html.lower()


def test_a_legenda_lista_so_as_familias_presentes(dados):
    html = render_site(dados)
    assert "cache_kv" in html
    assert "destilacao" not in html      # ausente do acervo de teste


def test_o_js_e_inline_e_nao_carrega_nada(dados):
    html = render_site(dados)
    assert "<script>" in html
    assert "<script src" not in html


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
    assert "alegado pelos autores, não verificado" in render_site(dados)


def test_a_secao_some_com_cobertura_abaixo_de_35_por_cento(dados_ganho_ralo):
    """Grafico sobre dado ralo e pior que grafico ausente."""
    assert dados_ganho_ralo.cobertura_de_ganho < 0.35
    assert "avanço alegado" not in render_site(dados_ganho_ralo).lower()


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
    ganhos = re.findall(r"ganho [\d.]+x em", html)
    if ganhos:
        assert html.count("alegado pelos autores, não verificado") >= len(ganhos)


def test_com_cobertura_suficiente_a_secao_aparece(dados):
    assert dados.cobertura_de_ganho >= 0.35
    assert "avanço alegado" in render_site(dados).lower()


# --- Tarefa 7: famílias no tempo, e a tabela ---

def test_a_tabela_traz_uma_linha_por_paper(dados):
    assert render_site(dados).count('class="linha"') == len(dados.pontos)


def test_citacao_desconhecida_vira_travessao_e_nao_zero():
    """Nao-resolvido nao e zero: ~8% dos papers nao tem DOI no OpenAlex.
    Renderizar 0 ali seria o mesmo defeito que as tarefas 2, 3 e 8 do plano
    anterior consertaram, reintroduzido pela camada de apresentacao."""
    import re
    # Nao `"—" in html`: o travessao tambem aparece na coluna de ganho, entao
    # aquela forma passava mesmo com a citacao virando zero. Verificado por
    # mutacao em 2026-08-30. A afirmacao precisa ser sobre A CELULA.
    html = render_site(_acervo([ponto(citations=None, ganho_fator=2.0)]))
    celulas = re.findall(r'<td class="num">([^<]*)</td>',
                         re.search(r'<tr class="linha".*?</tr>', html, re.S).group(0))
    assert celulas[2] == "—"        # impls, estrelas, CITACOES, ganho
    assert celulas[3] == "2x"       # o ganho tem numero, provando que nao e ele


def test_citacao_zero_e_renderizada_como_zero():
    html = render_site(_acervo([ponto(citations=0, arxiv_id="2608.33333")]))
    import re
    linha = re.search(r'<tr class="linha".*?</tr>', html, re.S).group(0)
    assert ">0<" in linha


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
     "is_author": 1, "is_author_reason": "sobrenome do autor no dono"},
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
    assert "sobrenome do autor no dono" in html
    assert "tridao/flash-attn" in html
    assert "acme/fa-triton" in html


def test_o_destaque_separa_autor_de_independente():
    d = SiteData(pontos=[ponto()], dia="2026-08-30", cortes={},
                 rechecked_total=0, repos_do_destaque=REPOS)
    html = render_site(d)
    assert "independente" in html
    assert "autor" in html


def test_destaque_sem_repos_diz_isso_em_vez_de_sumir():
    html = render_site(_acervo([ponto()]))
    assert "nenhum repositório" in html.lower()


def test_todos_os_cortes_do_dia_aparecem_com_contagem(dados):
    """Restricao global do projeto: todo corte e contado e chega ao leitor."""
    html = render_site(dados)
    for motivo, n in dados.cortes.items():
        # Renderizado legivel: `abaixo do piso`, nao `abaixo_do_piso`. O que a
        # restricao global exige e que o corte CHEGUE ao leitor, com contagem.
        assert motivo.replace("_", " ") in html
        assert f"<b>{n}</b>" in html


def test_dia_sem_corte_nenhum_ainda_mostra_a_secao():
    html = render_site(_acervo([ponto()]))
    assert "ficou de fora" in html.lower()
    assert "nenhum corte" in html.lower()


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
    assert f"de {len(dados.pontos)}" in html


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
    frase = re.search(r'<p class="frase"[^>]*>.*?não têm.*?</p>', html, re.S)
    assert frase and "data-aplicar" not in frase.group(0)


def test_acervo_vazio_nao_desenha_o_bloco(dados_vazio):
    assert 'class="leitura"' not in render_site(dados_vazio)


def test_os_numeros_do_bloco_ganham_destaque(dados):
    """Prosa com número destacado: o olho acha o número sem o cartão."""
    assert '<b class="n">' in render_site(dados)
