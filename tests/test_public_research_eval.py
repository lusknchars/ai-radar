import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar.formulas import TechnicalCore
from radar.public_research import build_research_page
from radar.public_research_eval import (
    ResearchEvaluationCase,
    ResearchEvaluationManifest,
    evaluate_public_research,
    evaluate_reader_study,
    load_evaluation_manifest,
    load_reader_study,
    render_evaluation_markdown,
)
from radar.report import (
    DeepReport,
    EvidenceClaim,
    ReportDocument,
    SourceProvenance,
    save_report,
)
from radar.reader_study import build_reader_study_assignments
from radar.site_data import Ponto


def _case(index: int) -> ResearchEvaluationCase:
    return ResearchEvaluationCase(
        arxiv_id=f"2608.{index:05d}",
        track="agents" if index == 1 else "inference",
        expected_family="cache_kv",
        expected_recommendation="testar",
    )


def _manifest(count: int = 20) -> ResearchEvaluationManifest:
    return ResearchEvaluationManifest(
        minimum_reports=count,
        required_tracks=("inference", "agents"),
        cases=tuple(_case(index) for index in range(1, count + 1)),
    )


def _artifacts(arxiv_id: str):
    paper = Ponto(
        arxiv_id=arxiv_id,
        titulo="Cache paper",
        familia="cache_kv",
        pratica="testar",
        independent_impls=1,
        total_impls=1,
        stars_total=3,
        citations=1,
        idade_dias=4,
        ganho_eixo="memoria",
        ganho_fator=2.0,
        ganho_texto="Reports 2x lower memory use.",
        resumo="Compresses the cache.",
        publicado="2026-08-01",
        score=1.0,
        scope="inferencia",
    )
    report = ReportDocument(
        arxiv_id=arxiv_id,
        title=paper.titulo,
        generated_at="2026-09-03T12:00:00+00:00",
        provider="kimi",
        model="kimi-k3",
        source_url=f"https://arxiv.org/pdf/{arxiv_id}",
        source=SourceProvenance(
            pdf_sha256="a" * 64,
            extracted_text_sha256="b" * 64,
            extractor="pypdf",
            pages=8,
        ),
        report=DeepReport(
            one_sentence="Compresses cache pages.",
            problem="Memory use.",
            mechanism="Encodes old cache pages.",
            evidence=[EvidenceClaim(
                claim="Cuts cache memory",
                result="2x",
                baseline="full precision",
                conditions="long context",
                source_page=4,
                source_excerpt="Cache memory is reduced by two times in this setting.",
            )],
            validation_tier="single_gpu_24gb",
            evidence_tier="single_gpu_48_80gb",
            infrastructure_basis="explicit",
            software_setup=["custom_cuda_kernel"],
            training_required="inference_only",
            minimum_test=["Compare memory and quality on one workload."],
            main_risks=["The kernel may not support the target GPU."],
            unanswered_questions=["Does quality hold on longer contexts?"],
            technical_core=TechnicalCore(
                kind="system",
                summary="Cache pages pass through a lossy encoder.",
            ),
        ),
    )
    page = build_research_page(paper, as_of="2026-09-03", report=report)
    return page, report


def _write_page(root: Path, reports_root: Path, arxiv_id: str) -> None:
    page, report = _artifacts(arxiv_id)
    destination = root / "papers" / arxiv_id
    destination.mkdir(parents=True)
    destination.joinpath("index.json").write_text(
        page.model_dump_json(indent=2), encoding="utf-8"
    )
    save_report(report, reports_root)


