from datetime import date

import pytest

from radar.config import ScopeConfig, Thresholds
from radar.models import Discovery, Judgment, Paper
from radar.pipeline import run_day
from radar.store import Store

SCOPE = ScopeConfig(categories=("cs.LG",), terms=("quantization",))
T = Thresholds(broke_out_stars=1000, broke_out_citations=200, score_floor=0.0)
TODAY = date(2026, 8, 27)


def paper(pid, authors=()):
    return Paper(arxiv_id=pid, title=f"T{pid}", abstract="A",
                 authors=list(authors), categories=["cs.LG"], published="2026-08-20")


def fake_signal(indep, stars, vel=1, cites=0):
    from radar.models import Signal
    return Signal(total_impls=indep, independent_impls=indep,
                  velocity_14d=vel, stars_total=stars, citations=cites)


def judgment(tech="T"):
    return Judgment(technique=tech, summary="S", runs_on_3090="sim", rationale="R")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    return s


def run(store, papers, signals, judgments=None, **kw):
    def judge_all(ps):
        if judgments is not None:
            return judgments
        return {p.arxiv_id: judgment(p.arxiv_id) for p in ps}

    return run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=papers),
        fetch_signal=lambda p, today: (signals[p.arxiv_id], []),
        judge_all=judge_all,
        **kw,
    )


def test_push_is_capped_at_three_even_with_many_candidates(store):
    papers = [paper(f"2508.0000{i}") for i in range(6)]
    signals = {p.arxiv_id: fake_signal(6 - i, 10 + i) for i, p in enumerate(papers)}
    result = run(store, papers, signals)
    assert len(result.radar) == 3


def test_radar_is_ordered_by_score_descending(store):
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(2, 500), "2508.00002": fake_signal(5, 10)}
    result = run(store, papers, signals)
    assert result.radar[0].paper.arxiv_id == "2508.00002"


def test_gated_papers_are_counted_as_cuts_not_delivered(store):
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(50, 9000), "2508.00002": fake_signal(3, 20)}
    result = run(store, papers, signals)
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002"]
    assert result.cuts["ja_estourou"] == 1


def test_every_in_scope_paper_reaches_the_markdown_even_when_gated(store):
    """Nenhum paper novo do escopo desaparece: o cortado do radar continua no
    feed. Radar e feed sao secoes distintas do mesmo markdown, e a uniao delas
    e que precisa cobrir o dia."""
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(50, 9000), "2508.00002": fake_signal(3, 20)}
    result = run(store, papers, signals)
    assert [i.paper.arxiv_id for i in result.feed] == ["2508.00001"]
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002"]


def test_radar_items_are_not_repeated_in_the_feed(store):
    """Spec secao 7: o markdown e (1) os tres do radar e (2) todos os DEMAIS
    candidatos. Os mesmos itens nas duas secoes fazem o dia parecer maior do
    que foi e obrigam a ler duas vezes."""
    papers = [paper(f"2508.0000{i}") for i in range(5)]
    signals = {p.arxiv_id: fake_signal(5 - i, 10) for i, p in enumerate(papers)}
    result = run(store, papers, signals)
    no_radar = [i.paper.arxiv_id for i in result.radar]
    no_feed = [i.paper.arxiv_id for i in result.feed]
    assert no_radar == ["2508.00000", "2508.00001", "2508.00002"]
    assert no_feed == ["2508.00003", "2508.00004"]
    assert set(no_radar).isdisjoint(no_feed)


def test_radar_items_are_not_repeated_in_the_rendered_markdown(store):
    """A mesma garantia onde ela e visivel: a linha de feed de um item do radar
    nao pode aparecer no arquivo do dia."""
    papers = [paper(f"2508.0000{i}") for i in range(4)]
    signals = {p.arxiv_id: fake_signal(4 - i, 10) for i, p in enumerate(papers)}
    result = run(store, papers, signals)
    corpo = result.markdown[result.markdown.index("## Feed"):]
    for no_radar in ("2508.00000", "2508.00001", "2508.00002"):
        assert no_radar not in corpo
    assert "2508.00003" in corpo


