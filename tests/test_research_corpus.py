import json
from datetime import date

import pytest

from radar.models import Paper, Signal
from radar.public_research_eval import (
    ResearchEvaluationCase,
    ResearchEvaluationManifest,
)
from radar.research_corpus import prepare_evaluation_database
from radar.store import Store


def _manifest(ids):
    return ResearchEvaluationManifest(
        minimum_reports=2,
        required_tracks=("inference", "agents"),
        cases=(
            ResearchEvaluationCase(
                arxiv_id=ids[0], track="inference",
                expected_family="cache_kv",
                expected_recommendation="testar",
            ),
            ResearchEvaluationCase(
                arxiv_id=ids[1], track="agents",
                expected_family="cache_kv",
                expected_recommendation="testar",
            ),
        ),
    )


def _source_database(path, ids):
    store = Store(path)
    store.init_schema()
    for arxiv_id in ids:
        store.upsert_paper(
            Paper(
                arxiv_id=arxiv_id,
                title=f"Paper {arxiv_id}",
                abstract="Abstract",
                authors=["A"],
                categories=["cs.LG"],
                published="2026-08-01",
            ),
            seen_at="2026-08-02",
            scope="inferencia",
        )
        store.record_signal(
            arxiv_id,
            Signal(
                total_impls=2,
                independent_impls=1,
                velocity_14d=0,
                stars_total=4,
                citations=2,
            ),
            score=1.0,
            checked_at="2026-09-01",
        )
    store.close()


def _checkpoint(path, ids):
    records = []
    for arxiv_id in ids:
        records.append({
            "arxiv_id": arxiv_id,
            "provider": "kimi",
            "model": "kimi-k3",
            "judgment": {
                "technique": "Cache compression",
                "familia": "cache_kv",
                "pratica": "testar",
                "ganho_eixo": "memoria",
                "ganho_fator": 2.0,
                "ganho_texto": "Reports 2x lower memory use.",
                "resumo": "Compresses cache pages.",
                "porque": "A small local test is possible.",
            },
        })
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_prepares_current_schema_database_without_changing_source(tmp_path):
    ids = ("2608.00001", "2608.00002")
    source = tmp_path / "source.db"
    checkpoint = tmp_path / "checkpoint.jsonl"
    destination = tmp_path / "evaluation.db"
    _source_database(source, ids)
    _checkpoint(checkpoint, ids)

    result = prepare_evaluation_database(
        _manifest(ids),
        source_database=source,
        checkpoint=checkpoint,
        destination=destination,
        as_of="2026-09-03",
    )

    assert result.papers == 2
    assert result.provider == "kimi"
    prepared = Store(destination)
    prepared.init_schema()
    data = prepared.site_data(date(2026, 9, 3))
    assert {paper.arxiv_id for paper in data.pontos} == set(ids)
    assert {paper.scope for paper in data.pontos} == {"inferencia", "agentes"}
    prepared.close()

    original = Store(source)
    assert len(original.all_papers()) == 2
    original.close()


def test_does_not_replace_an_existing_evaluation_database_by_default(tmp_path):
    ids = ("2608.00001", "2608.00002")
    source = tmp_path / "source.db"
    checkpoint = tmp_path / "checkpoint.jsonl"
    destination = tmp_path / "evaluation.db"
    _source_database(source, ids)
    _checkpoint(checkpoint, ids)
    destination.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="replace=True"):
        prepare_evaluation_database(
            _manifest(ids),
            source_database=source,
            checkpoint=checkpoint,
            destination=destination,
            as_of="2026-09-03",
        )
    assert destination.read_text(encoding="utf-8") == "keep"
