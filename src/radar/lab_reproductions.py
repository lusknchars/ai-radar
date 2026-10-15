"""Link a brief to Paper Raft studies that reran its claims, without promoting editorial status."""
from __future__ import annotations

from pathlib import Path
from shutil import copyfile
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .public_research import LabFlowRef, LabReproduction, ResearchPage


class LabReproductionEdition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arxiv_id: str = Field(pattern=r"^\d{4}\.\d{4,5}$")
    reproductions: tuple[LabReproduction, ...] = Field(min_length=1)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class FlowSource(_Strict):
    repo: str | None
    commit: str
    built_at: str


class FlowPaper(_Strict):
    title: str
    authors_short: str
    reference_checked: bool
    draft: bool


class FlowItem(_Strict):
    id: str
    kind: str


class FlowMethod(_Strict):
    name: str
    implements: tuple[str, ...]
    status: Literal["verified", "unverified", "failed", "no run"]
    color: int = Field(ge=0)


class FlowCase(_Strict):
    key: str
    label: str


class FlowMetricValue(_Strict):
    key: str
    value: float


class FlowRun(_Strict):
    run_id: str
    method: str
    params: dict[str, Any]
    case: str
    status: Literal["verified", "unverified", "failed", "stale", "missing"]
    passed: bool = Field(alias="pass")
    started_at: str | None
    metrics: tuple[FlowMetricValue, ...]


class FlowMetric(_Strict):
    key: str
    label: str
    note: str
    agg: Literal["max", "min", "mean"]
    format: Literal["sigma", "drop_percent", "sci", "kept_percent", "percent", "number"]


class FlowSnapshot(_Strict):
    """Mirror of paper-raft's raft/contracts/flow.schema.json (schema 1)."""

    schema_version: Literal[1] = Field(alias="schema")
    study: str
    source: FlowSource
    paper: FlowPaper
    items: tuple[FlowItem, ...]
    methods: tuple[FlowMethod, ...]
    cases: tuple[FlowCase, ...]
    runs: tuple[FlowRun, ...]
    metrics: tuple[FlowMetric, ...]


def load_flow(path: Path, ref: LabFlowRef) -> FlowSnapshot:
    if not path.is_file():
        raise ValueError(f"flow snapshot {path.name} is missing")
    snap = FlowSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    if snap.study != ref.study:
        raise ValueError("flow snapshot is for a different study")
    if snap.source.commit != ref.source_commit:
        raise ValueError("flow snapshot commit does not match the reproduction")
    return snap


def copy_lab_flow(page: ResearchPage, reproductions_root: Path, destination: Path) -> bool:
    """Publish the page's flow snapshot as papers/<id>/lab-flow.json. Returns whether there was one."""
    for item in page.lab_reproductions:
        if item.flow is not None:
            copyfile(reproductions_root / item.flow.file, destination / "lab-flow.json")
            return True
    return False


def apply_lab_reproductions(page: ResearchPage, path: Path) -> ResearchPage:
    if not path.exists():
        return page
    edition = LabReproductionEdition.model_validate_json(path.read_text(encoding="utf-8"))
    if edition.arxiv_id != page.arxiv_id:
        raise ValueError("lab reproduction belongs to a different paper")
    for item in edition.reproductions:
        if item.flow is not None:
            load_flow(path.parent / item.flow.file, item.flow)
    return ResearchPage.model_validate({
        **page.model_dump(),
        "lab_reproductions": edition.reproductions,
    })
