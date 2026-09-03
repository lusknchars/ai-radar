"""Balanced assignments for the five-reader paper decision study."""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict

from pydantic import BaseModel, ConfigDict

from .public_research_eval import ResearchEvaluationManifest


class ReaderStudyAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    participant_id: str
    arxiv_id: str
    condition: str


def build_reader_study_assignments(
    manifest: ResearchEvaluationManifest,
    *,
    participant_count: int = 5,
) -> tuple[ReaderStudyAssignment, ...]:
    """Assign every paper once per condition without repeat exposure."""
    if participant_count < 2:
        raise ValueError("reader study needs at least two participants")
    if len(manifest.cases) % participant_count:
        raise ValueError(
            "corpus size must be divisible by the participant count"
        )

    buckets: dict[int, dict[str, list[ReaderStudyAssignment]]] = defaultdict(
        lambda: {"abstract": [], "research_page": []}
    )
    for index, case in enumerate(manifest.cases):
        abstract_reader = index % participant_count
        page_reader = (index + 1) % participant_count
        for reader, condition in (
            (abstract_reader, "abstract"),
            (page_reader, "research_page"),
        ):
            buckets[reader][condition].append(ReaderStudyAssignment(
                participant_id=f"reader-{reader + 1:02d}",
                arxiv_id=case.arxiv_id,
                condition=condition,
            ))

    assignments: list[ReaderStudyAssignment] = []
    for reader in range(participant_count):
        abstract = buckets[reader]["abstract"]
        research = buckets[reader]["research_page"]
        if len(abstract) != len(research):
            raise RuntimeError("reader conditions are not balanced")
        pairs = zip(abstract, research) if reader % 2 == 0 else zip(research, abstract)
        for pair in pairs:
            assignments.extend(pair)

    paper_conditions = Counter(
        (item.arxiv_id, item.condition) for item in assignments
    )
    expected = {
        (case.arxiv_id, condition)
        for case in manifest.cases
        for condition in ("abstract", "research_page")
    }
    if set(paper_conditions) != expected or set(paper_conditions.values()) != {1}:
        raise RuntimeError("each paper must appear once in each condition")
    return tuple(assignments)


def render_reader_study_csv(
    assignments: tuple[ReaderStudyAssignment, ...],
) -> str:
    output = io.StringIO(newline="")
    fields = [
        "participant_id", "arxiv_id", "condition", "decision", "seconds",
        "decision_reason", "invented_risk", "invented_condition",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for assignment in assignments:
        writer.writerow({
            **assignment.model_dump(),
            "decision": "",
            "seconds": "",
            "decision_reason": "",
            "invented_risk": "",
            "invented_condition": "",
        })
    return output.getvalue()
