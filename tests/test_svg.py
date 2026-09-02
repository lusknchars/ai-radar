import pytest

from radar.site_data import Ponto
from radar.svg import ALTURA, LARGURA, METRICAS_X, PAD, projetar, render_scatter

CORES = {"cache_kv": "#abc", "outro": "#def"}


def ponto(**kw):
    base = dict(arxiv_id="2608.11111", titulo="T", familia="cache_kv",
                pratica="adotar", independent_impls=3, total_impls=4,
                stars_total=10, citations=None, idade_dias=12,
                ganho_eixo="velocidade", ganho_fator=2.3, ganho_texto="2.3x",
                resumo="r", publicado="2026-08-01", score=1.2,
                scope="inferencia")
    return Ponto(**{**base, **kw})


TRES = [ponto(arxiv_id="a", independent_impls=1, stars_total=0),
        ponto(arxiv_id="b", independent_impls=5, stars_total=50),
        ponto(arxiv_id="c", independent_impls=9, stars_total=100,
              familia="outro")]


# --- projecao ---

def test_o_maximo_cai_na_borda_util_direita():
    assert projetar(10, 10, LARGURA, PAD) == LARGURA - PAD


def test_o_zero_cai_na_borda_util_esquerda():
    assert projetar(0, 10, LARGURA, PAD) == PAD


def test_o_meio_cai_no_meio():
    assert projetar(5, 10, LARGURA, PAD) == PAD + (LARGURA - 2 * PAD) / 2


def test_o_eixo_invertido_espelha():
    """Em SVG o y cresce para baixo; o valor alto tem que subir."""
    assert projetar(10, 10, ALTURA, PAD, inverter=True) == PAD
    assert projetar(0, 10, ALTURA, PAD, inverter=True) == ALTURA - PAD


def test_maximo_zero_nao_divide_por_zero():
    """Acervo em que todo mundo tem zero estrela e caso real no dia 1."""
    assert projetar(0, 0, LARGURA, PAD) == PAD


# --- scatter ---

def test_o_scatter_desenha_um_circulo_por_ponto():
    assert render_scatter(TRES, "stars_total", CORES).count("<circle") == 3


def test_o_scatter_publica_eixos_grade_e_valores_de_referencia():
    svg = render_scatter(TRES, "stars_total", CORES)
    assert 'class="chart-grid"' in svg
    assert 'class="x-axis"' in svg
    assert 'class="y-axis"' in svg
    assert "GitHub stars" in svg
    assert "independent implementations" in svg


def test_a_cor_do_circulo_vem_da_familia():
    svg = render_scatter(TRES, "stars_total", CORES)
    assert 'fill="#abc"' in svg
    assert 'fill="#def"' in svg


def test_o_ponto_com_mais_impls_fica_acima_do_com_menos():
    """A afirmacao central do grafico. Sem ela, inverter o eixo y passaria
    despercebido e a fronteira apareceria de cabeca para baixo."""
    import re
    svg = render_scatter(TRES, "stars_total", CORES)
    ys = [float(m) for m in re.findall(r'cy="([\d.]+)"', svg)]
    assert ys[0] > ys[2]      # 1 impl mais abaixo que 9 impls


def test_o_scatter_vazio_gera_svg_valido_e_nao_explode():
    svg = render_scatter([], "stars_total", {})
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "<circle" not in svg


def test_metrica_desconhecida_e_recusada():
    with pytest.raises(ValueError, match="metrica"):
        render_scatter(TRES, "popularidade", CORES)


def test_citacao_nao_e_metrica_de_eixo():
    """Decisao travada da spec: o acervo e jovem demais para o eixo
    discriminar -- dos 25 papers mais antigos, 8 tem citacao e o resto tem
    zero legitimo. Um eixo em que tudo empilha no zero nao separa nada."""
    assert "citations" not in METRICAS_X
    with pytest.raises(ValueError):
        render_scatter(TRES, "citations", CORES)


def test_o_titulo_do_ponto_e_escapado():
    """Titulo de paper com `&` ou `<` quebraria o SVG silenciosamente."""
    svg = render_scatter([ponto(titulo="A & B <hack>")], "stars_total", CORES)
    assert "&amp;" in svg and "&lt;hack&gt;" in svg
    assert "<hack>" not in svg


def test_familia_sem_cor_declarada_nao_quebra_o_desenho():
    svg = render_scatter([ponto(familia="destilacao")], "stars_total", {})
    assert "<circle" in svg


# --- Tarefa 3: pequenos multiplos ---

import re                                                        # noqa: E402

from radar.svg import render_pequenos_multiplos                  # noqa: E402


def _alturas(svg):
    return [float(x) for x in re.findall(r'<rect[^>]*height="([\d.]+)"', svg)]


