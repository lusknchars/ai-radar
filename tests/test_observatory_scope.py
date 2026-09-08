import json
from pathlib import Path

from radar.arxiv import matches_scope_focus
from radar.config import OBSERVATORY_SCOPE
from radar.models import Paper


CORPUS = Path("eval/observatory-scope-corpus.json")


def _paper(case: dict) -> Paper:
    return Paper(
        arxiv_id="2609.00001",
        title=case["title"],
        abstract=case["abstract"],
        authors=[],
        categories=["cs.LG"],
        published="2026-09-01",
    )


def test_observatory_scope_matches_the_versioned_24_case_corpus():
    cases = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert len(cases) >= 20
    results = {
        case["id"]: matches_scope_focus(_paper(case), OBSERVATORY_SCOPE)
        for case in cases
    }
    expected = {case["id"]: case["expected"] for case in cases}
    assert results == expected


def test_short_terms_match_words_instead_of_substrings():
    paper = Paper(
        arxiv_id="2609.00002",
        title="Capital Allocation for Models",
        abstract="A reliability study for economic forecasts.",
        authors=[],
        categories=["cs.LG"],
        published="2026-09-01",
    )
    assert matches_scope_focus(paper, OBSERVATORY_SCOPE) is False