def test_dry_run_does_not_burn_the_days_best_items(store):
    """dry_run existe para ensaiar o dia. Gravar entrega de telegram nele
    queima os tres melhores papers para sempre: a primeira execucao de verdade
    os corta como ja_entregue, em silencio."""
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {p.arxiv_id: fake_signal(4, 20) for p in papers}
    result = run(store, papers, signals, dry_run=True)
    assert len(result.radar) == 2                       # a selecao acontece
    assert result.push != ""                            # o push e montado
    for pid in ("2508.00001", "2508.00002"):
        assert store.was_delivered(pid, channel="telegram") is False


def test_dry_run_still_writes_the_paper_so_the_cli_must_isolate_the_database(store):
    """Documenta por que a CLI aponta o ensaio para uma copia do banco.

    `dry_run` pula a entrega de telegram, mas NAO impede `run_day` de gravar o
    paper em `papers`. Como papers ja conhecidos deixaram de reentrar como
    novidade, um paper gravado durante o ensaio e cortado como `ja_conhecido`
    na execucao seguinte -- que entao nao entrega nada.

    Ou seja: a garantia "o ensaio nao rouba o dia seguinte" NAO existe nesta
    camada. Quem a fornece e a CLI, apontando o ensaio para uma copia
    descartavel (ver tests/test_cli.py). Este teste existe para falhar se
    alguem passar a acreditar que `run_day` sozinho ja protege, e remover a
    copia por acha-la redundante.
    """
    p = paper("2508.00001")
    ensaio = run(store, [p], {"2508.00001": fake_signal(4, 20)}, dry_run=True)
    assert [i.paper.arxiv_id for i in ensaio.radar] == ["2508.00001"]
    assert store.was_delivered("2508.00001", channel="telegram") is False
    assert len(store.all_papers()) == 1          # o ensaio GRAVOU

    real = run(store, [p], {"2508.00001": fake_signal(4, 20)})
    assert real.radar == []                      # e por isso o dia seguinte
    assert real.cuts["ja_conhecido"] == 1        # perde o paper
    assert real.push == ""


def test_discovery_cuts_are_carried_into_the_days_accounting(store):
    """O que o cliente do arXiv descarta tem de chegar a secao de cortes:
    contagem dentro do adaptador que ninguem le e truncamento silencioso."""
    p = paper("2508.00001")
    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(
            papers=[p], cuts={"fora_de_escopo": 7, "termo_falhou": 2}),
        fetch_signal=lambda pp, today: (fake_signal(4, 30), []),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
    )
    assert result.cuts["fora_de_escopo"] == 7
    assert result.cuts["termo_falhou"] == 2
    assert "- fora_de_escopo: 7" in result.markdown
    assert "- termo_falhou: 2" in result.markdown


def test_already_delivered_paper_is_not_pushed_twice(store):
    """A garantia de produto e "nenhum paper vai duas vezes para o Telegram".
    Quem a entrega hoje e o filtro de ja-conhecido: entregar exige estar no
    banco, e quem esta no banco nao reentra como novidade."""
    p = paper("2508.00001")
    store.upsert_paper(p, seen_at="2026-08-26")
    store.mark_delivered(p.arxiv_id, channel="telegram", at="2026-08-26", rank=1)
    result = run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert result.radar == []


def test_paper_already_in_the_database_is_not_rediscovered_as_news(store):
    """Spec secao 3: papers ja no banco nao reentram como novidade. O Feed
    responde "o que saiu hoje" -- um paper de ontem nao saiu hoje, entao fica
    fora do radar E do feed, contado na secao de cortes."""
    velho, novo = paper("2508.00001"), paper("2508.00002")
    store.upsert_paper(velho, seen_at="2026-08-26")
    result = run(store, [velho, novo],
                 {"2508.00001": fake_signal(4, 30), "2508.00002": fake_signal(3, 20)})
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002"]
    assert "2508.00001" not in [i.paper.arxiv_id for i in result.feed]
    assert result.cuts["ja_conhecido"] == 1


