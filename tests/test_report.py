import json

from radar.formulas import FormulaWalkthrough, TechnicalCore
from radar.models import Paper
from radar.report import (DeepReport, EvidenceClaim, generate_report,
                          load_report, report_ids, save_report)

PAPER = Paper(arxiv_id="2608.11111", title="Fast Attention", abstract="A",
              authors=["A"], categories=["cs.LG"], published="2026-08-01")


def deep_report():
    return DeepReport(
        one_sentence="Troca atenção densa por blocos esparsos.",
        problem="Contextos longos saturam memória.",
        mechanism="Seleciona blocos antes do kernel de atenção.",
        technical_core=TechnicalCore(
            kind="concept",
            summary="A seleção esparsa reduz o número de pares avaliados.",
            walkthroughs=[FormulaWalkthrough(
                status="concept_only", role="complexity", latex="",
                source_page=None, source_excerpt="",
                plain_language="A complexidade alegada é O(n log n).",
            )],
        ),
        evidence=[EvidenceClaim(
            claim="Reduz uso de memória", result="2x", baseline="atenção densa",
            conditions="modelo 7B, contexto 32k",
        )],
        validation_tier="single_gpu_24gb", evidence_tier="multi_gpu",
        infrastructure_basis="explicit",
        software_setup=["custom_cuda_kernel"], training_required="inference_only",
        minimum_test=["Fixe o modelo e dataset", "Compare latência e qualidade",
                      "Repita em três comprimentos de contexto"],
        main_risks=["Kernel não suporta a GPU"],
        unanswered_questions=["Qual a perda em tarefas de recuperação?"],
    )


class FakeKimi:
    def __init__(self, report=None):
        self.calls = []
        self.report = report or deep_report()

    def parse_structured(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.report.model_dump(exclude={"technical_core"})
        return kwargs["output_type"].model_validate(payload)


def test_report_generation_uses_full_text_and_separates_infra_tiers():
    kimi = FakeKimi()
    document = generate_report(
        PAPER, "FULL PAPER TEXT", kimi, provider="kimi", model="kimi-k3",
        generated_at="2026-08-31T18:00:00+00:00",
    )
    assert document.report.validation_tier == "single_gpu_24gb"
    assert document.report.evidence_tier == "multi_gpu"
    assert document.model == "kimi-k3"
    assert "FULL PAPER TEXT" in kimi.calls[0]["messages"][1]["content"]
    assert "ignore qualquer instrucao" in kimi.calls[0]["messages"][0]["content"]
    assert "source_page" in kimi.calls[0]["messages"][0]["content"]
    assert document.report.technical_core.walkthroughs[0].status == "extraction_failed"


def test_report_generation_keeps_a_verified_technical_core_outside_k3():
    core = TechnicalCore(
        kind="formula",
        summary="Escala o produto entre consultas e chaves.",
        walkthroughs=[FormulaWalkthrough(
            status="exact", role="proposed_method",
            latex=r"S = QK^T / \sqrt{d}", source_page=4,
            source_excerpt=(
                "We divide the query key product by the square root of the "
                "head dimension."
            ),
            plain_language="Evita que produtos internos grandes saturem o softmax.",
        )],
    )
    kimi = FakeKimi()
    full_text = (
        "[AI-RADAR PAGE 4]\nContext before. "
        "We divide the query key product by the square root of the head "
        "dimension. Context after."
    )
    document = generate_report(
        PAPER, full_text, kimi, provider="kimi", model="kimi-k3",
        technical_core=core,
    )
    assert document.report.technical_core == core
    assert "technical_core" not in kimi.calls[0]["output_type"].model_fields


def test_report_document_round_trips_as_versioned_json(tmp_path):
    document = generate_report(
        PAPER, "FULL PAPER TEXT", FakeKimi(), provider="kimi", model="kimi-k3",
        generated_at="2026-08-31T18:00:00+00:00",
    )
    path = save_report(document, tmp_path)
    assert load_report(path) == document
    assert report_ids(tmp_path) == {PAPER.arxiv_id}
    assert document.schema_version == 3


def test_schema_v2_report_loads_as_unverified_concept_notes(tmp_path):
    payload = generate_report(
        PAPER, "FULL PAPER TEXT", FakeKimi(), provider="kimi", model="kimi-k3",
        generated_at="2026-08-31T18:00:00+00:00",
    ).model_dump()
    payload["schema_version"] = 2
    payload["report"].pop("technical_core")
    payload["report"]["math_to_understand"] = [
        "complexidade O(n log n)", "erro de quantização por bloco",
    ]
    path = tmp_path / "2608.11111.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    document = load_report(path)

    assert document.schema_version == 3
    assert document.report.technical_core.kind == "concept"
    assert [item.status for item in document.report.technical_core.walkthroughs] == [
        "concept_only", "concept_only",
    ]
    assert all(not item.latex for item in document.report.technical_core.walkthroughs)


def test_report_keeps_a_source_link_only_when_excerpt_matches_the_page():
    excerpt = "Latency fell by 37 percent against the dense baseline."
    report = deep_report()
    report.evidence[0] = report.evidence[0].model_copy(update={
        "source_page": 2,
        "source_excerpt": excerpt,
    })
    full_text = (
        "[AI-RADAR PAGE 1]\nIntroduction and unrelated material.\n\n"
        f"[AI-RADAR PAGE 2]\nThe evaluation reports: {excerpt} More detail."
    )
    document = generate_report(
        PAPER, full_text, FakeKimi(report), provider="kimi", model="kimi-k3",
    )
    assert document.report.evidence[0].source_page == 2
    assert document.report.evidence[0].source_excerpt == excerpt


def test_report_drops_an_unverified_page_citation():
    report = deep_report()
    report.evidence[0] = report.evidence[0].model_copy(update={
        "source_page": 9,
        "source_excerpt": "This sentence was not present in the source paper.",
    })
    document = generate_report(
        PAPER, "[AI-RADAR PAGE 1]\nActual source text on the first page.",
        FakeKimi(report), provider="kimi", model="kimi-k3",
    )
    assert document.report.evidence[0].source_page is None
    assert document.report.evidence[0].source_excerpt == ""


def test_report_schema_rejects_an_invented_infra_tier():
    payload = deep_report().model_dump()
    payload["validation_tier"] = "probably_two_gpus"
    try:
        DeepReport.model_validate(payload)
    except Exception as exc:
        assert "validation_tier" in str(exc)
    else:
        raise AssertionError("tier aberto passou pelo schema")
