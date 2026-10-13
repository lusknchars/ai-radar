"""Link a brief to Paper Raft studies that reran its claims, without promoting editorial status."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .public_research import LabReproduction, ResearchPage


class LabReproductionEdition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arxiv_id: str = Field(pattern=r"^\d{4}\.\d{4,5}$")
    reproductions: tuple[LabReproduction, ...] = Field(min_length=1)


def apply_lab_reproductions(page: ResearchPage, path: Path) -> ResearchPage:
    if not path.exists():
        return page
    edition = LabReproductionEdition.model_validate_json(path.read_text(encoding="utf-8"))
    if edition.arxiv_id != page.arxiv_id:
        raise ValueError("lab reproduction belongs to a different paper")
    return ResearchPage.model_validate({
        **page.model_dump(),
        "lab_reproductions": edition.reproductions,
    })