def test_a_known_paper_is_never_sent_to_the_judge(store):
    """O corte precisa acontecer ANTES do julgamento: e o custo do lote que
    estoura quando o dia 2 re-julga tudo que o dia 1 ja julgou."""
    velho, novo = paper("2508.00001"), paper("2508.00002")
    store.upsert_paper(velho, seen_at="2026-08-26")
    julgados: list[list[str]] = []

    def judge_all(ps):
        julgados.append([p.arxiv_id for p in ps])
        return {p.arxiv_id: judgment(p.arxiv_id) for p in ps}

    run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=[velho, novo]),
        fetch_signal=lambda p, today: (fake_signal(3, 20), []),
        judge_all=judge_all,
    )
    assert julgados == [["2508.00002"]]


def test_a_day_whose_papers_are_all_known_judges_nothing(store):
    velho = paper("2508.00001")
    store.upsert_paper(velho, seen_at="2026-08-26")
    chamadas = []

    def judge_all(ps):
        chamadas.append(ps)
        return {}

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=[velho]),
        fetch_signal=lambda p, today: (fake_signal(3, 20), []),
        judge_all=judge_all,
    )
    assert chamadas == []                      # nem uma chamada ao LLM
    assert result.cuts["ja_conhecido"] == 1
    assert result.push == ""


def test_pushed_papers_are_marked_delivered(store):
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert store.was_delivered("2508.00001", channel="telegram") is True


def test_score_below_the_floor_is_cut(store):
    strict = Thresholds(broke_out_stars=1000, broke_out_citations=200, score_floor=0.9)
    p = paper("2508.00001")
    result = run_day(
        store=store, scope=SCOPE, thresholds=strict, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=[p]),
        fetch_signal=lambda pp, today: (fake_signal(1, 500), []),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
    )
    assert result.radar == []
    assert result.cuts["abaixo_do_piso"] == 1


def test_a_paper_with_no_independent_implementation_never_takes_a_push_slot(store):
    """O piso e o ultimo valor rejeitado, nao o primeiro aceito. Com o piso em
    0.0, score exatamente 0.0 e o paper que NINGUEM de fora implementou -- e a
    tese do produto e que implementacao independente E o sinal. Num dia magro
    ele tomaria uma das tres vagas so por nao ter concorrente."""
    p = paper("2508.00001")
    result = run(store, [p], {"2508.00001": fake_signal(0, 800)})
    assert result.radar == []
    assert result.push == ""                   # silencio e resultado valido
    assert result.cuts["abaixo_do_piso"] == 1
    assert [i.paper.arxiv_id for i in result.feed] == ["2508.00001"]


def test_a_paper_just_above_the_floor_still_passes(store):
    """Contraprova: `<=` nao pode virar um corte generico. Uma unica
    implementacao independente ja poe o score acima de zero."""
    p = paper("2508.00001")
    result = run(store, [p], {"2508.00001": fake_signal(1, 800)})
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00001"]


def test_judgment_records_which_model_produced_it(store):
    """A coluna `model` existe para auditoria. Gravar vazio a torna inutil."""
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(4, 30)})
    row = store._conn.execute(
        "SELECT model FROM judgments WHERE arxiv_id=?", ("2508.00001",)).fetchone()
    assert row["model"] == "modelo-de-teste"


def test_signal_is_persisted_for_every_paper(store):
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert len(store.signal_history("2508.00001")) == 1


def test_rediscovering_a_paper_does_not_add_a_second_observation(store):
    """Consequencia deliberada do filtro de ja-conhecido, registrada aqui para
    nao virar surpresa: quem ja esta no banco nao passa mais pelo laco, entao a
    redescoberta pelo arXiv NAO grava um segundo sinal e nao produz delta.

    O delta (spec secao 4, ressurreicao) volta a ter fonte quando a re-consulta
    da spec secao 6 for construida -- ela e que vai reobservar o sinal dos
    papers antigos. Ate la o `signals` de um paper tem uma linha so, e este
    teste falha no dia em que isso mudar, que e exatamente quando ele deve ser
    reescrito."""
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(2, 300)})
    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=date(2026, 9, 17), model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=[p]),
        fetch_signal=lambda pp, today: (fake_signal(9, 340, vel=7), []),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
    )
    assert len(store.signal_history("2508.00001")) == 1
    assert store.signal_delta("2508.00001") is None
    assert result.cuts["ja_conhecido"] == 1


