import csv
import io
from collections import Counter

import pytest

from radar.public_research_eval import (
    ResearchEvaluationCase,
    ResearchEvaluationManifest,
)
from radar.reader_study import (
    build_reader_study_assignments,
    render_reader_study_csv,
)


def _manifest(count=20):
    return ResearchEvaluationManifest(
        minimum_reports=count,
        minimum_readers=5,
        required_tracks=("inference", "agents"),
        cases=tuple(
            ResearchEvaluationCase(
                arxiv_id=f"2608.{index:05d}",
                track="agents" if index == 0 else "inference",
                expected_family="cache_kv",
                expected_recommendation="testar",
            )
            for index in range(count)
        ),
    )


def test_five_reader_schedule_is_balanced_without_repeat_exposure():
    assignments = build_reader_study_assignments(_manifest())

    assert len(assignments) == 40
    per_reader = Counter(item.participant_id for item in assignments)
    assert set(per_reader.values()) == {8}
    per_reader_condition = Counter(
        (item.participant_id, item.condition) for item in assignments
    )
    assert set(per_reader_condition.values()) == {4}
    per_paper_condition = Counter(
        (item.arxiv_id, item.condition) for item in assignments
    )
    assert set(per_paper_condition.values()) == {1}
    per_reader_paper = Counter(
        (item.participant_id, item.arxiv_id) for item in assignments
    )
    assert set(per_reader_paper.values()) == {1}


def test_schedule_csv_has_reviewable_empty_result_fields():
    rendered = render_reader_study_csv(
        build_reader_study_assignments(_manifest())
    )
    rows = list(csv.DictReader(io.StringIO(rendered)))

    assert len(rows) == 40
    assert rows[0]["decision"] == ""
    assert rows[0]["decision_reason"] == ""
    assert rows[0]["invented_risk"] == ""


def test_schedule_rejects_an_unbalanced_reader_count():
    with pytest.raises(ValueError, match="divisible"):
        build_reader_study_assignments(_manifest(), participant_count=6)
