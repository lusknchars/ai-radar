"""Build the isolated database used by the public research evaluation."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .models import Judgment, Paper, Signal
from .public_research_eval import ResearchEvaluationManifest
from .store import Store


@dataclass(frozen=True)
class PreparedCorpus:
    destination: Path
    papers: int
    provider: str
    model: str


def _checkpoint_records(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        arxiv_id = record.get("arxiv_id")
        if not arxiv_id:
            raise ValueError(f"checkpoint line {line_number} has no arxiv_id")
        if arxiv_id in records:
            raise ValueError(f"checkpoint repeats {arxiv_id}")
        records[arxiv_id] = record
    return records


def prepare_evaluation_database(
    manifest: ResearchEvaluationManifest,
    *,
    source_database: Path,
    checkpoint: Path,
    destination: Path,
    as_of: str,
    replace: bool = False,
) -> PreparedCorpus:
    """Copy the fixed corpus into a current-schema database without model calls."""
    if source_database.resolve() == destination.resolve():
        raise ValueError("evaluation database must differ from the source database")
    if destination.exists() and not replace:
        raise FileExistsError(
            f"destination already exists: {destination}; pass replace=True"
        )
    evaluation_day = date.fromisoformat(as_of)
    records = _checkpoint_records(checkpoint)
    wanted = {case.arxiv_id for case in manifest.cases}
    missing_records = wanted - records.keys()
    if missing_records:
        raise ValueError(
            "checkpoint is missing: " + ", ".join(sorted(missing_records))
        )
    providers = {records[arxiv_id].get("provider", "") for arxiv_id in wanted}
    models = {records[arxiv_id].get("model", "") for arxiv_id in wanted}
    if len(providers) != 1 or "" in providers:
        raise ValueError("checkpoint mixes providers")
    if len(models) != 1 or "" in models:
        raise ValueError("checkpoint mixes models")

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f"{destination.name}.", suffix=".tmp",
        dir=destination.parent, delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    source: sqlite3.Connection | None = None
    target: Store | None = None
    try:
        source = sqlite3.connect(
            f"file:{source_database.resolve()}?mode=ro", uri=True,
        )
        source.row_factory = sqlite3.Row
        target = Store(temporary)
        target.init_schema()
        for case in manifest.cases:
            paper_row = source.execute(
                "SELECT arxiv_id, title, abstract, authors, categories, "
                "published, first_seen FROM papers WHERE arxiv_id=?",
                (case.arxiv_id,),
            ).fetchone()
            if paper_row is None:
                raise ValueError(
                    f"source database has no paper {case.arxiv_id}"
                )
            signal_row = source.execute(
                "SELECT total_impls, independent_impls, velocity_14d, "
                "stars_total, citations, score, checked_at FROM signals "
                "WHERE arxiv_id=? ORDER BY checked_at DESC LIMIT 1",
                (case.arxiv_id,),
            ).fetchone()
            if signal_row is None:
                raise ValueError(
                    f"source database has no signal for {case.arxiv_id}"
                )

            paper = Paper(
                arxiv_id=paper_row["arxiv_id"],
                title=paper_row["title"],
                abstract=paper_row["abstract"],
                authors=json.loads(paper_row["authors"]),
                categories=json.loads(paper_row["categories"]),
                published=paper_row["published"],
            )
            judgment = Judgment(**records[case.arxiv_id]["judgment"])
            signal = Signal(
                total_impls=signal_row["total_impls"],
                independent_impls=signal_row["independent_impls"],
                velocity_14d=signal_row["velocity_14d"],
                stars_total=signal_row["stars_total"],
                citations=signal_row["citations"],
            )
            target.upsert_paper(
                paper,
                seen_at=paper_row["first_seen"],
                scope="agentes" if case.track == "agents" else "inferencia",
            )
            target.record_judgment(
                paper.arxiv_id,
                judgment,
                model=records[case.arxiv_id]["model"],
                judged_at=as_of,
            )
            target.record_signal(
                paper.arxiv_id,
                signal,
                score=signal_row["score"],
                checked_at=signal_row["checked_at"],
            )

        data = target.site_data(evaluation_day)
        if len(data.pontos) != len(manifest.cases):
            raise RuntimeError(
                f"prepared {len(data.pontos)} of {len(manifest.cases)} papers"
            )
        target.close()
        target = None
        os.replace(temporary, destination)
    except Exception:
        if target is not None:
            target.close()
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if source is not None:
            source.close()

    return PreparedCorpus(
        destination=destination,
        papers=len(manifest.cases),
        provider=next(iter(providers)),
        model=next(iter(models)),
    )