def test_markdown_and_push_are_both_produced(store):
    p = paper("2508.00001")
    result = run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert "## Radar" in result.markdown
    assert "## Cortes" in result.markdown
    assert "arxiv.org/abs/2508.00001" in result.push


def test_empty_day_produces_markdown_but_empty_push(store):
    result = run(store, [], {})
    assert result.push == ""
    assert "## Cortes" in result.markdown


def test_non_executable_is_demoted_below_executable_with_lower_score(store):
    """Paper de FP8 nao roda em Ampere. Mesmo com score maior, entra depois."""
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(9, 10),    # score ALTO, mas nao roda
               "2508.00002": fake_signal(2, 40)}    # score menor, roda
    result = run(store, papers, signals, judgments={
        "2508.00001": Judgment("FP8", "S", "nao", "R"),
        "2508.00002": Judgment("INT4", "S", "sim", "R"),
    })
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002", "2508.00001"]


def test_non_executable_is_dropped_when_executables_fill_the_cap(store):
    papers = [paper(f"2508.0000{i}") for i in range(4)]
    signals = {p.arxiv_id: fake_signal(4, 20) for p in papers}
    judgments = {p.arxiv_id: Judgment("T", "S", "sim", "R") for p in papers[:3]}
    judgments["2508.00003"] = Judgment("FP8", "S", "nao", "R")
    result = run(store, papers, signals, judgments=judgments)
    assert len(result.radar) == 3
    assert "2508.00003" not in [i.paper.arxiv_id for i in result.radar]


def test_non_executable_still_enters_when_a_slot_remains(store):
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {p.arxiv_id: fake_signal(3, 20) for p in papers}
    result = run(store, papers, signals, judgments={
        "2508.00001": Judgment("T", "S", "sim", "R"),
        "2508.00002": Judgment("FP8", "S", "nao", "R"),
    })
    assert len(result.radar) == 2


def test_sim_com_ressalva_ranks_as_executable(store):
    """Ressalva nao e recusa: continua na frente do que nao roda."""
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(9, 10),    # score maior, nao roda
               "2508.00002": fake_signal(2, 40)}    # score menor, com ressalva
    result = run(store, papers, signals, judgments={
        "2508.00001": Judgment("FP8", "S", "nao", "R"),
        "2508.00002": Judgment("INT4", "S", "sim_com_ressalva", "R"),
    })
    assert result.radar[0].paper.arxiv_id == "2508.00002"


def test_non_executable_always_reaches_the_feed(store):
    """Rebaixar afeta o push, nunca o arquivo."""
    papers = [paper(f"2508.0000{i}") for i in range(4)]
    signals = {p.arxiv_id: fake_signal(4, 20) for p in papers}
    judgments = {p.arxiv_id: Judgment("T", "S", "sim", "R") for p in papers[:3]}
    judgments["2508.00003"] = Judgment("FP8", "S", "nao", "R")
    result = run(store, papers, signals, judgments=judgments)
    assert "2508.00003" in [i.paper.arxiv_id for i in result.feed]


def test_paper_whose_signal_fails_is_cut_not_fatal(store):
    """Uma busca do GitHub que falha num paper nao pode derrubar o digest do
    dia. O paper vira corte contado e volta na re-consulta de amanha."""
    papers = [paper("2508.00001"), paper("2508.00002")]

    def fetch_signal(p, today):
        if p.arxiv_id == "2508.00001":
            raise RuntimeError("busca incompleta segundo o proprio GitHub")
        return fake_signal(3, 20), []

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=papers),
        fetch_signal=fetch_signal,
        judge_all=lambda ps: {p.arxiv_id: judgment() for p in ps},
    )
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002"]
    assert result.cuts["sinal_indisponivel"] == 1


def test_a_failing_signal_does_not_reach_the_feed_either(store):
    """Sem sinal nao ha o que reportar: o paper e corte, nao item de feed."""
    papers = [paper("2508.00001")]

    def fetch_signal(p, today):
        raise RuntimeError("rate limit")

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=papers),
        fetch_signal=fetch_signal,
        judge_all=lambda ps: {p.arxiv_id: judgment() for p in ps},
    )
    assert result.feed == []
    assert result.cuts["sinal_indisponivel"] == 1


