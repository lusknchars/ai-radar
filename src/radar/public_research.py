"""Public research model derived from the archive and optional deep report.

The module has one interface, ``build_research_page``. Callers do not decide
which findings qualify as source-linked or how absent analysis is represented.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .public_labels import (INFRASTRUCTURE_LABELS, SOFTWARE_SETUP_LABELS,
                            TRAINING_LABELS)
from .report import ReportDocument
from .site_data import Ponto

EditorialStatus = Literal["indexed", "source_mapped", "independently_tested"]
EvidenceBasis = Literal["source_linked", "inferred", "not_evaluated"]
FindingBasis = Literal["source_linked", "inferred"]
ExposureDimension = Literal[
    "quality", "compute", "latency", "operations", "compatibility",
    "security", "data_and_training", "reproducibility",
]

EXPOSURE_DIMENSIONS: tuple[ExposureDimension, ...] = (
    "quality", "compute", "latency", "operations", "compatibility",
    "security", "data_and_training", "reproducibility",
)


class ResearchClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(pattern=r"^claim-\d{2}$")
    statement: str = Field(min_length=1)
    basis: FindingBasis
    result: str = ""
    baseline: str = ""
    conditions: str = ""
    source_url: str = Field(pattern=r"^https://")
    source_page: int | None = Field(default=None, ge=1)
    source_excerpt: str = Field(default="", max_length=320)

    @model_validator(mode="after")
    def source_linked_requires_a_pinpoint(self) -> ResearchClaim:
        if self.basis == "source_linked" and (
            self.source_page is None or not self.source_excerpt.strip()
        ):
            raise ValueError(
                "source-linked claims require a PDF page and matching excerpt"
            )
        return self


class ExposureAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: ExposureDimension
    basis: EvidenceBasis
    finding: str = ""

    @model_validator(mode="after")
    def unevaluated_has_no_finding(self) -> ExposureAssessment:
        if self.basis == "not_evaluated" and self.finding:
            raise ValueError("not-evaluated exposure cannot present a finding")
        if self.basis != "not_evaluated" and not self.finding.strip():
            raise ValueError("evaluated exposure requires a finding")
        return self


class RiskNote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_id: str = Field(pattern=r"^risk-\d{2}$")
    statement: str = Field(min_length=1)
    basis: FindingBasis


class IndependentTest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")


class ResearchPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    arxiv_id: str
    title: str
    summary: str
    rationale: str
    technique: str
    family: str
    recommendation: str
    published: str
    as_of: str
    editorial_status: EditorialStatus
    source_url: str = Field(pattern=r"^https://")
    independent_implementations: int = Field(ge=0)
    total_implementations: int = Field(ge=0)
    stars: int = Field(ge=0)
    citations: int | None = Field(default=None, ge=0)
    claims: tuple[ResearchClaim, ...]
    exposure_map: tuple[ExposureAssessment, ...]
    risks: tuple[RiskNote, ...]
    minimum_test: tuple[str, ...]
    open_questions: tuple[str, ...]
    independent_tests: tuple[IndependentTest, ...] = ()
    report_available: bool

    @model_validator(mode="after")
    def exposure_map_is_complete(self) -> ResearchPage:
        dimensions = [item.dimension for item in self.exposure_map]
        if tuple(dimensions) != EXPOSURE_DIMENSIONS:
            raise ValueError(
                "exposure map must contain every dimension once in canonical order"
            )
        if self.editorial_status == "indexed" and self.report_available:
            raise ValueError("indexed page cannot claim that a deep report exists")
        has_independent_test = bool(self.independent_tests)
        if (self.editorial_status == "independently_tested") != has_independent_test:
            raise ValueError(
                "independently-tested status requires linked independent work"
            )
        if self.editorial_status != "indexed" and not self.report_available:
            raise ValueError(
                "source-mapped and independently-tested pages require a deep report"
            )
        return self


def _empty_exposure_map() -> dict[ExposureDimension, ExposureAssessment]:
    return {
        dimension: ExposureAssessment(
            dimension=dimension, basis="not_evaluated", finding="",
        )
        for dimension in EXPOSURE_DIMENSIONS
    }


def _report_exposures(
    document: ReportDocument,
) -> tuple[ExposureAssessment, ...]:
    report = document.report
    exposures = _empty_exposure_map()

    if report.validation_tier != "unknown" or report.evidence_tier != "unknown":
        exposures["compute"] = ExposureAssessment(
            dimension="compute",
            basis="inferred",
            finding=(
                f"Minimum useful test: {INFRASTRUCTURE_LABELS[report.validation_tier]}. "
                f"Published evidence: {INFRASTRUCTURE_LABELS[report.evidence_tier]}."
            ),
        )

    setup = [
        SOFTWARE_SETUP_LABELS[value]
        for value in report.software_setup if value != "unknown"
    ]
    if setup:
        exposures["compatibility"] = ExposureAssessment(
            dimension="compatibility", basis="inferred",
            finding=f"Reported setup: {', '.join(setup)}.",
        )

    if report.training_required != "unknown":
        exposures["data_and_training"] = ExposureAssessment(
            dimension="data_and_training", basis="inferred",
            finding=(
                f"Training requirement: "
                f"{TRAINING_LABELS[report.training_required]}."
            ),
        )

    if report.minimum_test:
        count = len(report.minimum_test)
        step = "step" if count == 1 else "steps"
        exposures["reproducibility"] = ExposureAssessment(
            dimension="reproducibility", basis="inferred",
            finding=(
                f"AI Radar defines a {count}-{step} falsification test. "
                "No reproduction is recorded."
            ),
        )

    return tuple(exposures[dimension] for dimension in EXPOSURE_DIMENSIONS)


def _claims_from_report(document: ReportDocument) -> tuple[ResearchClaim, ...]:
    return tuple(
        ResearchClaim(
            claim_id=f"claim-{index:02d}",
            statement=item.claim,
            basis=(
                "source_linked"
                if item.source_page is not None and item.source_excerpt
                else "inferred"
            ),
            result=item.result,
            baseline=item.baseline,
            conditions=item.conditions,
            source_url=document.source_url,
            source_page=item.source_page,
            source_excerpt=item.source_excerpt,
        )
        for index, item in enumerate(document.report.evidence, 1)
    )


def _claims_from_brief(paper: Ponto) -> tuple[ResearchClaim, ...]:
    source_url = f"https://arxiv.org/abs/{paper.arxiv_id}"
    claims = [ResearchClaim(
        claim_id="claim-01", statement=paper.resumo, basis="inferred",
        source_url=source_url,
    )]
    if paper.ganho_texto:
        claims.append(ResearchClaim(
            claim_id="claim-02", statement=paper.ganho_texto,
            basis="inferred", source_url=source_url,
        ))
    return tuple(claims)


def build_research_page(
    paper: Ponto, *, as_of: str, report: ReportDocument | None = None,
) -> ResearchPage:
    """Build the public model without network calls or new LLM inference."""
    if report is not None and report.arxiv_id != paper.arxiv_id:
        raise ValueError("deep report belongs to a different paper")

    if report is None:
        claims = _claims_from_brief(paper)
        exposures = tuple(_empty_exposure_map().values())
        risks: tuple[RiskNote, ...] = ()
        minimum_test: tuple[str, ...] = ()
        open_questions: tuple[str, ...] = ()
        status: EditorialStatus = "indexed"
    else:
        claims = _claims_from_report(report)
        exposures = _report_exposures(report)
        risks = tuple(
            RiskNote(
                risk_id=f"risk-{index:02d}", statement=statement,
                basis="inferred",
            )
            for index, statement in enumerate(report.report.main_risks, 1)
        )
        minimum_test = tuple(report.report.minimum_test)
        open_questions = tuple(report.report.unanswered_questions)
        status = "source_mapped"

    return ResearchPage(
        arxiv_id=paper.arxiv_id,
        title=paper.titulo,
        summary=paper.resumo,
        rationale=paper.porque,
        technique=paper.technique,
        family=paper.familia,
        recommendation=paper.pratica,
        published=paper.publicado,
        as_of=as_of,
        editorial_status=status,
        source_url=f"https://arxiv.org/abs/{paper.arxiv_id}",
        independent_implementations=paper.independent_impls,
        total_implementations=paper.total_impls,
        stars=paper.stars_total,
        citations=paper.citations,
        claims=claims,
        exposure_map=exposures,
        risks=risks,
        minimum_test=minimum_test,
        open_questions=open_questions,
        independent_tests=(),
        report_available=report is not None,
    )
