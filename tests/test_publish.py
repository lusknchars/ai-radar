from datetime import date

from radar.formulas import TechnicalCore
from radar.models import Judgment, Paper, Signal
from radar.publish import publish_site
from radar.report import DeepReport, ReportDocument, save_report
from radar.store import Store


def _document() -> ReportDocument:
    return ReportDocument(
        arxiv_id="2608.11111", title="Fast Attention",
        generated_at="2026-08-31T18:00:00+00:00", provider="kimi",
        model="kimi-k3", source_url="https://arxiv.org/pdf/2608.11111",
        source_sha256="a" * 64,
        report=DeepReport(
            one_sentence="Troca atenção densa por blocos.", problem="Memória.",
            mechanism="Seleciona blocos.",
            technical_core=TechnicalCore(
                kind="system", summary="Seleciona blocos antes do kernel.",
                walkthroughs=[]),
            evidence=[],
            validation_tier="single_gpu_24gb", evidence_tier="multi_gpu",
            infrastructure_basis="explicit", software_setup=["standard_python"],
            training_required="inference_only", minimum_test=["Compare latência"],
            main_risks=["Perda de qualidade"], unanswered_questions=[],
        ),
    )


def _store(path) -> Store:
    store = Store(path)
    store.init_schema()
    paper = Paper(
        arxiv_id="2608.11111", title="Fast Attention", abstract="A",
        authors=["A"], categories=["cs.LG"], published="2026-08-01",
    )
    store.upsert_paper(paper, seen_at="2026-08-30", scope="inferencia")
    store.record_judgment(
        paper.arxiv_id,
        Judgment(
            technique="Blocks", familia="kernels_e_atencao", pratica="testar",
            ganho_eixo="nenhum", ganho_fator=None, ganho_texto="",
            resumo="Seleciona blocos antes da atenção.", porque="Teste local.",
        ),
        model="kimi-k3", judged_at="2026-08-30",
    )
    store.record_signal(
        paper.arxiv_id,
        Signal(total_impls=2, independent_impls=2, velocity_14d=1,
               stars_total=5, citations=1),
        score=1.0, checked_at="2026-08-30",
    )
    return store


def test_publish_site_links_and_renders_saved_reports(tmp_path):
    store = _store(tmp_path / "data" / "radar.db")
    reports = tmp_path / "reports"
    save_report(_document(), reports)

    publish_site(
        store, tmp_path / "site", date(2026, 8, 31), reports_root=reports)

    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    page = (tmp_path / "site" / "reports" / "2608.11111" / "index.html")
    assert '/ai-radar/reports/2608.11111/' in index
    assert "Read deep report" in index
    assert page.exists()
    assert "1 GPU, up to 24 GB" in page.read_text(encoding="utf-8")
    plot_asset = tmp_path / "site" / "assets" / "observable-plot-0.6.17.min.js"
    d3_asset = tmp_path / "site" / "assets" / "d3-7.9.0.min.js"
    assert plot_asset.exists()
    assert plot_asset.stat().st_size == 209_183
    assert d3_asset.exists()
    assert d3_asset.stat().st_size == 279_706
