"""Offline acceptance gate for the public research pages.

The evaluator reads only published JSON. It does not call a model, download a
paper, or trust hidden application state. This keeps the same artifact that a
reader sees at the center of the release decision.
"""
from __future__ import annotations

import json
import csv
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import FAMILIAS, PRATICAS
from .public_research import (
    EXPOSURE_DIMENSIONS,
    ResearchPage,
    build_research_page,
)
from .report import load_report
from .site_data import Ponto

ResearchTrack = Literal["inference", "agents", "adjacent"]
CaseStatus = Literal["valid", "missing", "invalid"]
ReaderDecision = Literal["reject", "read", "test"]


class ResearchEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arxiv_id: str = Field(min_length=1)
    track: ResearchTrack
    expected_family: str
    expected_recommendation: str

    @model_validator(mode="after")
    def expected_labels_are_public_labels(self) -> ResearchEvaluationCase:
        if self.expected_family not in FAMILIAS:
            raise ValueError(f"unknown expected family: {self.expected_family}")
        if self.expected_recommendation not in PRATICAS:
            raise ValueError(
                f"unknown expected recommendation: {self.expected_recommendation}"
            )
        return self


class ResearchEvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    minimum_reports: int = Field(default=20, ge=1)
    minimum_readers: int = Field(default=5, ge=1)
    required_tracks: tuple[ResearchTrack, ...] = ("inference", "agents")
    cases: tuple[ResearchEvaluationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def corpus_can_reach_its_gate(self) -> ResearchEvaluationManifest:
        ids = [case.arxiv_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation corpus contains duplicate arXiv IDs")
        if self.minimum_reports > len(self.cases):
            raise ValueError("minimum_reports exceeds the corpus size")
        tracks = {case.track for case in self.cases}
        missing = set(self.required_tracks) - tracks
        if missing:
            raise ValueError(
                f"evaluation corpus is missing tracks: {', '.join(sorted(missing))}"
            )
        return self


class ResearchCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arxiv_id: str
    track: ResearchTrack
    status: CaseStatus
    editorial_status: str = ""
    claims: int = Field(default=0, ge=0)
    source_linked_claims: int = Field(default=0, ge=0)
    evaluated_exposures: int = Field(default=0, ge=0)
    risks: int = Field(default=0, ge=0)
    minimum_test_steps: int = Field(default=0, ge=0)
    problems: tuple[str, ...] = ()


class ReaderStudyObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    participant_id: str = Field(min_length=1)
    arxiv_id: str = Field(min_length=1)
    condition: Literal["abstract", "research_page"]
    decision: ReaderDecision
    seconds: float = Field(gt=0)
    decision_reason: str = Field(min_length=1, max_length=1200)
    invented_risk: bool
    invented_condition: bool


class ReaderStudyEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    participants: int = Field(ge=0)
    observations: int = Field(ge=0)
    abstract_median_seconds: float | None = Field(default=None, gt=0)
    research_page_median_seconds: float | None = Field(default=None, gt=0)
    time_ratio: float | None = Field(default=None, ge=0)
    invented_risks: int = Field(ge=0)
    invented_conditions: int = Field(ge=0)
    passed: bool
    failures: tuple[str, ...]


class ResearchEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    gate_passed: bool
    cases_total: int = Field(ge=0)
    pages_valid: int = Field(ge=0)
    reports_evaluated: int = Field(ge=0)
    source_linked_claims: int = Field(ge=0)
    claims_total: int = Field(ge=0)
    evaluated_exposures: int = Field(ge=0)
    exposures_total: int = Field(ge=0)
    tracks: dict[str, int]
    families: dict[str, int]
    reader_study: ReaderStudyEvaluation
    failures: tuple[str, ...]
    cases: tuple[ResearchCaseResult, ...]


def load_evaluation_manifest(path: Path) -> ResearchEvaluationManifest:
    return ResearchEvaluationManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _csv_bool(value: str, *, field: str, line_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(
        f"reader study line {line_number} has invalid {field}: {value!r}"
    )


def load_reader_study(path: Path) -> tuple[ReaderStudyObservation, ...]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        expected = {
            "participant_id", "arxiv_id", "condition", "decision", "seconds",
            "decision_reason", "invented_risk", "invented_condition",
        }
        if set(rows.fieldnames or ()) != expected:
            raise ValueError(
                "reader study columns must be: " + ", ".join(sorted(expected))
            )
        return tuple(
            ReaderStudyObservation(
                participant_id=row["participant_id"].strip(),
                arxiv_id=row["arxiv_id"].strip(),
                condition=row["condition"].strip(),
                decision=row["decision"].strip(),
                seconds=float(row["seconds"]),
                decision_reason=row["decision_reason"].strip(),
                invented_risk=_csv_bool(
                    row["invented_risk"], field="invented_risk",
                    line_number=index,
                ),
                invented_condition=_csv_bool(
                    row["invented_condition"], field="invented_condition",
                    line_number=index,
                ),
            )
            for index, row in enumerate(rows, 2)
        )


def evaluate_reader_study(
    observations: tuple[ReaderStudyObservation, ...], *, minimum_readers: int,
    expected_papers: set[str] | None = None,
) -> ReaderStudyEvaluation:
    failures: list[str] = []
    participants = {item.participant_id for item in observations}
    if len(participants) < minimum_readers:
        failures.append(
            f"only {len(participants)} of {minimum_readers} required readers participated"
        )
    for participant in sorted(participants):
        conditions = {
            item.condition for item in observations
            if item.participant_id == participant
        }
        if conditions != {"abstract", "research_page"}:
            failures.append(
                f"reader {participant} did not evaluate both conditions"
            )

    repeated_exposure = Counter(
        (item.participant_id, item.arxiv_id) for item in observations
    )
    duplicates = sum(count > 1 for count in repeated_exposure.values())
    if duplicates:
        failures.append(
            f"{duplicates} reader-paper pairs repeat the same paper"
        )

    if expected_papers is not None:
        observed_papers = {item.arxiv_id for item in observations}
        unknown = observed_papers - expected_papers
        if unknown:
            failures.append(
                f"reader study contains {len(unknown)} papers outside the corpus"
            )
        coverage = Counter(
            (item.arxiv_id, item.condition) for item in observations
            if item.arxiv_id in expected_papers
        )
        expected_coverage = {
            (arxiv_id, condition)
            for arxiv_id in expected_papers
            for condition in ("abstract", "research_page")
        }
        missing_coverage = expected_coverage - coverage.keys()
        repeated_coverage = sum(count > 1 for count in coverage.values())
        if missing_coverage:
            failures.append(
                f"reader study is missing {len(missing_coverage)} paper conditions"
            )
        if repeated_coverage:
            failures.append(
                f"reader study repeats {repeated_coverage} paper conditions"
            )

    abstract_times = [
        item.seconds for item in observations if item.condition == "abstract"
    ]
    page_times = [
        item.seconds for item in observations
        if item.condition == "research_page"
    ]
    abstract_median = median(abstract_times) if abstract_times else None
    page_median = median(page_times) if page_times else None
    ratio = (
        page_median / abstract_median
        if page_median is not None and abstract_median is not None else None
    )
    if not abstract_times or not page_times:
        failures.append("reader study needs observations for both conditions")
    elif ratio is not None and ratio > 0.5:
        failures.append(
            f"research page median time is {ratio:.0%} of the abstract baseline"
        )

    invented_risks = sum(item.invented_risk for item in observations)
    invented_conditions = sum(item.invented_condition for item in observations)
    if invented_risks:
        failures.append(f"readers invented {invented_risks} risk statements")
    if invented_conditions:
        failures.append(
            f"readers invented {invented_conditions} experimental conditions"
        )
    return ReaderStudyEvaluation(
        participants=len(participants),
        observations=len(observations),
        abstract_median_seconds=abstract_median,
        research_page_median_seconds=page_median,
        time_ratio=ratio,
        invented_risks=invented_risks,
        invented_conditions=invented_conditions,
        passed=not failures,
        failures=tuple(failures),
    )


def _evaluate_case(
    case: ResearchEvaluationCase, site_root: Path, reports_root: Path,
) -> tuple[ResearchCaseResult, ResearchPage | None]:
    path = site_root / "papers" / case.arxiv_id / "index.json"
    if not path.is_file():
        return ResearchCaseResult(
            arxiv_id=case.arxiv_id,
            track=case.track,
            status="missing",
            problems=("public JSON is missing",),
        ), None
    try:
        page = ResearchPage.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ResearchCaseResult(
            arxiv_id=case.arxiv_id,
            track=case.track,
            status="invalid",
            problems=(f"public JSON is invalid: {type(exc).__name__}",),
        ), None

    problems: list[str] = []
    if page.arxiv_id != case.arxiv_id:
        problems.append(f"page identifies itself as {page.arxiv_id}")
    if page.family != case.expected_family:
        problems.append(
            f"family changed from {case.expected_family} to {page.family}"
        )
    if page.recommendation != case.expected_recommendation:
        problems.append(
            "recommendation changed from "
            f"{case.expected_recommendation} to {page.recommendation}"
        )

    report_path = reports_root / f"{case.arxiv_id}.json"
    if page.report_available:
        if not report_path.is_file():
            problems.append("source-mapped page has no versioned report JSON")
        else:
            try:
                report = load_report(report_path)
                paper = Ponto(
                    arxiv_id=page.arxiv_id,
                    titulo=page.title,
                    familia=page.family,
                    pratica=page.recommendation,
                    independent_impls=page.independent_implementations,
                    total_impls=page.total_implementations,
                    stars_total=page.stars,
                    citations=page.citations,
                    idade_dias=0,
                    ganho_eixo="nenhum",
                    ganho_fator=None,
                    ganho_texto="",
                    resumo=page.summary,
                    publicado=page.published,
                    score=0,
                    scope="evaluation",
                    technique=page.technique,
                    porque=page.rationale,
                )
                expected = build_research_page(
                    paper, as_of=page.as_of, report=report,
                )
                if expected != page:
                    problems.append(
                        "public page does not match its versioned report"
                    )
            except (OSError, ValueError) as exc:
                problems.append(
                    f"versioned report is invalid: {type(exc).__name__}"
                )
    elif report_path.exists():
        problems.append("indexed page ignores an available versioned report")

    source_linked = sum(
        claim.basis == "source_linked" for claim in page.claims
    )
    evaluated_exposures = sum(
        item.basis != "not_evaluated" for item in page.exposure_map
    )
    return ResearchCaseResult(
        arxiv_id=case.arxiv_id,
        track=case.track,
        status="invalid" if problems else "valid",
        editorial_status=page.editorial_status,
        claims=len(page.claims),
        source_linked_claims=source_linked,
        evaluated_exposures=evaluated_exposures,
        risks=len(page.risks),
        minimum_test_steps=len(page.minimum_test),
        problems=tuple(problems),
    ), page


def evaluate_public_research(
    manifest: ResearchEvaluationManifest, site_root: Path,
    *, reports_root: Path | None = None,
    reader_study_path: Path | None = None,
) -> ResearchEvaluation:
    """Evaluate the public artifacts against a fixed, diverse corpus."""
    results: list[ResearchCaseResult] = []
    pages: list[ResearchPage] = []
    failures: list[str] = []
    family_counts: Counter[str] = Counter()

    reports_root = reports_root or site_root.parent / "reports"
    for case in manifest.cases:
        result, page = _evaluate_case(case, site_root, reports_root)
        results.append(result)
        if page is not None and result.status == "valid":
            pages.append(page)
            family_counts[page.family] += 1

    valid_count = len(pages)
    missing_count = sum(result.status == "missing" for result in results)
    invalid_count = sum(result.status == "invalid" for result in results)
    reports = [page for page in pages if page.report_available]
    source_linked = sum(
        claim.basis == "source_linked"
        for page in pages for claim in page.claims
    )
    claims_total = sum(len(page.claims) for page in pages)
    evaluated_exposures = sum(
        item.basis != "not_evaluated"
        for page in pages for item in page.exposure_map
    )
    exposures_total = len(pages) * len(EXPOSURE_DIMENSIONS)

    if len(manifest.cases) < 20:
        failures.append("the corpus contains fewer than 20 papers")
    if missing_count:
        failures.append(f"{missing_count} public pages are missing")
    if invalid_count:
        failures.append(f"{invalid_count} public pages are invalid")
    if len(reports) < manifest.minimum_reports:
        failures.append(
            f"only {len(reports)} of {manifest.minimum_reports} required reports exist"
        )

    without_linked_claim = [
        page.arxiv_id for page in reports
        if not any(claim.basis == "source_linked" for claim in page.claims)
    ]
    if without_linked_claim:
        failures.append(
            f"{len(without_linked_claim)} reports have no source-linked claim"
        )
    without_exposure = [
        page.arxiv_id for page in reports
        if not any(item.basis != "not_evaluated" for item in page.exposure_map)
    ]
    if without_exposure:
        failures.append(
            f"{len(without_exposure)} reports have no evaluated exposure"
        )
    without_risk = [page.arxiv_id for page in reports if not page.risks]
    if without_risk:
        failures.append(f"{len(without_risk)} reports have no risk note")
    without_test = [page.arxiv_id for page in reports if not page.minimum_test]
    if without_test:
        failures.append(f"{len(without_test)} reports have no minimum test")

    if reader_study_path is None or not reader_study_path.is_file():
        reader_study = evaluate_reader_study(
            (), minimum_readers=manifest.minimum_readers,
        )
        failures.append("reader study results are missing")
    else:
        reader_study = evaluate_reader_study(
            load_reader_study(reader_study_path),
            minimum_readers=manifest.minimum_readers,
            expected_papers={case.arxiv_id for case in manifest.cases},
        )
        failures.extend(
            f"reader study: {failure}" for failure in reader_study.failures
        )

    track_counts = Counter(case.track for case in manifest.cases)
    return ResearchEvaluation(
        gate_passed=not failures,
        cases_total=len(manifest.cases),
        pages_valid=valid_count,
        reports_evaluated=len(reports),
        source_linked_claims=source_linked,
        claims_total=claims_total,
        evaluated_exposures=evaluated_exposures,
        exposures_total=exposures_total,
        tracks=dict(sorted(track_counts.items())),
        families=dict(sorted(family_counts.items())),
        reader_study=reader_study,
        failures=tuple(failures),
        cases=tuple(results),
    )


def render_evaluation_markdown(evaluation: ResearchEvaluation) -> str:
    result = "PASS" if evaluation.gate_passed else "FAIL"
    lines = [
        "# Public research evaluation",
        "",
        f"Gate: **{result}**",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Corpus | {evaluation.cases_total} papers |",
        f"| Valid public pages | {evaluation.pages_valid} |",
        f"| Deep reports | {evaluation.reports_evaluated} |",
        (
            "| Source-linked claims | "
            f"{evaluation.source_linked_claims}/{evaluation.claims_total} |"
        ),
        (
            "| Evaluated exposures | "
            f"{evaluation.evaluated_exposures}/{evaluation.exposures_total} |"
        ),
        f"| Target readers | {evaluation.reader_study.participants} |",
        (
            "| Research-page time ratio | "
            f"{evaluation.reader_study.time_ratio:.0%} |"
            if evaluation.reader_study.time_ratio is not None
            else "| Research-page time ratio | not measured |"
        ),
        "",
    ]
    if evaluation.failures:
        lines.extend(["## Blocking findings", ""])
        lines.extend(f"- {failure}" for failure in evaluation.failures)
        lines.append("")
    lines.extend([
        "## Papers",
        "",
        "| arXiv | Track | Page | Report | Linked claims | Exposures | Risks | Test |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for case in evaluation.cases:
        report = case.editorial_status or "none"
        lines.append(
            f"| {case.arxiv_id} | {case.track} | {case.status} | {report} | "
            f"{case.source_linked_claims}/{case.claims} | "
            f"{case.evaluated_exposures}/{len(EXPOSURE_DIMENSIONS)} | "
            f"{case.risks} | {case.minimum_test_steps} |"
        )
        for problem in case.problems:
            lines.append(f"|  |  | problem | {problem} |  |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def evaluation_json(evaluation: ResearchEvaluation) -> str:
    return json.dumps(evaluation.model_dump(mode="json"), indent=2) + "\n"
