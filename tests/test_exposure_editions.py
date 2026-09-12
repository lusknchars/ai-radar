import json
from datetime import date
from pathlib import Path

import pytest

from radar.exposure_editions import ExposureEdition, apply_exposure_edition
from radar.public_research import ExposureAssessment, ResearchPage
from radar.publish import publish_site
from radar.site import render_research_page
from radar.store import Store

ROOT = Path(__file__).resolve().parents[1]
EDITION = ROOT / "content/exposures/2608.21223.json"


def page():
    return ResearchPage.model_validate_json(
        (ROOT / "site/papers/2608.21223/index.json").read_text())


def test_review_exposes_authors_results_interpretation_and_unknowns():
    original = page()
    reviewed = apply_exposure_edition(original, EDITION)
    assert reviewed.editorial_status == "indexed"
    assert not reviewed.report_available
    assert reviewed.independent_tests == ()
    assert reviewed.claims == original.claims
    assert reviewed.validation_tier == "unknown"
    assert [item.basis for item in reviewed.exposure_map] == [
        "source_linked", "source_linked", "source_linked", "not_evaluated",
        "inferred", "not_evaluated", "source_linked", "not_evaluated",
    ]
    html = render_research_page(reviewed)
    assert html.count('class="exposure-source"') == 5
    assert 'href="https://arxiv.org/pdf/2608.21223v1#page=9"' in html
    assert '76.41%' in html and '66.85%' in html and '76.53%' in html
    assert 'rental cost remain unknown' in html
    assert '5 of 8' in html


@pytest.mark.parametrize("change", [
    "missing_excerpt", "wrong_version", "wrong_page", "duplicate_dimension",
    "unsafe_url", "missing_limits", "inference_without_source", "unknown_finding",
])
def test_review_rejects_unsupported_provenance_or_false_coverage(change):
    data = json.loads(EDITION.read_text())
    first = data["assessments"][0]
    if change == "missing_excerpt":
        first["source_excerpt"] = ""
    elif change == "wrong_version":
        first["source_url"] = first["source_url"].replace("v1", "v2")
    elif change == "wrong_page":
        first["source_page"] = 10
    elif change == "duplicate_dimension":
        data["assessments"][1] = first
    elif change == "unsafe_url":
        first["source_url"] = "javascript:alert(1)"
    elif change == "missing_limits":
        first["limitation"] = " "
    elif change == "inference_without_source":
        for key in ("source_url", "source_page", "source_excerpt"):
            data["assessments"][4].pop(key)
    else:
        data["assessments"][3]["finding"] = "Ready for production"
    with pytest.raises(ValueError):
        ExposureEdition.model_validate(data)


def test_missing_review_preserves_page_and_wrong_paper_fails(tmp_path):
    original = page()
    assert apply_exposure_edition(original, tmp_path / "missing.json") is original
    with pytest.raises(ValueError, match="different paper"):
        apply_exposure_edition(original.model_copy(update={"arxiv_id": "2608.99999"}), EDITION)


def test_later_report_is_not_overwritten_by_selected_review():
    report_page = ResearchPage.model_validate({
        **page().model_dump(), "editorial_status": "source_mapped", "report_available": True,
    })
    assert apply_exposure_edition(report_page, EDITION) is report_page


def test_source_text_is_escaped_in_the_reading_view():
    data = json.loads(EDITION.read_text())
    data["assessments"][0]["source_excerpt"] = '<script>alert("test")</script>'
    edition = ExposureEdition.model_validate(data)
    rendered = render_research_page(page().model_copy(update={"exposure_map": edition.assessments}))
    assert '<script>alert("test")</script>' not in rendered
    assert '&lt;script&gt;' in rendered


def test_partial_source_cannot_be_exported_as_provenance():
    with pytest.raises(ValueError, match="together"):
        ExposureAssessment(dimension="quality", basis="inferred", finding="An inference", source_page=2)


def test_publication_includes_review_but_raw_baseline_can_exclude_it(tmp_path):
    # Copy the fixed sample DB so publication cannot mutate the tracked corpus.
    from shutil import copyfile
    database = tmp_path / "sample.db"
    copyfile(ROOT / "data/radar-state.db", database)
    store = Store(database)
    try:
        for name, content in (("reviewed", ROOT / "content"), ("raw", tmp_path / "empty")):
            publish_site(store, tmp_path / name, date(2026, 9, 12), content_root=content)
        reviewed = ResearchPage.model_validate_json(
            (tmp_path / "reviewed/papers/2608.21223/index.json").read_text())
        raw = ResearchPage.model_validate_json(
            (tmp_path / "raw/papers/2608.21223/index.json").read_text())
        assert sum(item.basis != "not_evaluated" for item in reviewed.exposure_map) == 5
        assert all(item.basis == "not_evaluated" for item in raw.exposure_map)
        assert not raw.exposures_reviewed_at
    finally:
        store.close()
