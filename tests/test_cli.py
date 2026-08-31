"""Testes do ponto de entrada.

Todo adaptador externo entra por injecao ou monkeypatch: nenhuma rede, nenhum
segredo, nenhuma espera de verdade.
"""
import pytest

import radar.cli as cli
from radar.models import Discovery, Judgment, Paper, Signal

PAPER = Paper(arxiv_id="2508.11111", title="Fused INT4 Kernels", abstract="A",
              authors=["A B"], categories=["cs.LG"], published="2026-08-20")
JUDGMENT = Judgment(technique="Kernel INT4", familia="quantizacao",
                    pratica="testar", ganho_eixo="nenhum", ganho_fator=None,
                    ganho_texto="", resumo="S", porque="P")


class FakeArxiv:
    def __init__(self, fetch, sleep=None):
        pass

    def recent(self, scope, max_results=100):
        return Discovery(papers=[PAPER])


class FakeGitHub:
    def __init__(self, fetch):
        pass

    def signal_with_repos(self, paper, today):
        return Signal(total_impls=4, independent_impls=4, velocity_14d=1,
                      stars_total=30), []


class FakeOpenAlex:
    """Sem isto os testes da CLI batem em api.openalex.org de verdade.

    Descoberto na tarefa 10 pela duracao: a suite pulou de 0,6s para 12s
    quando o quarto servico externo entrou sem ser isolado. A restricao
    global do projeto e que nenhum teste toque a rede.
    """
    def __init__(self, fetch):
        pass

    def citations_for(self, ids):
        return {i: None for i in ids}


