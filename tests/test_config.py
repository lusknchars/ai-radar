import pytest

from radar.config import (AGENT_SCOPE, DEFAULT_SCOPE, PUSH_CAP, ScopeConfig,
                          Thresholds, load_thresholds)
from radar.models import (FAMILIAS, GANHO_EIXOS, PRATICAS, Judgment,
                          Paper, Signal)


def test_scope_covers_the_five_arxiv_categories():
    assert set(DEFAULT_SCOPE.categories) == {"cs.LG", "cs.CL", "cs.DC", "cs.AR", "cs.PF"}


def test_scope_terms_are_non_empty_and_unique():
    terms = DEFAULT_SCOPE.terms
    assert len(terms) >= 10
    assert len(terms) == len(set(terms))


def test_scope_excludes_out_of_scope_domains():
    """O escopo de inferencia e estreito de proposito.

    Agentes nao estao aqui porque tem escopo proprio (AGENT_SCOPE), nao porque
    estejam fora do projeto -- a separacao e o que mantem os dois digests
    legiveis e os scores comparaveis dentro de cada literatura.
    """
    joined = " ".join(DEFAULT_SCOPE.terms).lower()
    for banned in ("vision", "speech", "robot", "agent", "retrieval"):
        assert banned not in joined


def test_paper_is_frozen_and_keyed_by_arxiv_id():
    p = Paper(arxiv_id="2508.12345", title="T", abstract="A",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-01")
    assert p.arxiv_id == "2508.12345"
    with pytest.raises(Exception):
        p.arxiv_id = "outro"


def test_paper_rejects_versioned_arxiv_id():
    """A chave canonica nao carrega versao: v1 e v2 sao o mesmo paper."""
    with pytest.raises(ValueError, match="versao"):
        Paper(arxiv_id="2508.12345v2", title="T", abstract="A",
              authors=[], categories=["cs.LG"], published="2026-08-01")


def test_paper_is_hashable_so_it_can_serve_as_a_dedup_key():
    """arxiv_id canonico existe para deduplicar. Um Paper nao-hashavel
    explodiria no primeiro `set(papers)` do pipeline."""
    p = Paper(arxiv_id="2508.12345", title="T", abstract="A",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-01")
    assert len({p, p}) == 1


def test_paper_coerces_sequences_so_contents_cannot_be_mutated():
    """frozen=True sozinho protege a reatribuicao, nao o conteudo da lista."""
    p = Paper(arxiv_id="2508.12345", title="T", abstract="A",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-01")
    assert p.authors == ("Elias Frantar",)
    assert p.categories == ("cs.LG",)
    with pytest.raises(AttributeError):
        p.authors.append("intruso")


def test_signal_defaults_citations_to_unknown():
    """O default virou `None`, e a mudanca e o ponto da tarefa 2.

    Antes era `0`, o que fazia "ninguem citou" e "nao perguntamos" ficarem
    indistinguiveis -- e foi assim que 1088 linhas ficaram constantes em zero
    participando da formula de atencao e do portao de estouro sem que ninguem
    percebesse.
    """
    s = Signal(total_impls=4, independent_impls=3, velocity_14d=1, stars_total=60)
    assert s.citations is None


def test_judgment_rejects_unknown_verdict():
    with pytest.raises(ValueError, match="runs_on_3090"):
        Judgment(technique="T", summary="S", runs_on_3090="talvez", rationale="R")


def test_judgment_accepts_the_three_valid_verdicts():
    for verdict in ("sim", "sim_com_ressalva", "nao"):
        j = Judgment(technique="T", summary="S", runs_on_3090=verdict, rationale="R")
        assert j.runs_on_3090 == verdict


def test_thresholds_come_from_env_with_documented_defaults(monkeypatch):
    monkeypatch.delenv("RADAR_BROKE_OUT_STARS", raising=False)
    monkeypatch.delenv("RADAR_BROKE_OUT_CITATIONS", raising=False)
    monkeypatch.delenv("RADAR_SCORE_FLOOR", raising=False)
    t = load_thresholds()
    assert t.broke_out_stars == 1000
    assert t.broke_out_citations == 200
    assert t.score_floor == 0.0        # nao calibrado; ver spec secao 10


def test_push_cap_is_three_and_lives_outside_thresholds():
    """O teto de 3 e rigido por decisao de produto, nao configuracao. Antes ele
    era campo de Thresholds E constante do render, e o pipeline fatiava pelo
    campo: um Thresholds com teto maior produzia mais de tres itens e so
    estourava no render, depois de as entregas ja terem sido gravadas. Nao
    existir como campo e o que torna esse caminho inexprimivel."""
    assert PUSH_CAP == 3
    with pytest.raises(TypeError):
        Thresholds(broke_out_stars=1000, broke_out_citations=200,
                   score_floor=0.0, push_cap=5)


def test_model_defaults_to_opus_5(monkeypatch):
    monkeypatch.delenv("RADAR_MODEL", raising=False)
    from radar.config import load_model
    assert load_model() == "claude-opus-5"


def test_recheck_limit_defaults_to_thirty(monkeypatch):
    monkeypatch.delenv("RADAR_RECHECK_LIMIT", raising=False)
    from radar.config import load_recheck_limit
    assert load_recheck_limit() == 30


def test_recheck_limit_is_configurable_unlike_the_push_cap(monkeypatch):
    """PUSH_CAP e decisao de produto e nao se mexe por ambiente. Este e
    orcamento operacional: muda com o tamanho do banco e com GH_TOKEN."""
    monkeypatch.setenv("RADAR_RECHECK_LIMIT", "5")
    from radar.config import load_recheck_limit
    assert load_recheck_limit() == 5


# --- Tarefa 1 do plano do segundo escopo ---

def test_cada_escopo_tem_nome_proprio():
    assert DEFAULT_SCOPE.name == "inferencia"
    assert AGENT_SCOPE.name == "agentes"


def test_o_escopo_de_agentes_exclui_cs_lg():
    # cs.LG triplica o volume com RL e robotica; medido em 2026-08-29:
    # 75 papers/dia com cs.LG contra 25/dia sem. Ver spec secao 2.
    assert "cs.LG" not in AGENT_SCOPE.categories
    assert set(AGENT_SCOPE.categories) == {"cs.AI", "cs.CL", "cs.SE", "cs.MA"}


def test_o_escopo_de_agentes_nao_carrega_termo_morto():
    # `tool retrieval` foi medido e nao trouxe um paper inedito sequer:
    # tudo que ele acha ja vem por `tool use` ou `tool calling`.
    assert "tool retrieval" not in AGENT_SCOPE.terms
    assert len(AGENT_SCOPE.terms) == 17


def test_os_dois_escopos_nao_compartilham_termo():
    assert not (set(AGENT_SCOPE.terms) & set(DEFAULT_SCOPE.terms))


def test_escopo_nao_pode_ser_construido_anonimo():
    """Nenhum campo de ScopeConfig pode ganhar default.

    A regra vem do plano (tarefa 1, passo 4): `name` sem default e o que
    impede uma linha sem escopo chegar a `papers`. O dataclass ja protege
    contra dar default so a `name` -- campo com default nao pode preceder
    campo sem, e a colecao quebra. Mas dar default aos TRES passa calado:
    verificado por mutacao em 2026-08-29, 199 de 199 testes seguiram verdes.
    E essa variante que este teste tranca.
    """
    with pytest.raises(TypeError):
        ScopeConfig()


# --- Tarefa 4 do plano do segundo escopo ---
# O plano pedia estes testes em tests/test_models.py, que nao existe: os
# modelos sao testados aqui desde o inicio do projeto. Segui a convencao do
# repositorio.

def julgamento(**kw):
    base = dict(technique="t", familia="cache_kv", pratica="testar",
                ganho_eixo="velocidade", ganho_fator=2.3,
                ganho_texto="2.3x mais rapido que vLLM",
                resumo="r", porque="p")
    return Judgment(**{**base, **kw})


def test_a_taxonomia_tem_dezenove_valores_com_o_escape():
    assert len(FAMILIAS) == 19
    assert "outro" in FAMILIAS


def test_familia_fora_da_taxonomia_e_recusada():
    with pytest.raises(ValueError, match="familia"):
        julgamento(familia="quantizacao_magica")


def test_pratica_fora_do_conjunto_e_recusada():
    assert PRATICAS == frozenset({"adotar", "testar", "observar", "nao_aplica"})
    with pytest.raises(ValueError, match="pratica"):
        julgamento(pratica="talvez")


def test_ganho_eixo_fora_do_conjunto_e_recusado():
    assert GANHO_EIXOS == frozenset(
        {"velocidade", "memoria", "custo", "qualidade", "nenhum"})
    with pytest.raises(ValueError, match="ganho_eixo"):
        julgamento(ganho_eixo="elegancia")


def test_sem_eixo_de_ganho_nao_pode_haver_fator():
    # Um fator sem dimensao e numero solto: se o paper nao alega nada, nao
    # existe 2.3 de coisa nenhuma.
    with pytest.raises(ValueError, match="ganho_fator"):
        julgamento(ganho_eixo="nenhum", ganho_fator=2.3)


def test_sem_eixo_de_ganho_o_fator_nulo_e_valido():
    assert julgamento(ganho_eixo="nenhum", ganho_fator=None,
                      ganho_texto="").ganho_fator is None


def test_fator_precisa_ser_razao_de_melhora():
    # Fator e razao. Zero e negativo nao sao razao de melhora, e um zero aqui
    # viraria coordenada invalida na escala log do grafico do jornal.
    for ruim in (0, -1.0, 0.0):
        with pytest.raises(ValueError, match="ganho_fator"):
            julgamento(ganho_fator=ruim)


def test_fator_abaixo_de_um_e_valido_porque_e_piora_relativa_declarada():
    # 0.8 significa "entrega 80% do baseline". E razao positiva, e o paper
    # pode legitimamente alegar isso ao trocar qualidade por velocidade.
    assert julgamento(ganho_fator=0.8).ganho_fator == 0.8


def test_as_familias_cobrem_os_dois_escopos():
    # Familia nao e derivada de escopo: um paper descoberto pelo escopo de
    # agentes pode ser legitimamente `cache_kv`. Os dois campos existem
    # separados justamente por isso.
    assert {"quantizacao", "cache_kv"} <= FAMILIAS          # inferencia
    assert {"uso_de_ferramenta", "memoria_e_contexto"} <= FAMILIAS   # agentes
