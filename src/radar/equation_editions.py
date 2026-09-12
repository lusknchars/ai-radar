"""Load source-pinned editorial explanations without promoting evidence status."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .arxiv_html import sanitize_mathml
from .public_research import ResearchEquation, ResearchPage


class EquationEdition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arxiv_id: str = Field(pattern=r"^\d{4}\.\d{4,5}$")
    source_url: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fetched_at: date
    equations: tuple[ResearchEquation, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def source_and_markup_are_valid(self):
        import re
        if not re.fullmatch(rf"https://arxiv\.org/html/{re.escape(self.arxiv_id)}v[1-9]\d*", self.source_url):
            raise ValueError("equation edition requires this paper's versioned arXiv HTML URL")
        anchors = set()
        for equation in self.equations:
            if equation.anchor in anchors:
                raise ValueError("equation anchors must be unique")
            anchors.add(equation.anchor)
            if equation.source_url != f"{self.source_url}#{equation.anchor}":
                raise ValueError("equation source must link to its original anchor")
            if not equation.evidence_url.startswith(self.source_url + "#"):
                raise ValueError("equation evidence must link to the same paper version")
            if equation.mathml != sanitize_mathml(equation.mathml) or equation.context:
                raise ValueError("edition requires sanitized MathML and plain-text explanations")
        return self


def apply_equation_edition(page: ResearchPage, path: Path) -> ResearchPage:
    if not path.exists():
        return page
    edition = EquationEdition.model_validate_json(path.read_text(encoding="utf-8"))
    if edition.arxiv_id != page.arxiv_id:
        raise ValueError("equation edition belongs to a different paper")
    return ResearchPage.model_validate({
        **page.model_dump(),
        "equations": edition.equations,
        "equations_status": "selected",
        "core_kind": "formula",
        "equations_fetched_at": edition.fetched_at.isoformat(),
        "equations_source_url": edition.source_url,
        "equations_source_sha256": edition.source_sha256,
    })
