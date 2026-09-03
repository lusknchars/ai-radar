import json

import pytest

from radar.models import Paper
from scripts import gerar_relatorio

PAPER = Paper(
    arxiv_id="2608.11111", title="Fast Attention", abstract="A",
    authors=["A"], categories=["cs.LG"], published="2026-08-01",
)
PAPER_2 = Paper(
    arxiv_id="2608.22222", title="Agent Memory", abstract="B",
    authors=["B"], categories=["cs.AI"], published="2026-08-02",
)


class FakeStore:
    paper = PAPER

    def __init__(self, path):
        self.path = path

    def init_schema(self):
        pass

    def get_paper(self, arxiv_id):
        return {
            PAPER.arxiv_id: self.paper,
            PAPER_2.arxiv_id: PAPER_2,
        }.get(arxiv_id)


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


def test_existing_manifest_reports_are_republished_in_one_pass(
    tmp_path, monkeypatch,
):
    manifest = tmp_path / "corpus.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "minimum_reports": 2,
        "required_tracks": ["inference", "agents"],
        "cases": [
            {
                "arxiv_id": PAPER.arxiv_id,
                "track": "inference",
                "expected_family": "cache_kv",
                "expected_recommendation": "testar",
            },
            {
                "arxiv_id": PAPER_2.arxiv_id,
                "track": "agents",
                "expected_family": "memoria_e_contexto",
                "expected_recommendation": "testar",
            },
        ],
    }), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    for paper in (PAPER, PAPER_2):
        reports.joinpath(f"{paper.arxiv_id}.json").write_text(
            "already generated", encoding="utf-8",
        )
    published = []
    monkeypatch.setattr(gerar_relatorio, "Store", FakeStore)
    monkeypatch.setattr(
        gerar_relatorio, "publish_site",
        lambda *a, **k: published.append((a, k)),
    )
    monkeypatch.setattr(
        gerar_relatorio, "KimiJudge",
        lambda *a, **k: pytest.fail("Kimi nao deveria ser chamado"),
    )

    assert gerar_relatorio.main([
        "--manifest", str(manifest),
        "--db", str(tmp_path / "radar.db"),
        "--reports-dir", str(reports),
        "--site-dir", str(tmp_path / "site"),
    ]) == 0
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

    source = type("Source", (), {
        "full_text": "text",
        "pdf_sha256": "a" * 64,
        "pdf_extraction_method": "docling",
        "pdf_fallback_from": None,
        "pdf_fallback_reason": None,
        "pdf_pages": ("text",),
    })()
    technical_core = object()

    document = object()
    monkeypatch.setattr(gerar_relatorio, "Store", FakeStore)
    monkeypatch.setattr(gerar_relatorio, "load_llm_provider", lambda: "kimi")
    monkeypatch.setattr(gerar_relatorio, "load_model", lambda: "kimi-k3")
    monkeypatch.setattr(gerar_relatorio, "load_formula_model", lambda: "kimi-k2.6")
    monkeypatch.setattr(gerar_relatorio, "load_formula_thinking", lambda: "disabled")
    monkeypatch.setattr(gerar_relatorio, "load_pdf_extractor", lambda: "docling")
    monkeypatch.setattr(gerar_relatorio, "build_pdf_extractor", lambda name: name)
    monkeypatch.setattr(gerar_relatorio, "KimiJudge", FakeJudge)
    monkeypatch.setattr(gerar_relatorio, "KimiFormulaSelector", FakeSelector)
    monkeypatch.setattr(
        gerar_relatorio, "fetch_paper_source",
        lambda arxiv_id, **kwargs: calls.append(
            ("source", arxiv_id, kwargs)) or source,
    )
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
    source_call = next(call for call in calls if call[0] == "source")
    assert source_call[1] == PAPER.arxiv_id
    assert source_call[2]["extractor"] == "docling"
    assert any(call[0] == "generate" for call in calls)
    generate = next(call for call in calls if call[0] == "generate")
    assert generate[2]["technical_core"] is technical_core
    provenance = generate[2]["source_provenance"]
    assert provenance.pdf_sha256 == "a" * 64
    assert provenance.extractor == "docling"
    assert any(call[0] == "save" for call in calls)
    assert any(call[0] == "publish" for call in calls)
    assert calls.count(("close",)) == 2
