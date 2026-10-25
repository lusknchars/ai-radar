import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar.lab_reproductions import apply_lab_reproductions
from radar.public_research import ResearchPage
from radar.site import render_research_page

ROOT = Path(__file__).resolve().parents[1]
EDITION = ROOT / "content/reproductions/2608.27428.json"


def page(arxiv_id="2608.27428"):
    raw = json.loads((ROOT / f"site/papers/{arxiv_id}/index.json").read_text())
    return ResearchPage.model_validate({**raw, "lab_reproductions": []})


def test_reproduction_adds_a_scoped_section_without_promoting_the_brief():
    original = page()
    linked = apply_lab_reproductions(original, EDITION)
    assert len(linked.lab_reproductions) == 1
    assert linked.editorial_status == original.editorial_status == "indexed"
    assert linked.independent_tests == () and not linked.report_available
    assert linked.validation_tier == original.validation_tier and linked.claims == original.claims
    html = render_research_page(linked)
    assert 'id="lab-reproductions"' in html and 'href="#lab-reproductions"' in html
    assert 'href="https://lusknchars.github.io/paper-raft/#study/transduced-lm-2026"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "5 of 5 methods verified" in html and "not Table 2&#x27;s numbers" in html


def test_missing_file_leaves_the_page_unchanged(tmp_path):
    original = page()
    assert apply_lab_reproductions(original, tmp_path / "none.json") == original
    assert 'id="lab-reproductions"' not in render_research_page(original)


@pytest.mark.parametrize("change", ["unsafe_url", "no_limits", "too_many_verified", "empty", "extra_field"])
def test_rejects_unsafe_or_overstated_reproductions(tmp_path, change):
    data = json.loads(EDITION.read_text())
    item = data["reproductions"][0]
    if change == "unsafe_url":
        item["source_url"] = "javascript:alert(1)"
    elif change == "no_limits":
        item["limits"] = ""
    elif change == "too_many_verified":
        item["methods_verified"] = 6
    elif change == "empty":
        data["reproductions"] = []
    else:
        item["editorial_status"] = "independently_tested"
    path = tmp_path / "2608.27428.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        apply_lab_reproductions(page(), path)


def test_rejects_a_reproduction_for_another_paper(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(EDITION.read_text())
    with pytest.raises(ValueError, match="different paper"):
        apply_lab_reproductions(page("2608.21223"), path)