class FakeAnthropic:
    def __init__(self, *args, **kwargs):
        pass


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """Isola a CLI de rede, de relogio e do ambiente da maquina."""
    monkeypatch.setattr(cli, "ArxivClient", FakeArxiv)
    monkeypatch.setattr(cli, "GitHubClient", FakeGitHub)
    monkeypatch.setattr(cli, "OpenAlexClient", FakeOpenAlex)
    monkeypatch.setattr(cli.anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    monkeypatch.setattr(cli, "submit_batch",
                        lambda client, papers, model: type("B", (), {"id": "b1"})())
    monkeypatch.setattr(cli, "wait_for_batch", lambda client, batch_id: True)
    monkeypatch.setattr(cli, "collect_batch_results",
                        lambda results: {PAPER.arxiv_id: JUDGMENT})
    monkeypatch.setattr(FakeAnthropic, "messages", type("M", (), {
        "batches": type("B", (), {"results": staticmethod(lambda bid: [])})()})(),
        raising=False)
    for chave in ("GH_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                  "RADAR_MODEL", "RADAR_SCORE_FLOOR", "RADAR_LLM_PROVIDER",
                  "KIMI_API_KEY", "RADAR_KIMI_BASE_URL"):
        monkeypatch.delenv(chave, raising=False)
    return tmp_path


def argv(tmp_path, *extra):
    return ["--db", str(tmp_path / "radar.db"), "--out", str(tmp_path / "radar"),
            *extra]


def test_github_interval_matches_the_unauthenticated_limit(monkeypatch):
    """Sem token o GitHub permite 10 req/min. Um intervalo dimensionado para o
    caso COM token faz a maioria dos papers tomar 403 e cair em
    `sinal_indisponivel` -- justamente no cenario que o README documenta como
    suportado, ja que GH_TOKEN e opcional."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert cli.github_sleep_seconds() >= 6.0


def test_github_interval_uses_the_authenticated_budget_when_a_token_exists(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_xxx")
    intervalo = cli.github_sleep_seconds()
    assert 2.0 <= intervalo < 6.0        # dentro dos 30 req/min autenticados


def test_dry_run_neither_sends_nor_records_a_telegram_delivery(ambiente, monkeypatch):
    """O help da CLI promete isso, e o plano prescreve o dry-run como primeiro
    contato com producao. Gravar a entrega ali queima os melhores itens do dia
    para sempre."""
    enviados = []
    monkeypatch.setattr(cli, "send", lambda *a, **k: enviados.append(a) or True)

    assert cli.main(argv(ambiente, "--dry-run")) == 0
    assert enviados == []

    from radar.store import Store
    store = Store(ambiente / "radar.db")
    store.init_schema()
    assert store.was_delivered(PAPER.arxiv_id, channel="telegram") is False


def test_dry_run_leaves_no_durable_state_at_all(ambiente, monkeypatch):
    """Pular so a entrega de telegram nao basta desde que papers ja conhecidos
    deixaram de reentrar como novidade: um paper gravado no ensaio seria
    cortado como `ja_conhecido` na primeira execucao de verdade -- a mesma
    queima, por outra porta. E o passo de commit do workflow nao distingue
    dry-run de execucao real."""
    monkeypatch.setattr(cli, "send", lambda *a, **k: True)
    assert cli.main(argv(ambiente, "--dry-run")) == 0

    from radar.store import Store
    store = Store(ambiente / "radar.db")
    store.init_schema()
    assert store.all_papers() == []
    assert store.signal_history(PAPER.arxiv_id) == []
    assert store.latest_judgment(PAPER.arxiv_id) is None


def test_dry_run_still_reads_the_real_state(ambiente, monkeypatch):
    """A copia e para escrita, nao para leitura: o ensaio precisa enxergar o
    que ja esta no banco, senao mostra como novidade o que nao e."""
    from radar.store import Store
    real = Store(ambiente / "radar.db")
    real.init_schema()
    real.upsert_paper(PAPER, seen_at="2026-08-26", scope="teste")

    monkeypatch.setattr(cli, "send", lambda *a, **k: True)
    assert cli.main(argv(ambiente, "--dry-run")) == 0

    digest = next((ambiente / "radar").glob("*.md")).read_text(encoding="utf-8")
    assert "- ja_conhecido: 1" in digest


def test_a_real_run_sends_and_records(ambiente, monkeypatch):
    """Contraprova do teste acima: sem --dry-run a entrega acontece."""
    enviados = []
    monkeypatch.setattr(cli, "send", lambda *a, **k: enviados.append(a) or True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")

    assert cli.main(argv(ambiente)) == 0
    assert len(enviados) == 1

    from radar.store import Store
    store = Store(ambiente / "radar.db")
    assert store.was_delivered(PAPER.arxiv_id, channel="telegram") is True


def test_a_cli_uses_kimi_when_configured(ambiente, monkeypatch):
    calls = []

    class FakeKimi:
        def __init__(self, api_key, model, request_interval, base_url):
            calls.append((api_key, model, request_interval, base_url))

        def judge_all(self, papers):
            return {paper.arxiv_id: JUDGMENT for paper in papers}

    monkeypatch.setattr(cli, "KimiJudge", FakeKimi)
    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_API_KEY", "secret")
    monkeypatch.setenv("RADAR_KIMI_REQUEST_INTERVAL", "0")
    monkeypatch.setattr(cli, "send", lambda *a, **k: True)

    assert cli.main(argv(ambiente)) == 0
    assert calls == [("secret", "kimi-k3", 0.0,
                      "https://api.moonshot.ai/v1")]


def test_legacy_database_stops_before_any_network_work(ambiente, monkeypatch, capsys):
    import sqlite3

    path = ambiente / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE judgments (
        arxiv_id TEXT, judged_at TEXT, model TEXT, technique TEXT,
        summary TEXT, runs_on_3090 TEXT, rationale TEXT
    )""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(cli, "ArxivClient",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("rede inicializada antes do preflight")))

    assert cli.main(["--db", str(path), "--out", str(ambiente / "out")]) == 2
    output = capsys.readouterr().out
    assert "pipeline bloqueado" in output
    assert "migrar_e_rejulgar.py" in output


def test_a_missing_telegram_secret_does_not_throw_away_the_digest(ambiente, capsys):
    """O markdown ja esta escrito e o lote ja foi pago quando a entrega falha.
    Deixar o ValueError subir matava o processo antes do passo de commit, e os
    dois iam embora com o runner efemero."""
    codigo = cli.main(argv(ambiente))          # sem TELEGRAM_BOT_TOKEN
    assert codigo == 1                         # falha reportada, nao mascarada
    assert "push nao enviado" in capsys.readouterr().out
    digests = list((ambiente / "radar").glob("*.md"))
    assert len(digests) == 1                   # o digest do dia sobreviveu
    assert "## Radar" in digests[0].read_text(encoding="utf-8")
    assert PAPER.arxiv_id in digests[0].read_text(encoding="utf-8")


def test_the_cli_passes_the_configured_recheck_limit(monkeypatch, tmp_path):
    """Sem esta ligacao a re-consulta existe e nunca roda -- exatamente o
    estado em que stalest_papers ficou desde que foi escrita."""
    monkeypatch.setenv("RADAR_RECHECK_LIMIT", "7")
    capturado = {}

    def fake_run_day(**kwargs):
        capturado.update(kwargs)
        raise SystemExit(0)

    monkeypatch.setattr("radar.cli.run_day", fake_run_day)
    monkeypatch.setattr("radar.cli.anthropic", type("A", (), {"Anthropic": lambda: None}))
    with pytest.raises(SystemExit):
        cli.main(["--dry-run", "--db", str(tmp_path / "r.db"), "--out", str(tmp_path)])
    # A PRIMEIRA chamada leva o orcamento; a segunda leva zero (ver
    # `test_a_reconsulta_roda_uma_vez_so`). Este teste captura a primeira,
    # porque `fake_run_day` levanta SystemExit antes da segunda.
    assert capturado["recheck_limit"] == 7


# --- Tarefa 10 do plano do segundo escopo ---

def _espiar_run_day(monkeypatch):
    """Captura os argumentos de cada chamada a run_day, devolvendo um
    DayResult minimo e valido."""
    from radar.pipeline import DayResult
    vistos = []

    def falso(**kw):
        vistos.append(kw)
        nome = kw["scope"].name
        return DayResult(radar=[], feed=[], cuts={},
                         markdown=f"# Radar — x\n\nmarcador-{nome}",
                         push=f"push-{nome}")

    monkeypatch.setattr(cli, "run_day", falso)
    return vistos


def test_a_cli_roda_os_dois_escopos_na_ordem(ambiente, monkeypatch):
    """Inferencia primeiro: decisao travada da spec. O primeiro escopo a
    descobrir um paper fica com ele; o segundo o corta por `ja_conhecido`."""
    vistos = _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente))
    assert [kw["scope"].name for kw in vistos] == ["inferencia", "agentes"]


def test_a_reconsulta_roda_uma_vez_so(ambiente, monkeypatch):
    """Ela varre `papers` inteira e nao conhece escopo. Passar o orcamento nas
    duas passadas re-consultaria o dobro -- os mesmos papers, duas vezes."""
    vistos = _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente))
    limites = [kw["recheck_limit"] for kw in vistos]
    assert limites[0] == cli.load_recheck_limit()
    assert limites[1] == 0


def test_o_arquivo_do_dia_e_um_so(ambiente, monkeypatch):
    _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente))
    arquivos = list((ambiente / "radar").glob("*.md"))
    assert len(arquivos) == 1
    texto = arquivos[0].read_text(encoding="utf-8")
    assert "marcador-inferencia" in texto
    assert "marcador-agentes" in texto


def test_o_push_concatena_os_dois_radares(ambiente, monkeypatch):
    _espiar_run_day(monkeypatch)
    enviados = []
    monkeypatch.setattr(cli, "send",
                        lambda texto, **kw: enviados.append(texto) or True)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    cli.main(argv(ambiente))
    assert "push-inferencia" in enviados[0]
    assert "push-agentes" in enviados[0]


def test_o_buscador_de_citacao_e_ligado_nos_dois_escopos(ambiente, monkeypatch):
    """Sem isso o campo continua desconhecido para sempre e o portao de
    estouro por citacao segue inerte, como esteve desde o dia um."""
    vistos = _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente))
    assert all(kw["fetch_citations"] is not None for kw in vistos)



def test_nenhum_teste_da_cli_toca_a_rede(ambiente, monkeypatch):
    """Guarda contra o defeito da tarefa 10: um servico externo novo ligado na
    CLI sem entrar na fixture `ambiente`.

    Se `httpx.get` for chamado, algum transporte real escapou do isolamento.
    """
    def proibido(*a, **kw):
        raise AssertionError("teste tentou usar a rede de verdade")

    monkeypatch.setattr(cli.httpx, "get", proibido)
    monkeypatch.setattr(cli.httpx, "post", proibido)
    assert cli.main(argv(ambiente, "--dry-run")) == 0


# --- Tarefa 9 do plano do jornal ---

def test_a_execucao_escreve_a_pagina(ambiente, monkeypatch):
    _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente))
    assert (ambiente / "site" / "index.html").exists()


def test_a_execucao_escreve_os_artefatos_de_distribuicao(ambiente, monkeypatch):
    _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente))
    site = ambiente / "site"
    for relativo in ("feed.xml", "about.html", "edicoes/index.html"):
        assert (site / relativo).exists(), relativo


def test_a_pagina_escrita_e_html_completo(ambiente, monkeypatch):
    _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente))
    html = (ambiente / "site" / "index.html").read_text(encoding="utf-8")
    assert html.lstrip().startswith("<!doctype html>")
    assert "</html>" in html


def test_o_ensaio_a_seco_nao_escreve_a_pagina(ambiente, monkeypatch):
    """O dry-run ja nao escreve markdown nem banco; a pagina segue a mesma
    regra. Publicar no Pages a partir de um ensaio seria efeito duravel de
    uma execucao que promete nao ter nenhum."""
    _espiar_run_day(monkeypatch)
    cli.main(argv(ambiente, "--dry-run"))
    assert not (ambiente / "site").exists()
