import pytest
from pydantic import ValidationError

from radar.formulas import TechnicalCore
from radar.public_research import (EXPOSURE_DIMENSIONS, ExposureAssessment,
                                   ResearchClaim, ResearchPage,
                                   build_research_page)
from radar.report import (DeepReport, EvidenceClaim, ReportDocument,
                          SourceProvenance)
from radar.site_data import Ponto


def _paper(**updates) -> Ponto:
    values = dict(
        arxiv_id="2608.11111", titulo="Fast Attention", familia="cache_kv",
        pratica="testar", independent_impls=3, total_impls=4,
        stars_total=10, citations=2, idade_dias=12,
        ganho_eixo="velocidade", ganho_fator=2.3,
        ganho_texto="Reports 2.3x throughput.",
        resumo="Replaces dense attention with selected blocks.",
        publicado="2026-08-01", score=1.2, scope="inferencia",
        technique="Block selection", porque="Test on a local workload.",
    )
    return Ponto(**{**values, **updates})


def _report(*, grounded: bool = True) -> ReportDocument:
    return ReportDocument(
        arxiv_id="2608.11111", title="Fast Attention",
        generated_at="2026-09-03T12:00:00+00:00", provider="kimi",
        model="kimi-k3", source_url="https://arxiv.org/pdf/2608.11111",
        source=SourceProvenance(
            pdf_sha256="a" * 64, extracted_text_sha256="b" * 64,
            extractor="pypdf", pages=12,
        ),
        report=DeepReport(
            one_sentence="Selects attention blocks.", problem="Memory.",
            mechanism="Prunes blocks before the kernel.",
            technical_core=TechnicalCore(
                kind="system", summary="The scheduler selects blocks.",
                walkthroughs=[],
            ),
            evidence=[EvidenceClaim(
                claim="Cuts peak memory", result="2x", baseline="dense",
                conditions="7B model", source_page=7 if grounded else None,
                source_excerpt=(
                    "Peak memory falls by half against dense attention."
                    if grounded else ""
                ),
            )],
            validation_tier="single_gpu_24gb", evidence_tier="multi_gpu",
            infrastructure_basis="explicit",
            software_setup=["custom_cuda_kernel"],
            training_required="inference_only",
            minimum_test=["Compare on one workload", "Measure quality"],
            main_risks=["The custom kernel may be incompatible."],
            unanswered_questions=["Does quality fall on long contexts?"],
        ),
    )


def test_indexed_page_makes_absent_analysis_visible():
    page = build_research_page(_paper(), as_of="2026-09-03")

    assert page.editorial_status == "indexed"
    assert page.report_available is False
    assert tuple(item.dimension for item in page.exposure_map) == EXPOSURE_DIMENSIONS
    assert {item.basis for item in page.exposure_map} == {"not_evaluated"}
    assert page.claims[0].basis == "inferred"


def test_deep_report_promotes_page_to_source_mapped():
    page = build_research_page(
        _paper(), as_of="2026-09-03", report=_report(),
    )

    assert page.editorial_status == "source_mapped"
    assert page.claims[0].basis == "source_linked"
    assert page.claims[0].source_page == 7
    assert page.risks[0].basis == "inferred"
    assert page.minimum_test == (
        "Compare on one workload", "Measure quality",
    )
    assert page.exposure_map[1].dimension == "compute"
    assert "multiple GPUs" in page.exposure_map[1].finding


def test_unlocated_report_claim_stays_an_inference():
    page = build_research_page(
        _paper(), as_of="2026-09-03", report=_report(grounded=False),
    )
    assert page.claims[0].basis == "inferred"


def test_source_linked_claim_requires_a_page_and_excerpt():
    with pytest.raises(ValidationError, match="PDF page"):
        ResearchClaim(
            claim_id="claim-01", statement="A claim",
            basis="source_linked", source_url="https://arxiv.org/pdf/x",
        )


def test_not_evaluated_exposure_cannot_smuggle_in_a_finding():
    with pytest.raises(ValidationError, match="cannot present a finding"):
        ExposureAssessment(
            dimension="security", basis="not_evaluated",
            finding="Probably safe.",
        )


def test_report_must_belong_to_the_same_paper():
    with pytest.raises(ValueError, match="different paper"):
        build_research_page(
            _paper(arxiv_id="2608.22222"), as_of="2026-09-03",
            report=_report(),
        )


def test_independent_status_requires_linked_external_work():
    page = build_research_page(_paper(), as_of="2026-09-03")
    with pytest.raises(ValidationError, match="linked independent work"):
        ResearchPage.model_validate({
            **page.model_dump(),
            "editorial_status": "independently_tested",
        })


def test_source_mapped_status_requires_a_deep_report():
    page = build_research_page(_paper(), as_of="2026-09-03")
    with pytest.raises(ValidationError, match="require a deep report"):
        ResearchPage.model_validate({
            **page.model_dump(),
            "editorial_status": "source_mapped",
        })
