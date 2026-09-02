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


# --- Tarefas 2 a 6: as afirmações ---

@pytest.fixture
def acervo_grande():
    """1000 papers com sinal suficiente para as guardas de concentração."""
    return acervo_de(
        [ponto(arxiv_id=f"z{i}") for i in range(700)]
        + [ponto(arxiv_id=f"o{i}", familia="outro") for i in range(94)]
        # As tres familias com sinal sao calibradas para que NENHUMA passe
        # de metade sozinha e DUAS passem juntas -- e o caso que o teste do
        # "menor conjunto" precisa exercitar. Uma familia dominante faria o
        # teste passar sem provar nada sobre o acumulo.
        + [ponto(arxiv_id=f"q{i}", familia="quantizacao", independent_impls=2,
                 stars_total=5, ganho_eixo="velocidade", ganho_fator=2.0)
           for i in range(100)]                      # 200
        + [ponto(arxiv_id=f"k{i}", familia="cache_kv", independent_impls=3,
                 stars_total=3) for i in range(60)]  # 180
        + [ponto(arxiv_id=f"s{i}", familia="serving_e_batching",
                 independent_impls=2, stars_total=8) for i in range(46)])  # 92


def test_a_escassez_traz_contagem_e_denominador(acervo):
    a = _so(afirmacoes(acervo), "no independent implementation")
    assert "3 of 5" in a.texto
    assert "60%" in a.texto


def test_a_escassez_sai_mesmo_quando_e_cem_por_cento():
    assert _so(afirmacoes(acervo_de([ponto()])), "no independent implementation") is not None


def test_a_escassez_sai_mesmo_quando_e_zero():
    a = _so(afirmacoes(acervo_de([ponto(independent_impls=1)])), "no independent implementation")
    assert "0 of 1" in a.texto


def test_a_escassez_vem_primeiro(acervo):
    assert "no independent implementation" in afirmacoes(acervo)[0].texto


def test_a_fronteira_conta_quem_tem_impl_e_nao_tem_atencao():
    d = acervo_de([ponto(arxiv_id="a", independent_impls=3, stars_total=2),
                   ponto(arxiv_id="b", independent_impls=5, stars_total=9),
                   ponto(arxiv_id="c", independent_impls=3, stars_total=50)])
    assert "2 papers" in _so(afirmacoes(d), "research frontier").texto


def test_a_fronteira_e_omitida_quando_ninguem_qualifica(acervo):
    """Guarda que não passa OMITE. "0 papers estão na fronteira" é ruído;
    a ausência da frase já diz."""
    assert _so(afirmacoes(acervo), "research frontier") is None


def test_a_fronteira_exclui_quem_ja_tem_estrelas():
    d = acervo_de([ponto(independent_impls=9, stars_total=500)])
    assert _so(afirmacoes(d), "research frontier") is None


def test_a_fronteira_carrega_o_filtro_que_a_reproduz():
    d = acervo_de([ponto(independent_impls=3, stars_total=0)])
    assert _so(afirmacoes(d), "research frontier").filtro == {"ordenar": "impls"}


def test_a_concentracao_nomeia_o_menor_conjunto_acima_de_metade(acervo_grande):
    a = _so(afirmacoes(acervo_grande), "account for")
    assert "2 research areas" in a.texto
    assert "KV cache" in a.texto and "quantization" in a.texto


def test_a_concentracao_e_omitida_em_acervo_pequeno():
    """99 papers com MUITA implementação: a guarda de tamanho reprova sozinha."""
    d = acervo_de([ponto(arxiv_id=f"p{i}", independent_impls=9)
                   for i in range(99)])
    assert _so(afirmacoes(d), "account for") is None


def test_a_concentracao_e_omitida_com_poucas_implementacoes():
    """200 papers e 49 implementações: as guardas são conjuntivas."""
    d = acervo_de([ponto(arxiv_id=f"p{i}") for i in range(199)]
                  + [ponto(arxiv_id="x", independent_impls=49)])
    assert _so(afirmacoes(d), "account for") is None


def test_a_concentracao_carrega_um_filtro_de_familia(acervo_grande):
    a = _so(afirmacoes(acervo_grande), "account for")
    assert a.filtro["familia"] in ("cache_kv", "quantizacao")


def test_a_cobertura_traz_contagem_denominador_e_o_rotulo(acervo):
    a = _so(afirmacoes(acervo), "quantified gain")
    assert "1 of 5" in a.texto
    assert "author-reported" in a.texto.lower()


def test_a_cobertura_sai_mesmo_com_zero():
    assert _so(afirmacoes(acervo_de([ponto()])), "quantified gain") is not None