def test_um_painel_por_familia_pedida():
    s = {"cache_kv": {"2026-07": 3}, "outro": {"2026-07": 1}}
    svg = render_pequenos_multiplos(s, ["cache_kv", "outro"], CORES)
    assert svg.count('<g class="painel"') == 2


def test_a_escala_e_compartilhada_entre_os_paineis():
    """Escala por painel faria 3 papers e 300 desenharem a mesma altura, e a
    comparacao entre familias -- a unica pergunta que a secao responde --
    passaria a mentir."""
    s = {"a": {"2026-07": 1}, "b": {"2026-07": 100}}
    alturas = _alturas(render_pequenos_multiplos(s, ["a", "b"], {}))
    assert alturas[0] < alturas[1] / 10


def test_familia_sem_dado_ainda_ganha_painel_vazio():
    """Ausencia e informacao: um painel vazio diz "nada saiu nesta familia",
    e some-la faria parecer que a familia nao existe."""
    svg = render_pequenos_multiplos({"a": {"2026-07": 2}}, ["a", "b"], {})
    assert svg.count('<g class="painel"') == 2


def test_o_rotulo_da_familia_aparece_em_cada_painel():
    svg = render_pequenos_multiplos({"cache_kv": {"2026-07": 2}}, ["cache_kv"], CORES)
    assert "cache_kv" in svg


def test_series_vazias_geram_svg_valido():
    svg = render_pequenos_multiplos({}, [], {})
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_todo_mundo_em_zero_nao_divide_por_zero():
    svg = render_pequenos_multiplos({"a": {"2026-07": 0}}, ["a"], {})
    assert "<svg" in svg
    assert all(h >= 0 for h in _alturas(svg))


def test_os_meses_saem_em_ordem_cronologica():
    s = {"a": {"2026-09": 1, "2026-07": 9, "2026-08": 5}}
    alturas = _alturas(render_pequenos_multiplos(s, ["a"], {}))
    assert alturas == sorted(alturas, reverse=True)   # 9, 5, 1


def test_o_mes_ocupa_a_mesma_coluna_em_todas_as_familias():
    """Agosto não pode virar a primeira coluna só porque julho está ausente."""
    svg = render_pequenos_multiplos(
        {"a": {"2026-07": 2, "2026-08": 3}, "b": {"2026-08": 1}},
        ["a", "b"], CORES,
    )
    grupos = re.findall(r'<g class="painel".*?</g>', svg)
    agosto_a = re.search(
        r'<rect[^>]*data-month="2026-08"[^>]*x="([\d.]+)"', grupos[0])
    agosto_b = re.search(
        r'<rect[^>]*data-month="2026-08"[^>]*x="([\d.]+)"', grupos[1])
    assert agosto_a and agosto_b
    assert agosto_a.group(1) == agosto_b.group(1)


# --- Tarefa 6: o avanço alegado ---

from radar.svg import render_avanco                              # noqa: E402


def pa(fator, mes="2026-07", familia="cache_kv"):
    return ponto(ganho_fator=fator, publicado=f"{mes}-01", familia=familia,
                 ganho_eixo="velocidade" if fator else "nenhum")


def test_a_escala_log_recusa_fator_nao_positivo():
    """Um zero aqui viraria coordenada NaN no SVG, e o grafico sairia
    silenciosamente errado em vez de quebrar alto."""
    for ruim in (0.0, -1.0):
        with pytest.raises(ValueError, match="fator"):
            render_avanco([ponto(ganho_fator=ruim)], CORES)


def test_papers_sem_fator_sao_ignorados_e_nao_zerados():
    svg = render_avanco([pa(2.0), pa(None), pa(None)], CORES)
    assert svg.count("<circle") == 1


def test_avanco_mostra_baseline_e_escala_logaritmica():
    svg = render_avanco([pa(2.0), pa(10.0, mes="2026-08")], CORES)
    assert 'class="chart-grid"' in svg
    assert 'class="baseline"' in svg
    assert "1x" in svg
    assert "log scale" in svg


def test_a_mediana_trimestral_exige_cinco_papers():
    """Abaixo de cinco a mediana e ruido com aparencia de tendencia."""
    quatro = [pa(2.0) for _ in range(4)]
    assert 'class="mediana"' not in render_avanco(quatro, CORES)
    assert 'class="mediana"' in render_avanco(quatro + [pa(2.0)], CORES)


def test_a_mediana_conta_por_familia_e_por_trimestre():
    # Cinco no mesmo trimestre mas em familias diferentes nao formam mediana.
    misto = [pa(2.0, familia=f) for f in
             ("cache_kv", "outro", "quantizacao", "destilacao", "cache_kv")]
    assert 'class="mediana"' not in render_avanco(misto, CORES)


def test_avanco_vazio_gera_svg_valido():
    svg = render_avanco([], CORES)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
