import pytest

from radar.leitura import Afirmacao, afirmacoes
from radar.site_data import Ponto, SiteData


def ponto(**kw):
    base = dict(arxiv_id="2608.11111", titulo="T", familia="cache_kv",
                pratica="adotar", independent_impls=0, total_impls=0,
                stars_total=0, citations=None, idade_dias=10,
                ganho_eixo="nenhum", ganho_fator=None, ganho_texto="",
                resumo="r", publicado="2026-08-01", score=1.0,
                scope="inferencia")
    return Ponto(**{**base, **kw})


def acervo_de(pontos, **kw):
    base = dict(dia="2026-08-30", cortes={}, rechecked_total=0)
    return SiteData(pontos=list(pontos), **{**base, **kw})


def _so(afs, trecho):
    """A afirmacao que contem o trecho, ou None. Nunca duas."""
    achadas = [a for a in afs if trecho in a.texto]
    assert len(achadas) <= 1, f"{trecho!r} casou com {len(achadas)} afirmacoes"
    return achadas[0] if achadas else None


@pytest.fixture
def acervo():
    """5 papers: 3 sem implementacao, 2 com. Um em 'outro', um com ganho."""
    return acervo_de([
        ponto(arxiv_id="a"), ponto(arxiv_id="b"),
        ponto(arxiv_id="c", familia="outro"),
        ponto(arxiv_id="d", independent_impls=2, stars_total=40),
        ponto(arxiv_id="e", independent_impls=1, stars_total=5,
              ganho_eixo="velocidade", ganho_fator=2.0),
    ])


@pytest.fixture
def acervo_vazio():
    return acervo_de([])


def test_a_afirmacao_carrega_texto_e_filtro():
    assert Afirmacao(texto="x", filtro={"familia": "cache_kv"}).filtro["familia"] == "cache_kv"


def test_afirmacao_sem_filtro_e_valida():
    assert Afirmacao(texto="x", filtro=None).filtro is None


def test_acervo_vazio_produz_lista_vazia(acervo_vazio):
    assert afirmacoes(acervo_vazio) == []


def test_a_leitura_nao_faz_io():
    import radar.leitura as m
    fonte = open(m.__file__, encoding="utf-8").read()
    for proibido in ("import sqlite3", "import httpx", "import anthropic"):
        assert proibido not in fonte
