import json
from pathlib import Path

import pytest

from radar.equation_editions import EquationEdition, apply_equation_edition
from radar.public_research import ResearchPage
from radar.site import render_research_page

ROOT = Path(__file__).resolve().parents[1]
EDITION = ROOT / "content/equations/2608.21223.json"


def page():
    return ResearchPage.model_validate_json(
        (ROOT / "site/papers/2608.21223/index.json").read_text())


def test_pinned_equations_render_explanations_without_promoting_paper_status():
    original = page()
    result = apply_equation_edition(original, EDITION)
    assert result.editorial_status == original.editorial_status == "indexed"
    assert result.report_available is False
    assert result.claims == original.claims
    assert result.exposure_map == original.exposure_map
    assert [e.anchor for e in result.equations] == ["S4.E3", "S5.E6"]
    assert result.equations[0].latex == r"x\cdot(\theta\pm\epsilon z_{i})=x\cdot\theta\pm x\cdot\epsilon z_{i}."
    html = render_research_page(result)
    assert html.count('<math display="block">') == 2
    assert 'class="research-signal"' not in html
    assert 'class="research-signal-note"' in html
    assert "Find the energy break-even point" in html
    assert '<var>e</var><sub>PGU-XOR</sub>' in html
    assert "post-layout IPZO simulation with estimated EPZO energy" in html
    assert 'href="https://arxiv.org/html/2608.21223v1#S5.SS4.SSS2"' in html


@pytest.mark.parametrize("change", ["markup", "wrong_source", "different_version", "duplicate"])
def test_edition_rejects_unsafe_markup_or_broken_source_relationships(change):
    data = json.loads(EDITION.read_text())
    if change == "markup":
        data["equations"][0]["mathml"] = '<math display="block"><mi onclick="alert(1)">x</mi></math>'
    elif change == "wrong_source":
        data["arxiv_id"] = "2608.99999"
    elif change == "different_version":
        data["equations"][0]["evidence_url"] = "https://arxiv.org/html/2608.21223v2#S4"
    else:
        data["equations"] = [data["equations"][0], data["equations"][0]]
    with pytest.raises(ValueError):
        EquationEdition.model_validate(data)


def test_missing_edition_preserves_existing_equations(tmp_path):
    original = page()
    assert apply_equation_edition(original, tmp_path / "missing.json") is original


def test_edition_cannot_be_applied_to_another_paper():
    other = page().model_copy(update={"arxiv_id": "2608.99999"})
    with pytest.raises(ValueError, match="different paper"):
        apply_equation_edition(other, EDITION)
