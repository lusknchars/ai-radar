import json
from html import escape
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar.builder_guides import (
    BenchmarkReading, BuilderReview, _AREA_PLANS, apply_builder_review,
    plan_for_family, render_application_plan,
)
from radar.models import FAMILIAS
from radar.public_research import ResearchPage
from radar.report import load_report
from radar.site import render_research_page

ROOT = Path(__file__).resolve().parents[1]


def _review():
    return BuilderReview.model_validate_json(
        (ROOT / "content/builders/2609.11060.json").read_text())


def _page():
    # Published input is not an answer key. Remove any existing editorial layer
    # so this works before and after regenerating the checked-in publication.
    value = json.loads((ROOT / "site/papers/2609.11060/index.json").read_text())
    value["builder_review"] = None
    value["builder_plan"] = plan_for_family(value["family"]).model_dump()
    return ResearchPage.model_validate(value)


def test_reviewed_table_cells_and_differences_match_independent_annotations():
    annotations = json.loads((ROOT / "eval/builder-readings.json").read_text())
    for paper in annotations["papers"]:
        review = BuilderReview.model_validate_json(
            (ROOT / "content/builders" / f'{paper["arxiv_id"]}.json').read_text())
        assert review.pdf_sha256 == paper["pdf_sha256"]
        assert len(review.comparisons) == len(paper["comparisons"])
        for cell in paper["comparisons"]:
            reading = review.comparisons[cell["index"]]
            assert reading.before == cell["before"]
            assert reading.after == cell["after"]
            assert reading.unit == cell["unit"]
            assert reading.source_page == cell["page"]
            assert reading.difference == cell["difference"]


@pytest.mark.parametrize("before,after,unit,expected", [
    (0, 10, "tokens/s", "+10 tokens/s; relative change undefined"),
    (None, 42, "score", "No matched comparison"),
    (10, 10, "percent", "+0 percentage points"),
    (80, 60, "percent", "-20 percentage points"),
])
def test_missing_zero_equal_and_negative_comparisons(before, after, unit, expected):
    values = _review().comparisons[0].model_dump()
    reading = BenchmarkReading.model_validate({
        **values, "before": before, "after": after, "unit": unit,
    })
    assert reading.difference == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 101])
def test_invalid_percentage_is_rejected(value):
    values = _review().comparisons[0].model_dump()
    with pytest.raises(ValidationError):
        BenchmarkReading.model_validate({**values, "after": value})


def test_small_api_costs_do_not_round_to_zero():
    values = _review().comparisons[0].model_dump()
    reading = BenchmarkReading.model_validate({
        **values, "before": .0005, "after": .0004, "unit": "USD",
    })
    assert reading.display(reading.before) == "$0.0005"
    assert reading.difference == "-0.0001 USD (-20.0%)"


def test_valid_review_changes_presentation_without_promoting_evidence(tmp_path):
    page = _page()
    path = tmp_path / "review.json"
    path.write_text(_review().model_dump_json())
    report = load_report(ROOT / "reports/2609.11060.json")
    result = apply_builder_review(page, path, report)
    assert result.builder_review == _review()
    assert result.builder_plan == _review().plan
    assert result.claims == page.claims
    assert result.editorial_status == page.editorial_status
    assert result.independent_tests == page.independent_tests
    html = render_research_page(result)
    assert html.index('id="for-builders"') < html.index('id="claims"')
    assert "+3 percentage points" in html
    assert escape(result.builder_review.intro) in html
    assert '2609.11060v1#page=5' in html
    plan = render_application_plan(result)
    assert result.builder_review.plan.measure in plan
    assert "## Record your result" in plan
    with pytest.raises(ValidationError, match="matching paper"):
        ResearchPage.model_validate({**result.model_dump(), "arxiv_id": "2609.09338"})
    with pytest.raises(ValidationError, match="reviewed proposal"):
        ResearchPage.model_validate({**result.model_dump(), "builder_plan": page.builder_plan})


@pytest.mark.parametrize("mismatch", ["report", "pdf", "missing"])
def test_stale_review_falls_back_without_old_findings(tmp_path, mismatch):
    page = _page()
    review = _review()
    report = load_report(ROOT / "reports/2609.11060.json")
    if mismatch == "missing":
        report = None
    else:
        key = "report_sha256" if mismatch == "report" else "pdf_sha256"
        review = review.model_copy(update={key: "a" * 64})
    path = tmp_path / "review.json"
    path.write_text(review.model_dump_json())
    result = apply_builder_review(page, path, report)
    assert result is page
    assert result.builder_review is None
    assert "## Read the benchmark correctly" not in render_application_plan(result)


def test_wrong_paper_and_invalid_pdf_page_are_rejected(tmp_path):
    path = tmp_path / "review.json"
    path.write_text(_review().model_dump_json())
    report = load_report(ROOT / "reports/2609.11060.json")
    with pytest.raises(ValueError, match="different paper"):
        apply_builder_review(_page().model_copy(update={"arxiv_id": "2609.09338"}), path, report)
    path.write_text(_review().model_copy(update={"method_page": 26}).model_dump_json())
    with pytest.raises(ValueError, match="outside"):
        apply_builder_review(_page(), path, report)
    with pytest.raises(ValidationError, match="versioned PDF"):
        BuilderReview.model_validate({**_review().model_dump(), "source_url": "https://example.com"})


def test_every_classified_area_has_a_plan_and_unknown_area_is_conservative():
    assert set(_AREA_PLANS) == set(FAMILIAS)
    assert len({plan_for_family(area).measure for area in FAMILIAS}) == len(FAMILIAS)
    assert plan_for_family("new_unclassified_area") == plan_for_family("outro")


def test_editorial_text_is_escaped_in_html():
    page = _page()
    plan = page.builder_plan.model_copy(update={"scenario": '<script>alert("x")</script>'})
    html = render_research_page(page.model_copy(update={"builder_plan": plan}))
    assert '<script>alert("x")</script>' not in html
    assert '&lt;script&gt;' in html
