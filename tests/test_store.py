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
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    store.upsert_paper(P, seen_at="2026-08-28", scope="teste")
    assert len(store.all_papers()) == 1


def test_first_seen_is_preserved_across_upserts(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    store.upsert_paper(P, seen_at="2026-08-28", scope="teste")
    assert store.all_papers()[0]["first_seen"] == "2026-08-27"


def test_known_ids_returns_only_the_keys(store):
    """O filtro de "ja conhecido" roda todo dia sobre a tabela inteira; carregar
    titulo e abstract de cada paper ja visto para montar um conjunto de chaves
    e desperdicio que cresce com o banco."""
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    assert store.known_ids() == {P.arxiv_id}


def test_known_ids_is_empty_on_a_fresh_database(store):
    assert store.known_ids() == set()


def test_get_paper_returns_the_domain_object_or_none(store):
    assert store.get_paper(P.arxiv_id) is None
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    assert store.get_paper(P.arxiv_id) == P


def test_signals_are_append_only(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    store.record_signal(P.arxiv_id, Signal(2, 2, 1, 40), score=0.4, checked_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(9, 9, 7, 340), score=0.3, checked_at="2026-09-17")
    assert len(store.signal_history(P.arxiv_id)) == 2


def test_delta_reports_growth_between_first_and_last_check(store):
    """Ressurreicao: paper antigo voltando a ser implementado."""
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    store.record_signal(P.arxiv_id, Signal(2, 2, 0, 300), score=0.1, checked_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(9, 9, 7, 340), score=0.4, checked_at="2026-09-17")
    delta = store.signal_delta(P.arxiv_id)
    assert delta["independent_from"] == 2
    assert delta["independent_to"] == 9
    assert delta["days"] == 21


def test_delta_is_none_with_a_single_observation(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    store.record_signal(P.arxiv_id, Signal(2, 2, 0, 40), score=0.4, checked_at="2026-08-27")
    assert store.signal_delta(P.arxiv_id) is None


def test_repos_persist_the_authorship_reason(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
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
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
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
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    store.upsert_paper(outro, seen_at="2026-08-27", scope="teste")
    store.record_repos(P.arxiv_id, [
        RepoClassification(Repo("a/b", "a", 10, "2024-01-01T00:00:00Z"),
                           is_author=False, reason=None)])
    store.record_repos(outro.arxiv_id, [
        RepoClassification(Repo("c/d", "c", 5, "2024-01-01T00:00:00Z"),
                           is_author=False, reason=None)])
    assert [r["full_name"] for r in store.repos_for(P.arxiv_id)] == ["a/b"]
    assert [r["full_name"] for r in store.repos_for(outro.arxiv_id)] == ["c/d"]


def test_delivered_paper_is_not_delivered_again(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    assert store.was_delivered(P.arxiv_id, channel="telegram") is False
    store.mark_delivered(P.arxiv_id, channel="telegram", at="2026-08-27", rank=1)
    assert store.was_delivered(P.arxiv_id, channel="telegram") is True


def test_delivery_channels_are_independent(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    store.mark_delivered(P.arxiv_id, channel="markdown", at="2026-08-27", rank=None)
    assert store.was_delivered(P.arxiv_id, channel="telegram") is False


def test_judgment_round_trips(store):
    """Todos os campos com valores distintos, de proposito.

    `record_judgment` liga os valores POSICIONALMENTE, e depois da tarefa 6
    sao onze em vez de quatro. Uma troca entre `resumo` e `porque`, ou entre
    `technique` e `ganho_texto`, passaria batido num teste que so confere um
    campo. Cada string abaixo e unica para que a troca apareca.
    """
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    j = Judgment(technique="Kernel INT4 fundido",
                 familia="quantizacao",
                 pratica="testar",
                 ganho_eixo="velocidade",
                 ganho_fator=2.3,
                 ganho_texto="2.3x sobre o kernel FP16 do vLLM",
                 resumo="Troca o kernel FP16 por INT4 fundido; custa qualidade.",
                 porque="Roda em infra pequena, mas o ganho depende do modelo.")
    store.record_judgment(P.arxiv_id, j, model="claude-opus-5", judged_at="2026-08-27")
    lido = store.latest_judgment(P.arxiv_id)
    for campo in ("technique", "familia", "pratica", "ganho_eixo",
                  "ganho_fator", "ganho_texto", "resumo", "porque"):
        assert getattr(lido, campo) == getattr(j, campo), campo


def test_stalest_papers_come_first(store):
    for pid, seen in (("2508.00001", "2026-08-01"), ("2508.00002", "2026-08-25")):
        paper = Paper(arxiv_id=pid, title="T", abstract="A", authors=[],
                      categories=["cs.LG"], published="2026-08-01")
        store.upsert_paper(paper, seen_at=seen, scope="teste")
        store.touch_checked(pid, at=seen)
    assert [p["arxiv_id"] for p in store.stalest_papers(limit=2)] == ["2508.00001", "2508.00002"]


def test_stalest_respects_the_limit(store):
    for i in range(5):
        paper = Paper(arxiv_id=f"2508.0000{i}", title="T", abstract="A", authors=[],
                      categories=["cs.LG"], published="2026-08-01")
        store.upsert_paper(paper, seen_at="2026-08-01", scope="teste")
        store.touch_checked(paper.arxiv_id, at="2026-08-01")
    assert len(store.stalest_papers(limit=3)) == 3


def test_init_schema_is_idempotent(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    s.init_schema()
    assert s.all_papers() == []


def test_scope_exclusion_is_known_only_inside_the_rejected_scope(store):
    store.record_scope_exclusion(
        P,
        scope="observatorio",
        excluded_at="2026-09-03",
        reason="julgamento_nao_aplica",
        detail="Requires custom hardware.",
        model="kimi-k3",
    )
    assert P.arxiv_id in store.known_ids("observatorio")
    assert P.arxiv_id not in store.known_ids("agentes")
    assert store.all_papers() == []


def test_init_schema_rejects_the_legacy_judgment_schema_before_the_pipeline(tmp_path):
    import sqlite3

    from radar.store import SchemaMigrationRequired

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE judgments (
        arxiv_id TEXT, judged_at TEXT, model TEXT, technique TEXT,
        summary TEXT, runs_on_3090 TEXT, rationale TEXT
    )""")
    conn.commit()
    conn.close()

    with pytest.raises(SchemaMigrationRequired, match="migrar_e_rejulgar.py"):
        Store(path).init_schema()


def test_papers_to_recheck_returns_paper_objects(store):
    """Quem codificou o JSON e quem decodifica. O pipeline nao deve saber
    que authors e categories viajam serializados."""
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    papers = store.papers_to_recheck(limit=10)
    assert len(papers) == 1
    assert isinstance(papers[0], Paper)
    assert papers[0].arxiv_id == P.arxiv_id


def test_papers_to_recheck_round_trips_sequences_as_tuples(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="teste")
    recuperado = store.papers_to_recheck(limit=10)[0]
    assert recuperado.authors == P.authors
    assert recuperado.categories == P.categories
    assert isinstance(recuperado.authors, tuple)


def test_papers_to_recheck_puts_never_checked_first(store):
    velho = Paper(arxiv_id="2508.00001", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01")
    nunca = Paper(arxiv_id="2508.00002", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01")
    store.upsert_paper(velho, seen_at="2026-08-01", scope="teste")
    store.touch_checked(velho.arxiv_id, at="2026-08-01")
    store.upsert_paper(nunca, seen_at="2026-08-01", scope="teste")
    assert [p.arxiv_id for p in store.papers_to_recheck(limit=10)] == \
        ["2508.00002", "2508.00001"]


def test_papers_to_recheck_respects_the_limit(store):
    for i in range(5):
        store.upsert_paper(
            Paper(arxiv_id=f"2508.0000{i}", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01"),
            seen_at="2026-08-01", scope="teste")
    assert len(store.papers_to_recheck(limit=3)) == 3


def test_papers_to_recheck_can_be_restricted_to_the_active_scope(store):
    store.upsert_paper(P, seen_at="2026-08-27", scope="observatorio")
    other = Paper(arxiv_id="2508.99999", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01")
    store.upsert_paper(other, seen_at="2026-08-27", scope="inferencia")
    assert [p.arxiv_id for p in store.papers_to_recheck(
        limit=10, scope="observatorio"
    )] == [P.arxiv_id]


def test_papers_to_recheck_is_empty_on_a_fresh_database(store):
    assert store.papers_to_recheck(limit=10) == []


def test_papers_to_recheck_returns_nothing_for_a_non_positive_limit(store):
    """`LIMIT -1` no SQLite significa ILIMITADO, nao zero. Sem a guarda,
    `RADAR_RECHECK_LIMIT=-1` -- que e como uma pessoa naturalmente tenta dizer
    "desliga a re-consulta" -- re-consultaria o banco INTEIRO num dia, uma busca
    no GitHub por paper guardado."""
    for i in range(3):
        store.upsert_paper(
            Paper(arxiv_id=f"2508.0000{i}", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01"),
            seen_at="2026-08-01", scope="teste")
    assert store.papers_to_recheck(limit=0) == []
    assert store.papers_to_recheck(limit=-1) == []


# --- Tarefa 6 do plano do segundo escopo ---
# O plano pedia fixtures em tests/conftest.py, que nao existe: este arquivo
# carrega as suas proprias desde o inicio. Segui a convencao do repositorio.

J = Judgment(technique="t", familia="cache_kv", pratica="testar",
             ganho_eixo="velocidade", ganho_fator=2.3,
             ganho_texto="2.3x sobre vLLM", resumo="r", porque="p")

J_SEM_GANHO = Judgment(technique="t", familia="outro", pratica="observar",
                       ganho_eixo="nenhum", ganho_fator=None,
                       ganho_texto="", resumo="r", porque="p")


def test_upsert_exige_escopo_explicito(store):
    # Sem default: um chamador que esquece o escopo tem que quebrar alto, nao
    # gravar linha anonima. A coluna existe para fatiar o acervo.
    with pytest.raises(TypeError):
        store.upsert_paper(P, seen_at="2026-08-29")


def test_o_escopo_gravado_volta_na_leitura(store):
    store.upsert_paper(P, seen_at="2026-08-29", scope="agentes")
    assert store.all_papers()[0]["scope"] == "agentes"


def test_o_julgamento_guarda_familia_pratica_e_ganho(store):
    store.upsert_paper(P, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(P.arxiv_id, J, "claude-opus-5", "2026-08-29")
    lido = store.latest_judgment(P.arxiv_id)
    assert lido.familia == "cache_kv"
    assert lido.pratica == "testar"
    assert lido.ganho_eixo == "velocidade"
    assert lido.ganho_fator == 2.3
    assert lido.ganho_texto == "2.3x sobre vLLM"
    assert lido.resumo == "r"
    assert lido.porque == "p"


def test_ganho_fator_nulo_volta_nulo_e_nao_zero(store):
    store.upsert_paper(P, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(P.arxiv_id, J_SEM_GANHO, "claude-opus-5", "2026-08-29")
    assert store.latest_judgment(P.arxiv_id).ganho_fator is None


def test_citacao_desconhecida_persiste_como_nula(store):
    # O default de Signal.citations e None desde a tarefa 2; o banco precisa
    # aceitar NULL, senao o INSERT quebra na primeira execucao real.
    store.upsert_paper(P, seen_at="2026-08-29", scope="inferencia")
    s = Signal(total_impls=1, independent_impls=1, velocity_14d=0,
               stars_total=0, citations=None)
    store.record_signal(P.arxiv_id, s, score=1.0, checked_at="2026-08-29")
    assert store.signal_history(P.arxiv_id)[0]["citations"] is None


def test_citacao_zero_persiste_como_zero(store):
    store.upsert_paper(P, seen_at="2026-08-29", scope="inferencia")
    s = Signal(total_impls=1, independent_impls=1, velocity_14d=0,
               stars_total=0, citations=0)
    store.record_signal(P.arxiv_id, s, score=1.0, checked_at="2026-08-29")
    assert store.signal_history(P.arxiv_id)[0]["citations"] == 0


def test_papers_por_familia_conta_o_acervo(store):
    store.upsert_paper(P, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(P.arxiv_id, J, "claude-opus-5", "2026-08-29")
    assert store.papers_por_familia() == {"cache_kv": 1}


def test_papers_por_familia_usa_so_o_julgamento_mais_recente(store):
    # Um paper re-julgado nao pode contar duas vezes, nem contar na familia
    # antiga: a contagem e do acervo, nao do historico.
    store.upsert_paper(P, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(P.arxiv_id, J, "claude-opus-5", "2026-08-29")
    store.record_judgment(P.arxiv_id, J_SEM_GANHO, "claude-opus-5", "2026-08-30")
    assert store.papers_por_familia() == {"outro": 1}


def test_o_escopo_do_primeiro_descobridor_sobrevive_ao_upsert(store):
    """Decisao travada da spec: o primeiro escopo a descobrir fica com o paper.

    O pipeline ja filtra por `known_ids()` antes de gravar, entao na pratica o
    segundo escopo nunca chega ao upsert -- mas o store nao pode depender de
    uma invariante do chamador. Verificado por mutacao em 2026-08-30: adicionar
    `scope=excluded.scope` ao ON CONFLICT passava com 237 testes verdes.
    """
    store.upsert_paper(P, seen_at="2026-08-29", scope="inferencia")
    store.upsert_paper(P, seen_at="2026-08-30", scope="agentes")
    assert store.all_papers()[0]["scope"] == "inferencia"
