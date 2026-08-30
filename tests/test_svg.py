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
