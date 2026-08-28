import pytest

from radar.models import Judgment, Paper, Repo, RepoClassification, Signal
from radar.store import Store

P = Paper(arxiv_id="2508.11111", title="T", abstract="A",
          authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-20")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    return s


def test_upsert_is_idempotent(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.upsert_paper(P, seen_at="2026-08-28")
    assert len(store.all_papers()) == 1


def test_first_seen_is_preserved_across_upserts(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.upsert_paper(P, seen_at="2026-08-28")
    assert store.all_papers()[0]["first_seen"] == "2026-08-27"


def test_known_ids_returns_only_the_keys(store):
    """O filtro de "ja conhecido" roda todo dia sobre a tabela inteira; carregar
    titulo e abstract de cada paper ja visto para montar um conjunto de chaves
    e desperdicio que cresce com o banco."""
    store.upsert_paper(P, seen_at="2026-08-27")
    assert store.known_ids() == {P.arxiv_id}


def test_known_ids_is_empty_on_a_fresh_database(store):
    assert store.known_ids() == set()


def test_signals_are_append_only(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(2, 2, 1, 40), score=0.4, checked_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(9, 9, 7, 340), score=0.3, checked_at="2026-09-17")
    assert len(store.signal_history(P.arxiv_id)) == 2


def test_delta_reports_growth_between_first_and_last_check(store):
    """Ressurreicao: paper antigo voltando a ser implementado."""
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(2, 2, 0, 300), score=0.1, checked_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(9, 9, 7, 340), score=0.4, checked_at="2026-09-17")
    delta = store.signal_delta(P.arxiv_id)
    assert delta["independent_from"] == 2
    assert delta["independent_to"] == 9
    assert delta["days"] == 21


def test_delta_is_none_with_a_single_observation(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(2, 2, 0, 40), score=0.4, checked_at="2026-08-27")
    assert store.signal_delta(P.arxiv_id) is None


def test_repos_persist_the_authorship_reason(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_repos(P.arxiv_id, [
        RepoClassification(Repo("a/b", "a", 10, "2024-01-01T00:00:00Z"),
                           is_author=True, reason="sobrenome"),
        RepoClassification(Repo("c/d", "c", 5, "2024-02-01T00:00:00Z"),
                           is_author=False, reason=None),
    ])
    rows = {r["full_name"]: r for r in store.repos_for(P.arxiv_id)}
    assert rows["a/b"]["is_author_reason"] == "sobrenome"
    assert rows["c/d"]["is_author_reason"] is None


def test_recording_repos_replaces_the_previous_classification(store):
    """Uma classificacao posterior manda: repo que saiu da busca nao cita mais
    o paper. Acumular linhas antigas deixa o markdown do dia contando repos que
    o sinal ja nao conta."""
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_repos(P.arxiv_id, [
        RepoClassification(Repo("a/b", "a", 10, "2024-01-01T00:00:00Z"),
                           is_author=True, reason="sobrenome"),
        RepoClassification(Repo("sumiu/depois", "sumiu", 3, "2024-02-01T00:00:00Z"),
                           is_author=False, reason=None),
    ])
    store.record_repos(P.arxiv_id, [
        RepoClassification(Repo("a/b", "a", 12, "2024-01-01T00:00:00Z"),
                           is_author=True, reason="sobrenome"),
    ])
    rows = store.repos_for(P.arxiv_id)
    assert [r["full_name"] for r in rows] == ["a/b"]
    assert rows[0]["stars"] == 12


def test_repos_of_one_paper_are_not_erased_by_another(store):
    """O DELETE e por arxiv_id: gravar o vizinho nao pode apagar este."""
    outro = Paper(arxiv_id="2508.22222", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-20")
    store.upsert_paper(P, seen_at="2026-08-27")
    store.upsert_paper(outro, seen_at="2026-08-27")
    store.record_repos(P.arxiv_id, [
        RepoClassification(Repo("a/b", "a", 10, "2024-01-01T00:00:00Z"),
                           is_author=False, reason=None)])
    store.record_repos(outro.arxiv_id, [
        RepoClassification(Repo("c/d", "c", 5, "2024-01-01T00:00:00Z"),
                           is_author=False, reason=None)])
    assert [r["full_name"] for r in store.repos_for(P.arxiv_id)] == ["a/b"]
    assert [r["full_name"] for r in store.repos_for(outro.arxiv_id)] == ["c/d"]


def test_delivered_paper_is_not_delivered_again(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    assert store.was_delivered(P.arxiv_id, channel="telegram") is False
    store.mark_delivered(P.arxiv_id, channel="telegram", at="2026-08-27", rank=1)
    assert store.was_delivered(P.arxiv_id, channel="telegram") is True


def test_delivery_channels_are_independent(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.mark_delivered(P.arxiv_id, channel="markdown", at="2026-08-27", rank=None)
    assert store.was_delivered(P.arxiv_id, channel="telegram") is False


def test_judgment_round_trips(store):
    """Os quatro campos, com valores distintos de proposito: `record_judgment`
    liga quatro strings posicionalmente, entao uma troca entre `summary` e
    `rationale` passaria batido num teste que so confere `technique`."""
    store.upsert_paper(P, seen_at="2026-08-27")
    j = Judgment(technique="Kernel INT4 fundido",
                 summary="Satura banda de memoria em batch unitario.",
                 runs_on_3090="sim_com_ressalva",
                 rationale="Roda em Ampere, mas so ate 13B em 24 GB.")
    store.record_judgment(P.arxiv_id, j, model="claude-opus-5", judged_at="2026-08-27")
    assert store.latest_judgment(P.arxiv_id) == j


def test_stalest_papers_come_first(store):
    for pid, seen in (("2508.00001", "2026-08-01"), ("2508.00002", "2026-08-25")):
        paper = Paper(arxiv_id=pid, title="T", abstract="A", authors=[],
                      categories=["cs.LG"], published="2026-08-01")
        store.upsert_paper(paper, seen_at=seen)
        store.touch_checked(pid, at=seen)
    assert [p["arxiv_id"] for p in store.stalest_papers(limit=2)] == ["2508.00001", "2508.00002"]


def test_stalest_respects_the_limit(store):
    for i in range(5):
        paper = Paper(arxiv_id=f"2508.0000{i}", title="T", abstract="A", authors=[],
                      categories=["cs.LG"], published="2026-08-01")
        store.upsert_paper(paper, seen_at="2026-08-01")
        store.touch_checked(paper.arxiv_id, at="2026-08-01")
    assert len(store.stalest_papers(limit=3)) == 3


def test_init_schema_is_idempotent(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    s.init_schema()
    assert s.all_papers() == []


def test_papers_to_recheck_returns_paper_objects(store):
    """Quem codificou o JSON e quem decodifica. O pipeline nao deve saber
    que authors e categories viajam serializados."""
    store.upsert_paper(P, seen_at="2026-08-27")
    papers = store.papers_to_recheck(limit=10)
    assert len(papers) == 1
    assert isinstance(papers[0], Paper)
    assert papers[0].arxiv_id == P.arxiv_id


def test_papers_to_recheck_round_trips_sequences_as_tuples(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    recuperado = store.papers_to_recheck(limit=10)[0]
    assert recuperado.authors == P.authors
    assert recuperado.categories == P.categories
    assert isinstance(recuperado.authors, tuple)


def test_papers_to_recheck_puts_never_checked_first(store):
    velho = Paper(arxiv_id="2508.00001", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01")
    nunca = Paper(arxiv_id="2508.00002", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01")
    store.upsert_paper(velho, seen_at="2026-08-01")
    store.touch_checked(velho.arxiv_id, at="2026-08-01")
    store.upsert_paper(nunca, seen_at="2026-08-01")
    assert [p.arxiv_id for p in store.papers_to_recheck(limit=10)] == \
        ["2508.00002", "2508.00001"]


def test_papers_to_recheck_respects_the_limit(store):
    for i in range(5):
        store.upsert_paper(
            Paper(arxiv_id=f"2508.0000{i}", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01"), seen_at="2026-08-01")
    assert len(store.papers_to_recheck(limit=3)) == 3


def test_papers_to_recheck_is_empty_on_a_fresh_database(store):
    assert store.papers_to_recheck(limit=10) == []