def test_markdown_carries_the_authorship_audit_trail_from_the_store(store):
    """Trava o contrato implicito entre store e render.

    As colunas do banco (`is_author_reason`) precisam casar com as chaves que
    `render_markdown` le. Os testes das Tarefas 6 e 8 asseguram cada metade
    usando literais proprios, e nenhum dos dois garante que as metades
    concordam: renomear a coluna deixaria os dois verdes enquanto a trilha de
    auditoria sumia do markdown em silencio. Este teste passa dado real do
    store para o render e falha se qualquer um dos lados mudar de nome.
    """
    from radar.models import Repo, RepoClassification

    p = paper("2508.00001")
    classificacoes = [
        RepoClassification(Repo("lab/oficial", "lab", 900, "2024-01-01T00:00:00Z"),
                           is_author=True, reason="mais_antigo_e_mais_estrelado"),
        RepoClassification(Repo("terceiro/impl", "terceiro", 12, "2024-06-01T00:00:00Z"),
                           is_author=False, reason=None),
    ]
    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=[p]),
        fetch_signal=lambda pp, today: (fake_signal(4, 30), classificacoes),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
    )
    assert "lab/oficial — 900 estrelas — autor (mais_antigo_e_mais_estrelado)" in result.markdown
    assert "terceiro/impl — 12 estrelas — independente" in result.markdown


# Motivos que REMOVEM o paper do dia. Os demais (ja_estourou, abaixo_do_piso,
# ja_entregue) tiram do push mas mantem o paper no feed, entao entrariam duas
# vezes na conta abaixo.
REMOCOES = ("ja_conhecido", "sem_julgamento", "sinal_indisponivel")


def test_every_discovered_paper_is_either_rendered_or_counted_as_a_cut(store):
    """A particao exata, nao uma desigualdade. `radar + cortes <= descobertos`
    e verdade ate quando um paper some sem deixar rastro -- que e exatamente o
    truncamento silencioso que a restricao global proibe. Aqui todo paper
    descoberto tem de aparecer no radar, no feed ou numa contagem de remocao,
    uma vez so."""
    conhecido = paper("2508.00000")
    store.upsert_paper(conhecido, seen_at="2026-08-26")
    papers = [conhecido] + [paper(f"2508.0000{i}") for i in range(1, 7)]
    signals = {
        "2508.00001": fake_signal(6, 20),      # radar
        "2508.00002": fake_signal(5, 20),      # radar
        "2508.00003": fake_signal(4, 20),      # radar
        "2508.00004": fake_signal(3, 20),      # sobra do teto -> feed
        "2508.00005": fake_signal(50, 9000),   # portao -> feed
        # 2508.00006 falha no sinal; 2508.00000 ja e conhecido
    }

    def fetch_signal(p, today):
        if p.arxiv_id == "2508.00006":
            raise RuntimeError("busca incompleta")
        return signals[p.arxiv_id], []

    def judge_all(ps):
        # o 2508.00002 volta sem julgamento do lote
        return {p.arxiv_id: judgment(p.arxiv_id)
                for p in ps if p.arxiv_id != "2508.00002"}

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: Discovery(papers=papers),
        fetch_signal=fetch_signal, judge_all=judge_all,
    )

    removidos = sum(result.cuts.get(motivo, 0) for motivo in REMOCOES)
    assert result.cuts["ja_conhecido"] == 1
    assert result.cuts["sem_julgamento"] == 1
    assert result.cuts["sinal_indisponivel"] == 1
    assert len(result.radar) + len(result.feed) + removidos == len(papers)
    # E cada paper aparece uma vez so entre as duas secoes.
    rendidos = [i.paper.arxiv_id for i in result.radar + result.feed]
    assert len(rendidos) == len(set(rendidos))


