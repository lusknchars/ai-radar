import pytest

from radar.config import Thresholds
from radar.models import Signal
from radar.scoring import evaluate

T = Thresholds(broke_out_stars=1000, broke_out_citations=200, score_floor=0.0)


def sig(indep, vel, stars, cites, total=None):
    return Signal(total_impls=total if total is not None else indep,
                  independent_impls=indep, velocity_14d=vel,
                  stars_total=stars, citations=cites)


def test_famous_paper_is_gated_out_by_stars():
    """GPTQ real: 103 impls, 3000 estrelas, 2500 citacoes. Ja estourou."""
    r = evaluate(sig(103, 2, 3000, 2500), T)
    assert r.value is None
    assert r.gated_by == "estrelas"


def test_paper_is_gated_out_by_citations_alone():
    r = evaluate(sig(5, 1, 50, 500), T)
    assert r.value is None
    assert r.gated_by == "citacoes"


def test_hidden_gem_outranks_everything_that_passes():
    gem = evaluate(sig(4, 3, 60, 0), T).value
    novo = evaluate(sig(2, 2, 15, 0), T).value
    revival = evaluate(sig(9, 7, 340, 120), T).value
    assert gem > novo > revival


def test_hidden_gem_score_matches_the_verified_value():
    """Regressao numerica: valor conferido na revisao da spec."""
    assert evaluate(sig(4, 3, 60, 0), T).value == pytest.approx(0.5332, abs=1e-4)


def test_no_independent_implementation_scores_zero():
    """So os autores publicaram. Nenhum sinal, mas passa o portao."""
    r = evaluate(sig(0, 0, 800, 30, total=3), T)
    assert r.value == pytest.approx(0.0)
    assert r.gated_by is None


def test_velocity_increases_the_score_at_equal_implementations():
    parado = evaluate(sig(5, 0, 100, 0), T).value
    acelerando = evaluate(sig(5, 5, 100, 0), T).value
    assert acelerando > parado


def test_attention_decreases_the_score_at_equal_implementations():
    obscuro = evaluate(sig(5, 2, 10, 0), T).value
    conhecido = evaluate(sig(5, 2, 900, 0), T).value
    assert obscuro > conhecido


def test_gate_is_exclusive_not_inclusive_at_the_boundary():
    exatamente = evaluate(sig(3, 1, 1000, 0), T)
    um_acima = evaluate(sig(3, 1, 1001, 0), T)
    assert exatamente.passed is True
    assert um_acima.passed is False


def test_stars_gate_is_reported_when_both_gates_would_fire():
    r = evaluate(sig(3, 1, 5000, 5000), T)
    assert r.gated_by == "estrelas"


def test_thresholds_are_respected_not_hardcoded():
    frouxo = Thresholds(broke_out_stars=100000, broke_out_citations=100000, score_floor=0.0)
    assert evaluate(sig(103, 2, 3000, 2500), frouxo).passed is True


def test_negative_input_is_rejected():
    with pytest.raises(ValueError, match="negativ"):
        evaluate(sig(-1, 0, 0, 0), T)


# --- Tarefa 2 do plano do segundo escopo ---
# Uso o helper `sig` do proprio arquivo em vez do Signal explicito do plano:
# mesmo comportamento, e mantem a idiomatica daqui.

def test_citacao_desconhecida_nao_dispara_o_portao():
    # Um paper sem citacao resolvida nao pode ser cortado por citacao:
    # nao sabemos o numero. Cortar aqui seria inventar dado.
    assert evaluate(sig(3, 1, 10, None), T).gated_by is None


def test_citacao_desconhecida_contribui_zero_para_atencao():
    # log1p(0) == 0, entao desconhecido e "ninguem citou" pontuam igual.
    # E deliberado: a alternativa seria descartar o paper, e um paper sem DOI
    # no OpenAlex nao merece sumir do radar por isso.
    assert evaluate(sig(3, 1, 10, None), T).value == evaluate(sig(3, 1, 10, 0), T).value


def test_citacao_conhecida_acima_do_limiar_ainda_corta():
    assert evaluate(sig(3, 1, 10, 201), T).gated_by == "citacoes"


def test_citacao_negativa_continua_sendo_erro():
    with pytest.raises(ValueError, match="citations"):
        evaluate(sig(3, 1, 10, -1), T)
