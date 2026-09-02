import pytest

from radar.models import Paper
from scripts import gerar_relatorio

PAPER = Paper(
    arxiv_id="2608.11111", title="Fast Attention", abstract="A",
    authors=["A"], categories=["cs.LG"], published="2026-08-01",
)


class FakeStore:
    paper = PAPER

    def __init__(self, path):
        self.path = path

    def init_schema(self):
        pass

    def get_paper(self, arxiv_id):
        return self.paper if arxiv_id == PAPER.arxiv_id else None


def _args(tmp_path):
    return [
        "--arxiv-id", PAPER.arxiv_id,
        "--db", str(tmp_path / "radar.db"),
        "--reports-dir", str(tmp_path / "reports"),
        "--site-dir", str(tmp_path / "site"),
    ]


def test_existing_report_is_republished_without_another_paid_call(tmp_path, monkeypatch):
    report = tmp_path / "reports" / f"{PAPER.arxiv_id}.json"
    report.parent.mkdir()
    report.write_text("already generated", encoding="utf-8")
    published = []
    monkeypatch.setattr(gerar_relatorio, "Store", FakeStore)
    monkeypatch.setattr(gerar_relatorio, "publish_site",
                        lambda *a, **k: published.append((a, k)))
    monkeypatch.setattr(gerar_relatorio, "KimiJudge",
                        lambda *a, **k: pytest.fail("Kimi nao deveria ser chamado"))

    assert gerar_relatorio.main(_args(tmp_path)) == 0
    assert len(published) == 1


def test_unknown_paper_stops_before_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(gerar_relatorio, "Store", FakeStore)
    monkeypatch.setattr(gerar_relatorio, "fetch_paper_source",
                        lambda *a, **k: pytest.fail("download nao deveria ocorrer"))
    with pytest.raises(SystemExit, match="nao existe no acervo"):
        gerar_relatorio.main([
            "--arxiv-id", "2608.99999", "--db", str(tmp_path / "radar.db")])


def test_new_report_reads_pdf_saves_json_and_republishes(tmp_path, monkeypatch):
    calls = []

    class FakeJudge:
        def __init__(self, *args, **kwargs):
            calls.append(("judge", args, kwargs))

        def close(self):
            calls.append(("close",))

    class FakeSelector(FakeJudge):
        pass

    source = type("Source", (), {"full_text": "text"})()
    technical_core = object()

    document = object()
    monkeypatch.setattr(gerar_relatorio, "Store", FakeStore)
    monkeypatch.setattr(gerar_relatorio, "load_llm_provider", lambda: "kimi")
    monkeypatch.setattr(gerar_relatorio, "load_model", lambda: "kimi-k3")
    monkeypatch.setattr(gerar_relatorio, "load_formula_model", lambda: "kimi-k2.6")
    monkeypatch.setattr(gerar_relatorio, "load_formula_thinking", lambda: "disabled")
    monkeypatch.setattr(gerar_relatorio, "KimiJudge", FakeJudge)
    monkeypatch.setattr(gerar_relatorio, "KimiFormulaSelector", FakeSelector)
    monkeypatch.setattr(gerar_relatorio, "fetch_paper_source",
                        lambda arxiv_id: calls.append(("source", arxiv_id)) or source)
    monkeypatch.setattr(
        gerar_relatorio, "extract_technical_core",
        lambda *a: calls.append(("core", a)) or technical_core,
    )
    monkeypatch.setattr(gerar_relatorio, "generate_report",
                        lambda *a, **k: calls.append(("generate", a, k)) or document)
    monkeypatch.setattr(gerar_relatorio, "save_report",
                        lambda *a, **k: calls.append(("save", a, k)))
    monkeypatch.setattr(gerar_relatorio, "publish_site",
                        lambda *a, **k: calls.append(("publish", a, k)))

    assert gerar_relatorio.main(_args(tmp_path)) == 0
    assert ("source", PAPER.arxiv_id) in calls
    assert any(call[0] == "generate" for call in calls)
    generate = next(call for call in calls if call[0] == "generate")
    assert generate[2]["technical_core"] is technical_core
    assert any(call[0] == "save" for call in calls)
    assert any(call[0] == "publish" for call in calls)
    assert calls.count(("close",)) == 2