def test_a_taxonomia_reporta_a_taxa_de_outro(acervo):
    assert "1 of 5" in _so(afirmacoes(acervo), "'other'").texto


def test_a_taxonomia_traz_denominador_proprio_e_nao_por_acidente(acervo):
    """A redação do plano passava no teste de denominador pelo " das " de
    "nenhuma das dezoito famílias" — coincidência, não contrato."""
    import re
    assert re.search(r"\d+ of \d+ papers", _so(afirmacoes(acervo), "'other'").texto)


def test_a_taxonomia_sai_mesmo_sem_nenhum_outro():
    d = acervo_de([ponto(arxiv_id=f"p{i}") for i in range(5)])
    assert "0 of 5 papers" in _so(afirmacoes(d), "'other'").texto


def test_o_movimento_e_omitido_sem_historico(acervo_grande):
    assert _so(afirmacoes(acervo_grande), "gained an independent") is None


def test_o_movimento_e_omitido_com_menos_de_trinta_dias():
    d = acervo_de([ponto()], dias_de_coleta=29, papers_que_moveram=5)
    assert _so(afirmacoes(d), "gained an independent") is None


def test_o_movimento_e_omitido_quando_ninguem_moveu():
    d = acervo_de([ponto()], dias_de_coleta=60, papers_que_moveram=0)
    assert _so(afirmacoes(d), "gained an independent") is None


def test_o_movimento_aparece_com_historico():
    d = acervo_de([ponto()], dias_de_coleta=30, papers_que_moveram=2)
    assert "2 papers" in _so(afirmacoes(d), "gained an independent").texto


# --- Tarefa 7: as guardas de linguagem ---
# Só teste, e é deliberado: estas proibições são propriedades do CONJUNTO das
# frases, não de cada função. O valor delas é pegar a violação que a sétima
# afirmação vai introduzir daqui a seis meses.

CAUSAIS = ("porque", "devido", "graças a", "por causa", "resulta de",
           "leva a", "provoca", "explica")
PREVISAO = ("vai ", "deve ", "tende a", "provavelmente", "espera-se",
            "deverá", "no futuro")


@pytest.fixture
def acervo_completo(acervo_grande):
    """Todas as seis afirmações emitidas ao mesmo tempo."""
    d = SiteData(pontos=acervo_grande.pontos + [
        ponto(arxiv_id="f1", independent_impls=4, stars_total=1),
        ponto(arxiv_id="f2", independent_impls=3, stars_total=0)],
        dia="2026-08-30", cortes={}, rechecked_total=0,
        dias_de_coleta=45, papers_que_moveram=7)
    assert len(afirmacoes(d)) == 6, "a fixture precisa emitir as seis"
    return d


def test_nenhuma_afirmacao_usa_verbo_causal(acervo_completo):
    """O dado suporta "quantos", nunca "por quê"."""
    for a in afirmacoes(acervo_completo):
        for proibido in CAUSAIS:
            assert proibido not in a.texto.lower(), f"{proibido!r} em {a.texto!r}"


def test_nenhuma_afirmacao_preve(acervo_completo):
    for a in afirmacoes(acervo_completo):
        for proibido in PREVISAO:
            assert proibido not in a.texto.lower(), f"{proibido!r} em {a.texto!r}"


def test_nenhum_superlativo_sem_numero(acervo_completo):
    import re
    for a in afirmacoes(acervo_completo):
        if re.search(r"\bmais\b|\bmaior\b|\bmenor\b|\bmelhor\b", a.texto.lower()):
            assert re.search(r"\d", a.texto), a.texto


def test_toda_afirmacao_com_numero_traz_denominador(acervo_completo):
    """Percentual sem denominador é a forma mais fácil de enganar sem mentir."""
    for a in afirmacoes(acervo_completo):
        if "%" in a.texto:
            assert " of " in a.texto, a.texto


def test_todo_filtro_emitido_e_aplicavel(acervo_completo):
    validas = {"familia", "pratica", "ordenar"}
    ordenaveis = {"impls", "estrelas", "citacoes", "ganho", "score"}
    familias = {p.familia for p in acervo_completo.pontos}
    for a in afirmacoes(acervo_completo):
        if a.filtro is None:
            continue
        for chave, valor in a.filtro.items():
            assert chave in validas, chave
            if chave == "ordenar":
                assert valor in ordenaveis, valor
            if chave == "familia":
                assert valor in familias, valor


def test_toda_afirmacao_termina_em_ponto(acervo_completo):
    for a in afirmacoes(acervo_completo):
        assert a.texto.endswith("."), a.texto


def test_nenhuma_afirmacao_leva_emoji(acervo_completo):
    for a in afirmacoes(acervo_completo):
        assert all(ord(c) < 0x2190 or c in "—–" for c in a.texto), a.texto
