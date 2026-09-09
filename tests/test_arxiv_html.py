from pathlib import Path

import pytest

from radar import arxiv_html
from radar.arxiv_html import HtmlEquation, parse_arxiv_html

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_html_sample.html"


@pytest.fixture
def sample() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parser_yields_one_equation_per_numbered_row_in_document_order(sample):
    equations = parse_arxiv_html(sample)
    assert [e.anchor for e in equations] == ["S3.E1", "S4.E9", "S4.Ex1", "A3.E19"]
    assert [e.position for e in equations] == [1, 2, 3, 4]
    assert [e.label for e in equations] == ["(1)", "(9)", "", "(19)"]


def test_parser_records_section_titles_including_appendices(sample):
    equations = {e.anchor: e for e in parse_arxiv_html(sample)}
    assert equations["S3.E1"].section == "3 Preliminaries"
    assert equations["S4.E9"].section == "4 Methodology"
    assert equations["A3.E19"].section == "Appendix C Proofs"


def test_parser_joins_aligned_cells_and_merges_continuation_rows(sample):
    equations = {e.anchor: e for e in parse_arxiv_html(sample)}
    assert equations["S4.E9"].latex == (
        r"Loss= \operatorname{CE}(S^{F},I) \\ +\operatorname{CE}(S^{I},I)"
    )


def test_parser_strips_only_the_injected_displaystyle_prefix(sample):
    equations = {e.anchor: e for e in parse_arxiv_html(sample)}
    assert equations["S3.E1"].latex == r"F(P;A,U)=0\mathrm{~in~}\Omega"
    assert equations["S4.Ex1"].latex == r"Z_{t-1}=\sqrt{\alpha_{t-1}}Z_{0}"


def test_parser_context_is_the_neighbouring_prose_without_math(sample):
    equations = {e.anchor: e for e in parse_arxiv_html(sample)}
    first = equations["S3.E1"]
    assert first.context_before.endswith("defined by a function as follows:")
    assert first.context_after == "where is a bounded spatial domain."
    assert "\\Omega" not in first.context_after
    assert equations["S4.Ex1"].context_after == ""


def test_inline_math_in_prose_is_never_an_equation(sample):
    anchors = [e.anchor for e in parse_arxiv_html(sample)]
    assert "S3.SS1.p3" not in anchors
    assert len(anchors) == 4


def test_parser_caps_the_number_of_equations(sample, monkeypatch):
    monkeypatch.setattr(arxiv_html, "MAX_EQUATIONS", 2)
    assert len(parse_arxiv_html(sample)) == 2


def test_parser_drops_an_equation_whose_latex_exceeds_the_cap(sample, monkeypatch):
    monkeypatch.setattr(arxiv_html, "MAX_LATEX_CHARS", 30)
    anchors = [e.anchor for e in parse_arxiv_html(sample)]
    assert "S4.E9" not in anchors
    assert "A3.E19" in anchors


def test_a_page_without_equations_yields_nothing():
    assert parse_arxiv_html('<div class="ltx_page_main"><p class="ltx_p">Hi</p></div>') == []


def test_html_equation_is_a_frozen_value():
    equation = HtmlEquation(
        anchor="S1.E1", label="(1)", section="1 Intro", position=1,
        latex="x", mathml="<math></math>", context_before="", context_after="",
    )
    with pytest.raises(Exception):
        equation.anchor = "other"


from radar.arxiv_html import sanitize_math_cells, sanitize_mathml


def test_sanitizer_keeps_allowed_elements_and_unwraps_semantics():
    fragment = (
        '<math id="m1" class="ltx_Math" alttext="x^2" display="inline">'
        '<semantics><msup><mi>x</mi><mn>2</mn></msup>'
        '<annotation encoding="application/x-tex">x^2</annotation></semantics></math>'
    )
    assert sanitize_mathml(fragment) == (
        '<math display="block"><msup><mi>x</mi><mn>2</mn></msup></math>'
    )


def test_sanitizer_drops_scripts_links_styles_and_unknown_elements():
    fragment = (
        '<math><mrow><script>alert(1)</script>'
        '<a href="https://evil.example">x</a>'
        '<mi style="color:red" onclick="x()" href="javascript:1">y</mi>'
        '<menclose notation="box"><mn>1</mn></menclose>'
        '<mstyle mathcolor="red" displaystyle="true"><mo>+</mo></mstyle></mrow></math>'
    )
    out = sanitize_mathml(fragment)
    assert out == (
        '<math display="block"><mrow>x<mi>y</mi><mn>1</mn>'
        '<mstyle displaystyle="true"><mo>+</mo></mstyle></mrow></math>'
    )
    assert "alert" not in out and "href" not in out and ' style="' not in out


def test_sanitizer_validates_attribute_values_and_escapes_text():
    fragment = (
        '<math><mspace width="0.5em"/><mo stretchy="true" lspace="1&quot;bad">&lt;</mo>'
        '<mi mathvariant="bold">q</mi><mtd columnalign="right left"><mn>1</mn></mtd></math>'
    )
    assert sanitize_mathml(fragment) == (
        '<math display="block"><mspace width="0.5em"></mspace>'
        '<mo stretchy="true">&lt;</mo><mi mathvariant="bold">q</mi>'
        '<mtd columnalign="right left"><mn>1</mn></mtd></math>'
    )


def test_sanitizer_returns_empty_for_empty_input():
    assert sanitize_mathml("") == ""
    assert sanitize_mathml("<math><semantics><annotation>x</annotation></semantics></math>") == ""


def test_cells_of_one_row_merge_into_a_single_block():
    cells = [
        "<math><semantics><mrow><mi>L</mi><mo>=</mo></mrow></semantics></math>",
        "<math><mrow><mn>1</mn></mrow></math>",
    ]
    assert sanitize_math_cells(cells) == (
        '<math display="block"><mrow><mrow><mi>L</mi><mo>=</mo></mrow>'
        '<mrow><mn>1</mn></mrow></mrow></math>'
    )
    assert sanitize_math_cells(cells[:1]) == (
        '<math display="block"><mrow><mi>L</mi><mo>=</mo></mrow></math>'
    )


def test_parsed_equations_carry_sanitized_mathml(sample):
    equations = {e.anchor: e for e in parse_arxiv_html(sample)}
    first = equations["S3.E1"].mathml
    assert first.startswith('<math display="block">')
    assert '<mi mathvariant="normal">Ω</mi>' in first
    assert "annotation" not in first and 'id="' not in first and "alttext" not in first
    loss = equations["S4.E9"].mathml
    assert loss.count('<math display="block">') == 2
    assert "<mi>CE</mi>" in loss
