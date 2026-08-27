import pytest

from radar.config import DEFAULT_SCOPE, Thresholds, load_thresholds
from radar.models import Judgment, Paper, Repo, Signal


def test_scope_covers_the_five_arxiv_categories():
    assert set(DEFAULT_SCOPE.categories) == {"cs.LG", "cs.CL", "cs.DC", "cs.AR", "cs.PF"}


def test_scope_terms_are_non_empty_and_unique():
    terms = DEFAULT_SCOPE.terms
    assert len(terms) >= 10
    assert len(terms) == len(set(terms))


def test_scope_excludes_out_of_scope_domains():
    """O escopo estreito e deliberado: visao, audio e agentes ficam de fora."""
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


def test_signal_defaults_citations_to_zero():
    s = Signal(total_impls=4, independent_impls=3, velocity_14d=1, stars_total=60)
    assert s.citations == 0


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
    assert t.push_cap == 3


def test_push_cap_cannot_be_raised_by_env(monkeypatch):
    """O teto de 3 e rigido por decisao de produto, nao configuracao."""
    monkeypatch.setenv("RADAR_PUSH_CAP", "10")
    assert load_thresholds().push_cap == 3


def test_model_defaults_to_opus_5(monkeypatch):
    monkeypatch.delenv("RADAR_MODEL", raising=False)
    from radar.config import load_model
    assert load_model() == "claude-opus-5"