def _write_reader_study(
    path: Path, manifest=None, *, page_seconds: int = 40,
) -> None:
    manifest = manifest or _manifest()
    rows = [
        "participant_id,arxiv_id,condition,decision,seconds,"
        "decision_reason,invented_risk,invented_condition"
    ]
    for assignment in build_reader_study_assignments(manifest):
        if assignment.condition == "abstract":
            decision, seconds = "read", 100
            reason = "The method may fit the budget"
        else:
            decision, seconds = "test", page_seconds
            reason = "The minimum test is affordable"
        rows.append(
            f"{assignment.participant_id},{assignment.arxiv_id},"
            f"{assignment.condition},{decision},{seconds},{reason},0,0"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_fixed_manifest_has_twenty_diverse_real_cases():
    manifest = load_evaluation_manifest(
        Path("eval/public-research-corpus.json")
    )
    assert len(manifest.cases) == 20
    assert {case.track for case in manifest.cases} == {
        "inference", "agents", "adjacent",
    }
    assert len({case.expected_family for case in manifest.cases}) == 10


def test_manifest_rejects_duplicate_papers():
    case = _case(1)
    with pytest.raises(ValidationError, match="duplicate"):
        ResearchEvaluationManifest(
            minimum_reports=2,
            required_tracks=("agents",),
            cases=(case, case),
        )


def test_twenty_complete_reports_pass_the_automated_gate(tmp_path):
    manifest = _manifest()
    reports = tmp_path / "reports"
    for case in manifest.cases:
        _write_page(tmp_path, reports, case.arxiv_id)
    reader_study = tmp_path / "reader-study.csv"
    _write_reader_study(reader_study, manifest)

    evaluation = evaluate_public_research(
        manifest, tmp_path, reports_root=reports,
        reader_study_path=reader_study,
    )

    assert evaluation.gate_passed is True
    assert evaluation.pages_valid == 20
    assert evaluation.reports_evaluated == 20
    assert evaluation.source_linked_claims == 20
    assert evaluation.evaluated_exposures == 80
    assert evaluation.failures == ()
    assert "Gate: **PASS**" in render_evaluation_markdown(evaluation)


def test_missing_report_remains_a_blocking_finding(tmp_path):
    manifest = _manifest()
    reports = tmp_path / "reports"
    for case in manifest.cases[:-1]:
        _write_page(tmp_path, reports, case.arxiv_id)
    reader_study = tmp_path / "reader-study.csv"
    _write_reader_study(reader_study, manifest)

    evaluation = evaluate_public_research(
        manifest, tmp_path, reports_root=reports,
        reader_study_path=reader_study,
    )

    assert evaluation.gate_passed is False
    assert evaluation.pages_valid == 19
    assert "1 public pages are missing" in evaluation.failures
    assert "only 19 of 20 required reports exist" in evaluation.failures


def test_reader_study_rejects_a_slow_research_page(tmp_path):
    path = tmp_path / "reader-study.csv"
    _write_reader_study(path, page_seconds=70)

    result = evaluate_reader_study(
        load_reader_study(path), minimum_readers=5,
    )

    assert result.passed is False
    assert result.time_ratio == 0.7
    assert "70%" in result.failures[0]


def test_reader_study_requires_each_corpus_paper_in_both_conditions(tmp_path):
    manifest = _manifest()
    path = tmp_path / "reader-study.csv"
    _write_reader_study(path, manifest)
    observations = load_reader_study(path)[:-1]

    result = evaluate_reader_study(
        observations,
        minimum_readers=5,
        expected_papers={case.arxiv_id for case in manifest.cases},
    )

    assert result.passed is False
    assert any("missing 1 paper conditions" in item for item in result.failures)


def test_release_gate_requires_reader_results_even_when_reports_pass(tmp_path):
    manifest = _manifest()
    reports = tmp_path / "reports"
    for case in manifest.cases:
        _write_page(tmp_path, reports, case.arxiv_id)

    evaluation = evaluate_public_research(
        manifest, tmp_path, reports_root=reports,
    )

    assert evaluation.gate_passed is False
    assert "reader study results are missing" in evaluation.failures


def test_release_gate_rejects_a_public_claim_changed_after_generation(tmp_path):
    manifest = _manifest()
    reports = tmp_path / "reports"
    for case in manifest.cases:
        _write_page(tmp_path, reports, case.arxiv_id)
    target = tmp_path / "papers" / manifest.cases[0].arxiv_id / "index.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["claims"][0]["statement"] = "A claim not present in the report"
    target.write_text(json.dumps(payload), encoding="utf-8")
    reader_study = tmp_path / "reader-study.csv"
    _write_reader_study(reader_study, manifest)

    evaluation = evaluate_public_research(
        manifest, tmp_path, reports_root=reports,
        reader_study_path=reader_study,
    )

    assert evaluation.gate_passed is False
    assert evaluation.pages_valid == 19
    assert "public page does not match" in evaluation.cases[0].problems[0]
