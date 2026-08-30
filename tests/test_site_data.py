from datetime import date

from radar.site_data import Ponto, SiteData


def _ponto(**kw):
    base = dict(arxiv_id="2608.11111", titulo="T", familia="cache_kv",
                pratica="adotar", independent_impls=3, total_impls=4,
                stars_total=10, citations=None, idade_dias=12,
                ganho_eixo="velocidade", ganho_fator=2.3,
                ganho_texto="2.3x", resumo="r", publicado="2026-08-01",
                score=1.2, scope="inferencia")
    return Ponto(**{**base, **kw})


def _dados(pontos, **kw):
    base = dict(dia="2026-08-30", cortes={}, rechecked_total=0)
    return SiteData(pontos=list(pontos), **{**base, **kw})


def test_o_ponto_carrega_o_que_a_pagina_desenha():
    p = _ponto()
    assert p.ganho_fator == 2.3
    assert p.citations is None


def test_a_cobertura_de_ganho_e_calculada_e_nao_informada():
    """O jornal decide sozinho se desenha a secao de avanco. Receber a
    cobertura pronta permitiria que quem monta o SiteData mentisse sobre
    a densidade do proprio dado."""
    d = _dados([_ponto(ganho_fator=2.0), _ponto(ganho_fator=None, ganho_eixo="nenhum"),
                _ponto(ganho_fator=None, ganho_eixo="nenhum"),
                _ponto(ganho_fator=None, ganho_eixo="nenhum")])
    assert d.cobertura_de_ganho == 0.25


def test_acervo_vazio_tem_cobertura_zero_e_nao_explode():
    assert _dados([]).cobertura_de_ganho == 0.0


def test_familias_presentes_sai_ordenada_e_sem_repeticao():
    d = _dados([_ponto(familia="outro"), _ponto(familia="cache_kv"),
                _ponto(familia="cache_kv")])
    assert d.familias_presentes == ["cache_kv", "outro"]


def test_o_destaque_e_o_de_maior_score():
    d = _dados([_ponto(arxiv_id="a", score=0.1), _ponto(arxiv_id="b", score=9.9),
                _ponto(arxiv_id="c", score=1.0)])
    assert d.destaque.arxiv_id == "b"


def test_acervo_vazio_nao_tem_destaque():
    assert _dados([]).destaque is None


def test_o_site_data_nao_faz_io():
    """A camada de desenho recebe dado pronto e nao sabe de onde ele veio.

    O plano do jornal afirmava que ja existia teste de pureza para `scoring`,
    `authorship` e `render`. Nao existia -- verificado em 2026-08-30. Este e
    o primeiro, e cobre os modulos novos e os antigos.
    """
    import radar.authorship, radar.render, radar.scoring, radar.site_data
    for modulo in (radar.site_data, radar.scoring, radar.authorship, radar.render):
        fonte = open(modulo.__file__, encoding="utf-8").read()
        for proibido in ("import sqlite3", "import httpx", "import anthropic"):
            assert proibido not in fonte, f"{modulo.__name__} importa {proibido}"


# --- a leitura que monta o SiteData ---

def test_a_leitura_monta_um_ponto_por_paper(store, paper_e_julgamento):
    d = store.site_data(date(2026, 8, 30))
    assert len(d.pontos) == 1
    assert d.pontos[0].arxiv_id == "2508.11111"
    assert d.pontos[0].familia == "cache_kv"
    assert d.pontos[0].scope == "inferencia"


def test_a_idade_vem_do_dia_passado_e_nao_do_relogio(store, paper_e_julgamento):
    """Usar `date.today()` faria o teste mudar de resultado todo dia e a
    pagina mentir quando gerada com atraso."""
    a = store.site_data(date(2026, 8, 30)).pontos[0].idade_dias
    b = store.site_data(date(2026, 9, 30)).pontos[0].idade_dias
    assert b - a == 31


def test_paper_sem_julgamento_nao_vira_ponto(store, paper_sem_julgamento):
    assert store.site_data(date(2026, 8, 30)).pontos == []


def test_a_leitura_usa_o_julgamento_e_o_sinal_MAIS_RECENTES(store, paper_rejulgado):
    p = store.site_data(date(2026, 8, 30)).pontos[0]
    assert p.familia == "outro"          # o segundo julgamento
    assert p.independent_impls == 9      # o segundo sinal


# --- fixtures ---

import pytest                                                    # noqa: E402

from radar.models import Judgment, Paper, ScoreResult, Signal    # noqa: E402
from radar.store import Store                                    # noqa: E402

_P = Paper(arxiv_id="2508.11111", title="T", abstract="A", authors=[],
           categories=["cs.LG"], published="2026-08-18")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    return s


def _sinal(indep, checked):
    return Signal(total_impls=indep, independent_impls=indep, velocity_14d=1,
                  stars_total=10, citations=None), checked


@pytest.fixture
def paper_sem_julgamento(store):
    store.upsert_paper(_P, seen_at="2026-08-29", scope="inferencia")
    s, c = _sinal(3, "2026-08-29")
    store.record_signal(_P.arxiv_id, s, score=1.2, checked_at=c)


@pytest.fixture
def paper_e_julgamento(store):
    store.upsert_paper(_P, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(_P.arxiv_id, Judgment(
        technique="t", familia="cache_kv", pratica="adotar",
        ganho_eixo="velocidade", ganho_fator=2.3, ganho_texto="2.3x",
        resumo="r", porque="p"), "claude-opus-5", "2026-08-29")
    s, c = _sinal(3, "2026-08-29")
    store.record_signal(_P.arxiv_id, s, score=1.2, checked_at=c)


@pytest.fixture
def paper_rejulgado(store, paper_e_julgamento):
    store.record_judgment(_P.arxiv_id, Judgment(
        technique="t2", familia="outro", pratica="observar",
        ganho_eixo="nenhum", ganho_fator=None, ganho_texto="",
        resumo="r2", porque="p2"), "claude-opus-5", "2026-08-30")
    s, c = _sinal(9, "2026-08-30")
    store.record_signal(_P.arxiv_id, s, score=0.9, checked_at=c)
