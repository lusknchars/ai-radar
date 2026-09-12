"""Apply selected, source-pinned exposure reviews without claiming reproduction."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .public_research import EXPOSURE_DIMENSIONS, ExposureAssessment, ResearchPage


class ExposureEdition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arxiv_id: str = Field(pattern=r"^\d{4}\.\d{4,5}$")
    source_url: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_at: date
    assessments: tuple[ExposureAssessment, ...]

    @model_validator(mode="after")
    def complete_and_pinned(self):
        if not re.fullmatch(
            rf"https://arxiv\.org/pdf/{re.escape(self.arxiv_id)}v[1-9]\d*",
            self.source_url,
        ):
            raise ValueError("exposure edition requires this paper's versioned PDF")
        if tuple(item.dimension for item in self.assessments) != EXPOSURE_DIMENSIONS:
            raise ValueError("exposure edition requires every dimension in canonical order")
        for item in self.assessments:
            if not item.limitation.strip() or not item.next_check.strip():
                raise ValueError("reviewed exposures require limits and a next check")
            if item.basis != "not_evaluated" and not item.source_url:
                raise ValueError("reviewed findings require a source, including interpretations")
            if item.source_url and item.source_url != f"{self.source_url}#page={item.source_page}":
                raise ValueError("exposure source must match the paper version and PDF page")
        return self


def apply_exposure_edition(page: ResearchPage, path: Path) -> ResearchPage:
    if not path.exists():
        return page
    edition = ExposureEdition.model_validate_json(path.read_text(encoding="utf-8"))
    if edition.arxiv_id != page.arxiv_id:
        raise ValueError("exposure edition belongs to a different paper")
    # A later deep report supersedes this limited review of an indexed brief.
    if page.report_available:
        return page
    return ResearchPage.model_validate({
        **page.model_dump(),
        "exposure_map": edition.assessments,
        "exposures_reviewed_at": edition.reviewed_at.isoformat(),
        "exposures_source_sha256": edition.source_sha256,
    })
