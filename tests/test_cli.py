"""Testes do ponto de entrada.

Todo adaptador externo entra por injecao ou monkeypatch: nenhuma rede, nenhum
segredo, nenhuma espera de verdade.
"""
import pytest

import radar.cli as cli
from radar.models import Discovery, Judgment, Paper, Signal

PAPER = Paper(arxiv_id="2508.11111", title="Fused INT4 Kernels", abstract="A",
              authors=["A B"], categories=["cs.LG"], published="2026-08-20")
JUDGMENT = Judgment(technique="Kernel INT4", summary="S", runs_on_3090="sim",
                    rationale="R")


class FakeArxiv:
    def __init__(self, fetch, sleep=None):
        pass

    def recent(self, scope, max_results=100):
        return Discovery(papers=[PAPER])


class FakeGitHub:
    def __init__(self, fetch):
        pass

    def signal_with_repos(self, paper, today, citations=0):
        return Signal(total_impls=4, independent_impls=4, velocity_14d=1,
                      stars_total=30), []


class FakeAnthropic:
    def __init__(self, *args, **kwargs):
        pass


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """Isola a CLI de rede, de relogio e do ambiente da maquina."""
    monkeypatch.setattr(cli, "ArxivClient", FakeArxiv)
    monkeypatch.setattr(cli, "GitHubClient", FakeGitHub)
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
                  "RADAR_MODEL", "RADAR_SCORE_FLOOR"):
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
    real.upsert_paper(PAPER, seen_at="2026-08-26")

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