def test_a_rechecked_paper_can_reach_the_radar_with_delta_wording(store):
    """O caso que a feature existe para pegar: paper guardado, nunca entregue
    porque o sinal era fraco, volta quando o sinal cresce."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 300), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment("GPTQ"), model="m", judged_at="2026-08-01")

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 340, vel=7), []),
        judge_all=lambda ps: {},
        recheck_limit=10,
    )
    assert [i.paper.arxiv_id for i in result.radar] == ["2210.17323"]
    assert result.radar[0].delta is not None
    assert "2 -> 9 impls independentes" in result.push


def test_a_rechecked_paper_never_reaches_the_feed(store):
    """O feed responde 'o que saiu hoje'. Um paper de 2022 nao saiu hoje."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 300), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    store.mark_delivered(p.arxiv_id, channel="telegram", at="2026-08-01", rank=1)

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 340), []),
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.feed == []
    assert result.cuts["ja_entregue"] == 1


def test_an_already_delivered_paper_never_comes_back(store):
    """Spec secao 6, sem excecao: nenhum paper e entregue duas vezes."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 300), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    store.mark_delivered(p.arxiv_id, channel="telegram", at="2026-08-01", rank=1)

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(99, 10), []),   # sinal enorme
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.radar == []
    assert result.push == ""


def test_recheck_reuses_the_stored_judgment_and_never_calls_the_llm(store):
    """Re-consulta nao gasta token. Re-julgar trinta papers por dia
    multiplicaria a conta para produzir texto que ja esta no banco."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 30), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment("Tecnica Guardada"), model="m",
                          judged_at="2026-08-01")

    julgados = []
    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 40), []),
        judge_all=lambda ps: julgados.extend(ps) or {}, recheck_limit=10,
    )
    assert julgados == []                                   # o LLM nao foi chamado
    assert result.radar[0].judgment.technique == "Tecnica Guardada"


def test_a_rechecked_paper_without_a_stored_judgment_is_cut_distinctly(store):
    """Motivo distinto do `sem_julgamento` dos novos: la o LLM falhou, aqui e
    linha antiga sem julgamento. Causas e consertos diferentes."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")     # sem record_judgment

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 40), []),
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.cuts["reconsulta_sem_julgamento"] == 1
    assert "sem_julgamento" not in result.cuts


def test_recheck_respects_the_limit(store):
    for i in range(5):
        pp = paper(f"2508.0000{i}")
        store.upsert_paper(pp, seen_at="2026-08-01")
        store.record_judgment(pp.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    vistos = []
    run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (vistos.append(pp.arxiv_id) or (fake_signal(1, 5), [])),
        judge_all=lambda ps: {}, recheck_limit=2,
    )
    assert len(vistos) == 2


def test_a_paper_discovered_today_has_its_signal_fetched_exactly_once(store):
    """A propriedade e verdadeira, mas NAO pela razao que parece.

    Nao e a guarda de de-duplicacao que a garante: `known_ids()` ja removeu de
    `papers` tudo que esta no banco, e `papers_to_recheck` le exatamente o
    banco, entao os dois conjuntos sao disjuntos antes de a guarda ser
    consultada. Verificado por mutacao -- este teste passa com a guarda
    deletada.

    Ele fica porque a propriedade importa por si (buscar o sinal duas vezes
    gastaria rate limit e gravaria `record_signal` em dobro) e porque quebraria
    se alguem invertesse a ordem entre a consulta de re-consulta e o
    `upsert_paper`. O que ele NAO faz e exercitar a guarda; o nome antigo
    prometia isso e mentia.
    """
    p = paper("2508.00001")
    vistos = []
    run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[p], cuts={}),
        fetch_signal=lambda pp, t: (vistos.append(pp.arxiv_id) or (fake_signal(4, 20), [])),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
        recheck_limit=10,
    )
    assert vistos == ["2508.00001"]


def test_recheck_advances_the_rotation_even_when_the_signal_fails(store):
    """Sem touch_checked na falha, `stalest_papers` devolveria os mesmos
    papers para sempre e a rotacao nunca chegaria aos demais."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (_ for _ in ()).throw(RuntimeError("GitHub fora")),
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.cuts["sinal_indisponivel"] == 1
    assert store.all_papers()[0]["last_checked"] == TODAY.isoformat()


def test_recheck_is_off_by_default(store):
    """recheck_limit=0 por default: os chamadores existentes nao ganham
    re-consulta sem pedir."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    vistos = []
    run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (vistos.append(pp.arxiv_id) or (fake_signal(1, 5), [])),
        judge_all=lambda ps: {},
    )
    assert vistos == []
