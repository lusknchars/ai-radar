# Equations on Research Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show up to three central equations of every indexed paper on its research page as natively rendered MathML taken from arXiv's HTML, typeset with a vendored math font, with explicit English absence states and no outbound formula links.

**Architecture:** A new `arxiv_html.py` fetches, parses, and sanitizes arXiv's LaTeXML HTML into equations. A new `equations.py` runs the daily collection step (parse, select with the existing K2.6 formula selector, store) into two new SQLite tables. `site_data` exposes the selected equations on each `Ponto`, `public_research` publishes them in the page model and JSON, `site.py` renders one new section, and `site_assets.py` owns the math typography.

**Tech Stack:** Python 3.12 standard library (`html.parser`, `sqlite3`, `hashlib`), Pydantic v2, pytest, the existing Kimi adapter. No new dependency, no client-side math library, no remote asset.

**Spec:** `docs/plans/2026-09-08-equations-on-research-pages.md`

## Global Constraints

- Python `>=3.12`; dependencies stay `httpx`, `anthropic`, `pydantic`, `pypdf`, `python-dotenv`; dev adds nothing beyond `pytest`.
- The test suite runs offline and stays fast; no test touches the network.
- No page makes a remote font, script, or CDN request. The math font lives in `assets/fonts/` and is copied by `publish_site`.
- No equation links to arXiv. The only arXiv link on a research page stays the existing "Read original paper".
- All new user-facing copy is English. Test names may follow either language convention already present in the suite.
- Existing invariants hold: the daily run cannot fail because of an equation fetch or selection error; `dry_run` leaves no durable state.
- Commit after every task with the repo's `feat:`/`test:`/`docs:` prefixes and the session trailer:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01ExvV1mBMYmDQZXxMofSsPS
  ```
- Run `python3 -m pytest -q` before every commit; all tests must pass.

## File Structure

| File | Responsibility |
|---|---|
| `src/radar/arxiv_html.py` (new) | Fetch status, LaTeXML parsing into `HtmlEquation`, MathML sanitizer |
| `src/radar/equations.py` (new) | Daily collection step: candidates, selection, statuses, storing |
| `src/radar/site_data.py` | `EquationView` value and the two new `Ponto` fields |
| `src/radar/store.py` | Two tables and four methods; `site_data` attaches equations |
| `src/radar/formulas.py` | `label` and `section` on `FormulaCandidate` |
| `src/radar/judge.py` | Selector prompt carries `label` and `section` |
| `src/radar/public_labels.py` | `CORE_KIND_PHRASES` for the absence copy |
| `src/radar/public_research.py` | `ResearchEquation`, page fields, invariant |
| `src/radar/site.py` | Equations section, jump link, math font style hook |
| `src/radar/site_assets.py` | `math_font_face()` and equation CSS |
| `src/radar/publish.py` | Copies `assets/fonts/*.woff2` |
| `src/radar/cli.py` | Daily step after judging |
| `scripts/backfill_equations.py` (new) | One-off and repair runs |
| `assets/fonts/stix-two-math.woff2`, `assets/fonts/STIXTwoMath-OFL.txt` (new) | Vendored font and license |
| `tests/fixtures/arxiv_html_sample.html` (new) | Trimmed real LaTeXML excerpt |
| `tests/test_arxiv_html.py`, `tests/test_equations.py` (new) | Parser, sanitizer, fetch, collection |
| `tests/test_store.py`, `tests/test_formulas.py`, `tests/test_judge.py`, `tests/test_public_research.py`, `tests/test_site.py`, `tests/test_site_assets.py`, `tests/test_publish.py`, `tests/test_cli.py` | Extended |
| `README.md`, `CONTEXT.md` | Documentation |

---

### Task 1: LaTeXML fixture and equation parser

**Files:**
- Create: `tests/fixtures/arxiv_html_sample.html`
- Create: `src/radar/arxiv_html.py`
- Test: `tests/test_arxiv_html.py`

**Interfaces:**
- Produces: `HtmlEquation(anchor, label, section, position, latex, mathml, context_before, context_after)` frozen dataclass; `parse_arxiv_html(text: str) -> list[HtmlEquation]`; constants `MAX_EQUATIONS = 100`, `MAX_LATEX_CHARS = 6000`, `MAX_MATHML_CHARS = 20_000`, `CONTEXT_CHARS = 900`, `LATEXML_MARKER = 'class="ltx_page_main"'`.
- Consumes: nothing. Task 2 adds the sanitizer this task calls; until then `mathml` is produced by a stub defined here and replaced in Task 2.

- [ ] **Step 1: Write the fixture**

Create `tests/fixtures/arxiv_html_sample.html` with this content. It mirrors real LaTeXML markup: a numbered single-row group, a two-cell aligned row with a continuation row sharing the number, an unnumbered single equation table, inline math inside prose, a heading with a tag span, and an appendix equation. Keep it exactly as written so the assertions below hold.

```html
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Sample</title></head>
<body>
<div class="ltx_page_main">
<article class="ltx_document">
<section id="S3" class="ltx_section">
<h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">3 </span>Preliminaries</h2>
<div id="S3.SS1.p3" class="ltx_para">
<p id="S3.SS1.p3.2" class="ltx_p">Static systems are governed by time-independent coefficients. They are typically defined by a function as follows:</p>
<table id="S3.E1" class="ltx_equationgroup ltx_eqn_table">
<tbody><tr id="S3.E1X" class="ltx_equation ltx_eqn_row ltx_align_baseline">
<td class="ltx_eqn_cell ltx_eqn_center_padleft"></td>
<td class="ltx_td ltx_align_right ltx_eqn_cell"><math id="S3.E1.m1" class="ltx_Math" alttext="\displaystyle F(P;A,U)=0\mathrm{~in~}\Omega" display="inline"><semantics><mrow><mi>F</mi><mo>(</mo><mi>P</mi><mo>;</mo><mi>A</mi><mo>,</mo><mi>U</mi><mo>)</mo><mo>=</mo><mn>0</mn><mspace width="0.5em"/><mi mathvariant="normal">in</mi><mi mathvariant="normal">&#937;</mi></mrow><annotation encoding="application/x-tex">F(P;A,U)=0</annotation></semantics></math></td>
<td class="ltx_eqn_cell ltx_eqn_center_padright"></td>
<td rowspan="1" class="ltx_eqn_cell ltx_eqn_eqno ltx_align_middle ltx_align_right"><span class="ltx_tag ltx_tag_equationgroup ltx_align_right">(1)</span></td></tr></tbody>
</table>
<p id="S3.SS1.p3.3" class="ltx_p">where <math id="S3.SS1.p3.m1" class="ltx_Math" alttext="\Omega" display="inline"><semantics><mi mathvariant="normal">&#937;</mi><annotation encoding="application/x-tex">\Omega</annotation></semantics></math> is a bounded spatial domain.</p>
</div>
</section>
<section id="S4" class="ltx_section">
<h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">4 </span>Methodology</h2>
<div id="S4.SS2.p7" class="ltx_para">
<p id="S4.SS2.p7.3" class="ltx_p">The loss function can be expressed as follows:</p>
<table id="S4.E9" class="ltx_equationgroup ltx_eqn_table">
<tbody><tr id="S4.E9X" class="ltx_equation ltx_eqn_row ltx_align_baseline">
<td class="ltx_eqn_cell ltx_eqn_center_padleft"></td>
<td class="ltx_td ltx_align_right ltx_eqn_cell"><math id="S4.E9.m1" class="ltx_Math" alttext="\displaystyle Loss=" display="inline"><semantics><mrow><mi>L</mi><mi>o</mi><mi>s</mi><mi>s</mi><mo>=</mo></mrow></semantics></math></td>
<td class="ltx_td ltx_align_left ltx_eqn_cell"><math id="S4.E9.m2" class="ltx_Math" alttext="\displaystyle\operatorname{CE}(S^{F},I)" display="inline"><semantics><mrow><mi>CE</mi><mo>(</mo><msup><mi>S</mi><mi>F</mi></msup><mo>,</mo><mi>I</mi><mo>)</mo></mrow></semantics></math></td>
<td class="ltx_eqn_cell ltx_eqn_center_padright"></td>
<td rowspan="2" class="ltx_eqn_cell ltx_eqn_eqno ltx_align_middle ltx_align_right"><span class="ltx_tag ltx_tag_equationgroup ltx_align_right">(9)</span></td></tr>
<tr id="S4.E9Xa" class="ltx_equation ltx_eqn_row ltx_align_baseline">
<td class="ltx_eqn_cell ltx_eqn_center_padleft"></td>
<td class="ltx_td ltx_align_right ltx_eqn_cell"></td>
<td class="ltx_td ltx_align_left ltx_eqn_cell"><math id="S4.E9.m3" class="ltx_Math" alttext="\displaystyle+\operatorname{CE}(S^{I},I)" display="inline"><semantics><mrow><mo>+</mo><mi>CE</mi><mo>(</mo><msup><mi>S</mi><mi>I</mi></msup><mo>,</mo><mi>I</mi><mo>)</mo></mrow></semantics></math></td>
<td class="ltx_eqn_cell ltx_eqn_center_padright"></td></tr></tbody>
</table>
<p id="S4.SS2.p7.4" class="ltx_p">where CE is the cross-entropy loss function.</p>
</div>
<div id="S4.SS3.p1" class="ltx_para">
<p id="S4.SS3.p1.1" class="ltx_p">The unnumbered update reads:</p>
<table id="S4.Ex1" class="ltx_equation ltx_eqn_table">
<tbody><tr class="ltx_equation ltx_eqn_row ltx_align_baseline">
<td class="ltx_eqn_cell ltx_eqn_center_padleft"></td>
<td class="ltx_eqn_cell ltx_align_center"><math id="S4.Ex1.m1" class="ltx_Math" alttext="\displaystyle Z_{t-1}=\sqrt{\alpha_{t-1}}Z_{0}" display="inline"><semantics><mrow><msub><mi>Z</mi><mrow><mi>t</mi><mo>&#8722;</mo><mn>1</mn></mrow></msub><mo>=</mo><msqrt><msub><mi>&#945;</mi><mrow><mi>t</mi><mo>&#8722;</mo><mn>1</mn></mrow></msub></msqrt><msub><mi>Z</mi><mn>0</mn></msub></mrow></semantics></math></td>
<td class="ltx_eqn_cell ltx_eqn_center_padright"></td></tr></tbody>
</table>
</div>
</section>
<section id="A3" class="ltx_appendix">
<h2 class="ltx_title ltx_title_appendix"><span class="ltx_tag ltx_tag_appendix">Appendix C </span>Proofs</h2>
<div id="A3.p1" class="ltx_para">
<p id="A3.p1.1" class="ltx_p">This yields the following approximation:</p>
<table id="A3.E19" class="ltx_equationgroup ltx_eqn_table">
<tbody><tr id="A3.E19X" class="ltx_equation ltx_eqn_row ltx_align_baseline">
<td class="ltx_eqn_cell ltx_eqn_center_padleft"></td>
<td class="ltx_td ltx_align_right ltx_eqn_cell"><math id="A3.E19.m1" class="ltx_Math" alttext="\displaystyle\mathbf{q}(\mathbf{x}_{l})" display="inline"><semantics><mrow><mi mathvariant="bold">q</mi><mo>(</mo><msub><mi mathvariant="bold">x</mi><mi>l</mi></msub><mo>)</mo></mrow></semantics></math></td>
<td class="ltx_eqn_cell ltx_eqn_center_padright"></td>
<td rowspan="1" class="ltx_eqn_cell ltx_eqn_eqno ltx_align_middle ltx_align_right"><span class="ltx_tag ltx_tag_equationgroup ltx_align_right">(19)</span></td></tr></tbody>
</table>
</div>
</section>
</article>
</div>
</body></html>
```

- [ ] **Step 2: Write the failing parser tests**

Create `tests/test_arxiv_html.py`:

```python
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
    monkeypatch.setattr(arxiv_html, "MAX_LATEX_CHARS", 20)
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_arxiv_html.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'radar.arxiv_html'`

- [ ] **Step 4: Write the parser**

Create `src/radar/arxiv_html.py`:

```python
"""arXiv HTML (LaTeXML) as a source of equations for research pages.

The module owns three things: fetch status for the unversioned HTML page,
parsing of LaTeXML markup into equations with their number, section, LaTeX,
and neighbouring prose, and a MathML sanitizer that rebuilds every equation
from an allowlist before it can reach a page. Nothing here calls a model.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from typing import Literal

LATEXML_MARKER = 'class="ltx_page_main"'
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_EQUATIONS = 100
MAX_LATEX_CHARS = 6000
MAX_MATHML_CHARS = 20_000
CONTEXT_CHARS = 900

_ROW_SUFFIX = re.compile(r"X[a-z]*$")
_DISPLAYSTYLE = re.compile(r"^\s*\\displaystyle(?![A-Za-z])\s*")
HtmlStatus = Literal["available", "unavailable", "rejected"]


@dataclass(frozen=True)
class HtmlEquation:
    anchor: str
    label: str
    section: str
    position: int
    latex: str
    mathml: str
    context_before: str
    context_after: str


@dataclass(frozen=True)
class HtmlFetch:
    status: HtmlStatus
    text: str = ""
    sha256: str = ""


def _collapse(parts: list[str]) -> str:
    return " ".join("".join(parts).split())


def _classes(attrs: dict[str, str | None]) -> set[str]:
    return set((attrs.get("class") or "").split())


class _LatexmlParser(HTMLParser):
    """One pass over the page. Raw MathML is buffered for the sanitizer."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._section = ""
        self._heading: list[str] | None = None
        self._heading_tag = ""
        self._div_depth = 0
        self._para_depth: int | None = None
        self._paragraph: list[str] | None = None
        self._last_paragraph = ""
        self._pending_after: list[dict] = []
        self._table_id = ""
        self._row: dict | None = None
        self._math: list[str] | None = None
        self._math_depth = 0
        self._math_alttext = ""
        self._tag: list[str] | None = None

    # -- tags ---------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if self._math is not None:
            self._math.append(self.get_starttag_text() or "")
            self._math_depth += 1
            return
        classes = _classes(attributes)
        if tag == "math":
            self._math = [self.get_starttag_text() or ""]
            self._math_depth = 1
            self._math_alttext = attributes.get("alttext") or ""
            return
        if tag == "div":
            self._div_depth += 1
            if "ltx_para" in classes:
                self._para_depth = self._div_depth
                self._last_paragraph = ""
                self._pending_after = []
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and (
                "ltx_title_section" in classes or "ltx_title_appendix" in classes):
            self._heading = []
            self._heading_tag = tag
            return
        if tag == "p" and "ltx_p" in classes:
            self._paragraph = []
            return
        if tag == "table" and ("ltx_equation" in classes or "ltx_equationgroup" in classes):
            self._table_id = attributes.get("id") or ""
            return
        if tag == "tr" and "ltx_equation" in classes and "ltx_eqn_row" in classes:
            self._row = {"id": attributes.get("id") or "", "cells": [],
                         "latex": [], "label": ""}
            return
        if tag == "span" and self._row is not None and (
                "ltx_tag_equation" in classes or "ltx_tag_equationgroup" in classes):
            self._tag = []

    def handle_startendtag(self, tag: str, attrs) -> None:
        if self._math is not None:
            self._math.append(self.get_starttag_text() or "")
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._math is not None:
            self._math_depth -= 1
            self._math.append(f"</{tag}>")
            if self._math_depth == 0:
                markup = "".join(self._math)
                self._math = None
                if self._row is not None:
                    self._row["cells"].append(markup)
                    self._row["latex"].append(self._math_alttext)
            return
        if tag == "div":
            if self._para_depth == self._div_depth:
                self._para_depth = None
                self._pending_after = []
            self._div_depth -= 1
            return
        if self._heading is not None and tag == self._heading_tag:
            self._section = _collapse(self._heading)
            self._heading = None
            return
        if tag == "p" and self._paragraph is not None:
            text = _collapse(self._paragraph)
            self._paragraph = None
            self._last_paragraph = text
            for row in self._pending_after:
                row["context_after"] = text[:CONTEXT_CHARS]
            self._pending_after = []
            return
        if tag == "span" and self._tag is not None and self._row is not None:
            self._row["label"] = _collapse(self._tag)
            self._tag = None
            return
        if tag == "tr" and self._row is not None:
            self._finish_row()
            return
        if tag == "table":
            self._table_id = ""

    def handle_data(self, data: str) -> None:
        if self._math is not None:
            self._math.append(escape(data, quote=False))
        elif self._tag is not None:
            self._tag.append(data)
        elif self._heading is not None:
            self._heading.append(data)
        elif self._paragraph is not None:
            self._paragraph.append(data)

    # -- rows ---------------------------------------------------------------
    def _finish_row(self) -> None:
        row, self._row = self._row, None
        if not row["cells"]:
            return
        anchor = _ROW_SUFFIX.sub("", row["id"]) if row["id"] else self._table_id
        latex = " ".join(_DISPLAYSTYLE.sub("", cell) for cell in row["latex"]).strip()
        previous = self.rows[-1] if self.rows else None
        if previous is not None and previous["anchor"] == anchor and not row["label"]:
            previous["latex"] = f"{previous['latex']} \\\\ {latex}"
            previous["cell_rows"].append(row["cells"])
            return
        equation = {
            "anchor": anchor, "label": row["label"], "section": self._section,
            "latex": latex, "cell_rows": [row["cells"]],
            "context_before": self._last_paragraph[-CONTEXT_CHARS:],
            "context_after": "",
        }
        self.rows.append(equation)
        self._pending_after.append(equation)


def _render_cell_rows(cell_rows: list[list[str]]) -> str:
    # Replaced by the sanitizer in Task 2; kept here so Task 1 stands alone.
    return "".join(
        '<math display="block">' + "".join(cells) + "</math>" for cells in cell_rows
    )


def parse_arxiv_html(text: str) -> list[HtmlEquation]:
    """Return display equations in document order, capped and size-checked."""
    parser = _LatexmlParser()
    parser.feed(text)
    parser.close()
    equations: list[HtmlEquation] = []
    for row in parser.rows:
        if not row["latex"] or len(row["latex"]) > MAX_LATEX_CHARS:
            continue
        mathml = _render_cell_rows(row["cell_rows"])
        if not mathml or len(mathml) > MAX_MATHML_CHARS:
            continue
        equations.append(HtmlEquation(
            anchor=row["anchor"], label=row["label"], section=row["section"],
            position=len(equations) + 1, latex=row["latex"], mathml=mathml,
            context_before=row["context_before"],
            context_after=row["context_after"],
        ))
        if len(equations) >= MAX_EQUATIONS:
            break
    return equations
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_arxiv_html.py -q`
Expected: 10 passed

- [ ] **Step 6: Run the whole suite and commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add tests/fixtures/arxiv_html_sample.html tests/test_arxiv_html.py src/radar/arxiv_html.py
git commit -m "feat: parse arXiv HTML equations with number, section and prose"
```

---

### Task 2: MathML sanitizer

**Files:**
- Modify: `src/radar/arxiv_html.py` (replace `_render_cell_rows`)
- Test: `tests/test_arxiv_html.py`

**Interfaces:**
- Produces: `sanitize_mathml(fragment: str) -> str` returning `<math display="block">…</math>` or `""`; `sanitize_math_cells(fragments: list[str]) -> str` merging several cells into one block.
- Consumes: `_LatexmlParser` row buffers from Task 1.

- [ ] **Step 1: Write the failing sanitizer tests**

Append to `tests/test_arxiv_html.py`:

```python
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
        '<math display="block"><mrow>alert(1)x<mi>y</mi><mn>1</mn>'
        '<mstyle displaystyle="true"><mo>+</mo></mstyle></mrow></math>'
    )
    assert "script" not in out and "href" not in out and "style=" not in out


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


def test_sanitizer_returns_empty_for_empty_or_oversized_input(monkeypatch):
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
    assert "<mi mathvariant=\"normal\">Ω</mi>" in first
    assert "annotation" not in first and 'id="' not in first and "alttext" not in first
    loss = equations["S4.E9"].mathml
    assert loss.count('<math display="block">') == 2
    assert "<mi>CE</mi>" in loss
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_arxiv_html.py -q`
Expected: FAIL with `ImportError: cannot import name 'sanitize_math_cells'`

- [ ] **Step 3: Write the sanitizer and wire it into the parser**

In `src/radar/arxiv_html.py`, replace the `_render_cell_rows` function with:

```python
_ALLOWED_ELEMENTS = frozenset({
    "math", "mrow", "mi", "mn", "mo", "mtext", "mspace", "ms", "msup", "msub",
    "msubsup", "mfrac", "msqrt", "mroot", "mover", "munder", "munderover",
    "mtable", "mtr", "mtd", "mstyle", "mpadded", "mphantom",
})
_DROPPED_ELEMENTS = frozenset({"annotation", "annotation-xml", "script", "style"})
_ALLOWED_ATTRIBUTES = frozenset({
    "mathvariant", "stretchy", "fence", "separator", "largeop", "movablelimits",
    "symmetric", "lspace", "rspace", "minsize", "maxsize", "form", "accent",
    "accentunder", "displaystyle", "scriptlevel", "linethickness",
    "columnalign", "rowalign", "columnspacing", "rowspacing", "width",
    "height", "depth", "voffset",
})
_ATTRIBUTE_VALUE = re.compile(r"^[A-Za-z0-9.%+\- ]{1,40}$")


class _MathTree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: list = []
        self._stack: list = []

    def _children(self) -> list:
        return self._stack[-1][2] if self._stack else self.root

    def handle_starttag(self, tag: str, attrs) -> None:
        node = [tag.lower(), dict(attrs), []]
        self._children().append(node)
        self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._children().append([tag.lower(), dict(attrs), []])

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        while self._stack:
            node = self._stack.pop()
            if node[0] == tag:
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._children().append(data)


def _serialize(nodes: list) -> str:
    out: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            out.append(escape(node, quote=False))
            continue
        tag, attrs, children = node
        if tag in _DROPPED_ELEMENTS:
            continue
        if tag not in _ALLOWED_ELEMENTS or tag == "math":
            out.append(_serialize(children))
            continue
        kept = "".join(
            f' {name}="{escape(value, quote=True)}"'
            for name, value in attrs.items()
            if name in _ALLOWED_ATTRIBUTES and value is not None
            and _ATTRIBUTE_VALUE.fullmatch(value)
        )
        out.append(f"<{tag}{kept}>{_serialize(children)}</{tag}>")
    return "".join(out)


def _sanitized_inner(fragment: str) -> str:
    tree = _MathTree()
    tree.feed(fragment)
    tree.close()
    return _serialize(tree.root)


def sanitize_mathml(fragment: str) -> str:
    """Rebuild one equation from the allowlist; the input never reaches a page."""
    inner = _sanitized_inner(fragment)
    return f'<math display="block">{inner}</math>' if inner else ""


def sanitize_math_cells(fragments: list[str]) -> str:
    """Join the cells LaTeXML splits an aligned row into as one block."""
    if len(fragments) == 1:
        return sanitize_mathml(fragments[0])
    inner = "".join(_sanitized_inner(fragment) for fragment in fragments)
    return f'<math display="block"><mrow>{inner}</mrow></math>' if inner else ""


def _render_cell_rows(cell_rows: list[list[str]]) -> str:
    return "".join(sanitize_math_cells(cells) for cells in cell_rows)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_arxiv_html.py -q`
Expected: 16 passed

- [ ] **Step 5: Run the whole suite and commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add tests/test_arxiv_html.py src/radar/arxiv_html.py
git commit -m "feat: sanitize arXiv MathML against an element and attribute allowlist"
```

---

### Task 3: HTML fetch with statuses

**Files:**
- Modify: `src/radar/arxiv_html.py`
- Test: `tests/test_arxiv_html.py`

**Interfaces:**
- Produces: `fetch_arxiv_html(arxiv_id: str, *, get) -> HtmlFetch`; `get` has the `httpx.get` signature (`get(url, headers=..., timeout=..., follow_redirects=...)`) and returns an object with `status_code`, `content`, `text`, and `raise_for_status()`.
- Consumes: `HtmlFetch`, `LATEXML_MARKER`, `MAX_HTML_BYTES` from Task 1.

- [ ] **Step 1: Write the failing fetch tests**

Append to `tests/test_arxiv_html.py`:

```python
import hashlib

from radar.arxiv_html import fetch_arxiv_html


class _Response:
    status_code = 200

    def __init__(self, body: bytes) -> None:
        self.content = body
        self.text = body.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_returns_the_page_and_its_hash(sample):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(sample.encode("utf-8"))

    fetched = fetch_arxiv_html("2605.13790", get=get)
    assert fetched.status == "available"
    assert fetched.text == sample
    assert fetched.sha256 == hashlib.sha256(sample.encode("utf-8")).hexdigest()
    assert calls[0][0] == "https://arxiv.org/html/2605.13790"
    assert calls[0][1]["headers"]["User-Agent"].startswith("ai-radar/")
    assert calls[0][1]["follow_redirects"] is True


def test_fetch_marks_a_missing_rendering_as_unavailable():
    class Missing(_Response):
        status_code = 404

    fetched = fetch_arxiv_html("2608.24070", get=lambda url, **kw: Missing(b"no"))
    assert fetched == arxiv_html.HtmlFetch(status="unavailable")


def test_fetch_rejects_an_oversized_or_non_latexml_body(monkeypatch):
    monkeypatch.setattr(arxiv_html, "MAX_HTML_BYTES", 10)
    big = fetch_arxiv_html("2605.13790", get=lambda url, **kw: _Response(b"x" * 11))
    assert big.status == "rejected"
    monkeypatch.setattr(arxiv_html, "MAX_HTML_BYTES", 1000)
    plain = fetch_arxiv_html("2605.13790", get=lambda url, **kw: _Response(b"<html>hi</html>"))
    assert plain.status == "rejected"


def test_fetch_raises_on_other_http_errors():
    class Broken(_Response):
        status_code = 503

    with pytest.raises(RuntimeError):
        fetch_arxiv_html("2605.13790", get=lambda url, **kw: Broken(b""))


def test_fetch_rejects_a_versioned_or_malformed_id():
    with pytest.raises(ValueError):
        fetch_arxiv_html("2605.13790v1", get=lambda url, **kw: _Response(b""))
    with pytest.raises(ValueError):
        fetch_arxiv_html("../etc", get=lambda url, **kw: _Response(b""))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_arxiv_html.py -q`
Expected: FAIL with `ImportError: cannot import name 'fetch_arxiv_html'`

- [ ] **Step 3: Write the fetch function**

Add to `src/radar/arxiv_html.py`, after the dataclasses:

```python
_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}$")
USER_AGENT = "ai-radar/0.1 (research page equations)"


def fetch_arxiv_html(arxiv_id: str, *, get) -> HtmlFetch:
    """Fetch the unversioned HTML rendering: latest version at fetch time."""
    if not _ARXIV_ID.fullmatch(arxiv_id):
        raise ValueError(f"arxiv_id invalido para download: {arxiv_id!r}")
    response = get(
        f"https://arxiv.org/html/{arxiv_id}",
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
        follow_redirects=True,
    )
    if getattr(response, "status_code", 200) == 404:
        return HtmlFetch(status="unavailable")
    response.raise_for_status()
    content = response.content
    if len(content) > MAX_HTML_BYTES or LATEXML_MARKER not in response.text:
        return HtmlFetch(status="rejected")
    return HtmlFetch(
        status="available", text=response.text,
        sha256=hashlib.sha256(content).hexdigest(),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_arxiv_html.py -q`
Expected: 21 passed

- [ ] **Step 5: Run the whole suite and commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add tests/test_arxiv_html.py src/radar/arxiv_html.py
git commit -m "feat: fetch arXiv HTML with explicit availability statuses"
```

---

### Task 4: Equation value and store tables

**Files:**
- Modify: `src/radar/site_data.py:12-34` (add `EquationView`, two `Ponto` fields)
- Modify: `src/radar/store.py:27-83` (SCHEMA) and `src/radar/store.py:293-386` (`site_data`), plus new methods after `papers_por_familia`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `EquationView(anchor, label, section, role, latex, mathml, context)` frozen dataclass in `site_data.py`; `Ponto.equations: tuple[EquationView, ...] = ()`; `Ponto.equations_status: str = "not_fetched"`; `Ponto.equations_fetched_at: str = ""`; `Store.record_equations(arxiv_id, *, fetched_at, status, html_sha256, core_kind, selector_model, equations)`; `Store.equations_for(arxiv_id) -> list[EquationView]`; `Store.equation_source(arxiv_id) -> dict | None`; `Store.papers_without_equations() -> list[Paper]`.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing store tests**

Append to `tests/test_store.py`:

```python
from radar.site_data import EquationView


def _equation(anchor="S4.E9", role="loss") -> EquationView:
    return EquationView(
        anchor=anchor, label="(9)", section="4 Methodology", role=role,
        latex=r"Loss=\operatorname{CE}(S^{F},I)",
        mathml='<math display="block"><mi>L</mi></math>',
        context="The loss function can be expressed as follows:",
    )


def test_recording_equations_stores_source_and_rows(store):
    store.upsert_paper(P, seen_at="2026-09-08", scope="teste")
    store.record_equations(
        P.arxiv_id, fetched_at="2026-09-08", status="selected",
        html_sha256="c" * 64, core_kind="formula", selector_model="kimi-k2.6",
        equations=[_equation(), _equation(anchor="S3.E1", role="baseline")],
    )
    source = store.equation_source(P.arxiv_id)
    assert source["status"] == "selected"
    assert source["equation_count"] == 2
    assert source["core_kind"] == "formula"
    rows = store.equations_for(P.arxiv_id)
    assert [e.anchor for e in rows] == ["S4.E9", "S3.E1"]
    assert rows[0] == _equation()


def test_recording_again_replaces_previous_rows(store):
    store.upsert_paper(P, seen_at="2026-09-08", scope="teste")
    store.record_equations(
        P.arxiv_id, fetched_at="2026-09-08", status="selected",
        html_sha256="c" * 64, core_kind="formula", selector_model="kimi-k2.6",
        equations=[_equation()],
    )
    store.record_equations(
        P.arxiv_id, fetched_at="2026-09-09", status="unavailable",
        html_sha256=None, core_kind=None, selector_model=None, equations=[],
    )
    assert store.equations_for(P.arxiv_id) == []
    assert store.equation_source(P.arxiv_id)["status"] == "unavailable"
    assert store.equation_source(P.arxiv_id)["fetched_at"] == "2026-09-09"


def test_papers_without_equations_lists_only_unfetched_papers(store):
    other = Paper(arxiv_id="2508.22222", title="U", abstract="A", authors=["B"],
                  categories=["cs.LG"], published="2026-08-21")
    store.upsert_paper(P, seen_at="2026-09-08", scope="teste")
    store.upsert_paper(other, seen_at="2026-09-08", scope="teste")
    store.record_equations(
        P.arxiv_id, fetched_at="2026-09-08", status="no_equations",
        html_sha256="c" * 64, core_kind=None, selector_model=None, equations=[],
    )
    assert store.papers_without_equations() == [other]
    assert store.equation_source("2508.22222") is None
    assert store.equations_for("2508.22222") == []


def test_site_data_attaches_selected_equations_to_each_point(store):
    from datetime import date

    from radar.models import Judgment, Signal
    store.upsert_paper(P, seen_at="2026-09-08", scope="teste")
    store.record_judgment(
        P.arxiv_id,
        Judgment(technique="T", familia="cache_kv", pratica="testar",
                 ganho_eixo="nenhum", ganho_fator=None, ganho_texto="",
                 resumo="R", porque="P"),
        model="kimi-k3", judged_at="2026-09-08")
    store.record_signal(
        P.arxiv_id,
        Signal(total_impls=1, independent_impls=1, velocity_14d=0,
               stars_total=0, citations=None),
        score=0.5, checked_at="2026-09-08")
    ponto = store.site_data(date(2026, 9, 8)).pontos[0]
    assert ponto.equations == () and ponto.equations_status == "not_fetched"
    store.record_equations(
        P.arxiv_id, fetched_at="2026-09-08", status="selected",
        html_sha256="c" * 64, core_kind="formula", selector_model="kimi-k2.6",
        equations=[_equation()])
    ponto = store.site_data(date(2026, 9, 8)).pontos[0]
    assert ponto.equations == (_equation(),)
    assert ponto.equations_status == "selected"
    assert ponto.equations_fetched_at == "2026-09-08"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_store.py -q`
Expected: FAIL with `ImportError: cannot import name 'EquationView'`

- [ ] **Step 3: Add the value type and `Ponto` fields**

In `src/radar/site_data.py`, insert before `class Ponto`:

```python
@dataclass(frozen=True)
class EquationView:
    """One selected equation as the page draws it. MathML is already sanitized."""
    anchor: str
    label: str
    section: str
    role: str
    latex: str
    mathml: str
    context: str
```

Add these three fields at the end of `Ponto`, after `porque: str = ""`:

```python
    # Equacoes centrais vindas do HTML do arXiv. `not_fetched` significa que
    # o passo nunca rodou para este paper; a pagina diz isso em vez de omitir.
    equations: tuple[EquationView, ...] = ()
    equations_status: str = "not_fetched"
    equations_fetched_at: str = ""
```

- [ ] **Step 4: Add the tables and methods to the store**

In `src/radar/store.py`, append to the `SCHEMA` string before its closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS equation_sources (
    arxiv_id       TEXT PRIMARY KEY REFERENCES papers(arxiv_id),
    fetched_at     TEXT NOT NULL,
    status         TEXT NOT NULL,
    html_sha256    TEXT,
    core_kind      TEXT,
    selector_model TEXT,
    equation_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS equations (
    arxiv_id   TEXT NOT NULL REFERENCES papers(arxiv_id),
    anchor     TEXT NOT NULL,
    position   INTEGER NOT NULL,
    label      TEXT NOT NULL,
    section    TEXT NOT NULL,
    role       TEXT NOT NULL,
    latex      TEXT NOT NULL,
    mathml     TEXT NOT NULL,
    context    TEXT NOT NULL,
    PRIMARY KEY (arxiv_id, anchor)
);
```

Add these methods after `papers_por_familia` (before `site_data`):

```python
    # ---------- equations ----------

    def record_equations(
        self, arxiv_id: str, *, fetched_at: str, status: str,
        html_sha256: str | None, core_kind: str | None,
        selector_model: str | None, equations,
    ) -> None:
        """Substitui o resultado anterior do paper: um paper tem um estado so."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM equations WHERE arxiv_id = ?", (arxiv_id,))
            self._conn.execute("""
                INSERT INTO equation_sources
                    (arxiv_id, fetched_at, status, html_sha256, core_kind,
                     selector_model, equation_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(arxiv_id) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    status = excluded.status,
                    html_sha256 = excluded.html_sha256,
                    core_kind = excluded.core_kind,
                    selector_model = excluded.selector_model,
                    equation_count = excluded.equation_count
            """, (arxiv_id, fetched_at, status, html_sha256, core_kind,
                  selector_model, len(equations)))
            self._conn.executemany("""
                INSERT INTO equations
                    (arxiv_id, anchor, position, label, section, role,
                     latex, mathml, context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (arxiv_id, e.anchor, position, e.label, e.section, e.role,
                 e.latex, e.mathml, e.context)
                for position, e in enumerate(equations, 1)
            ])

    def equations_for(self, arxiv_id: str) -> list:
        from .site_data import EquationView
        rows = self._conn.execute("""
            SELECT anchor, label, section, role, latex, mathml, context
              FROM equations WHERE arxiv_id = ? ORDER BY position
        """, (arxiv_id,))
        return [EquationView(**dict(row)) for row in rows]

    def equation_source(self, arxiv_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM equation_sources WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def papers_without_equations(self) -> list[Paper]:
        rows = self._conn.execute("""
            SELECT p.* FROM papers p
             LEFT JOIN equation_sources s ON s.arxiv_id = p.arxiv_id
             WHERE s.arxiv_id IS NULL
             ORDER BY p.arxiv_id
        """)
        return [
            Paper(arxiv_id=row["arxiv_id"], title=row["title"],
                  abstract=row["abstract"], authors=json.loads(row["authors"]),
                  categories=json.loads(row["categories"]),
                  published=row["published"])
            for row in rows
        ]
```

In `site_data`, before the `pontos = []` loop, load the equation state once:

```python
        sources = {
            row["arxiv_id"]: dict(row)
            for row in self._conn.execute("SELECT * FROM equation_sources")
        }
```

Inside the loop, change the `Ponto(...)` construction to end with:

```python
                technique=r["technique"], porque=r["porque"],
                equations=tuple(self.equations_for(r["arxiv_id"])),
                equations_status=sources.get(r["arxiv_id"], {}).get("status", "not_fetched"),
                equations_fetched_at=sources.get(r["arxiv_id"], {}).get("fetched_at", ""),
            ))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_store.py tests/test_site_data.py -q`
Expected: all pass

- [ ] **Step 6: Run the whole suite and commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add src/radar/site_data.py src/radar/store.py tests/test_store.py
git commit -m "feat: store selected equations per paper and expose them to site data"
```

---

### Task 5: Candidate label and section for the selector

**Files:**
- Modify: `src/radar/formulas.py:54-64` (`FormulaCandidate`)
- Modify: `src/radar/judge.py:209-237` (`build_formula_selection_prompt`)
- Test: `tests/test_formulas.py`, `tests/test_judge.py`

**Interfaces:**
- Produces: `FormulaCandidate.label: str = ""` and `FormulaCandidate.section: str = ""` (max 40 and 200 characters); the selector prompt payload carries both keys.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_formulas.py`:

```python
def test_candidates_can_carry_an_equation_label_and_section():
    from radar.formulas import FormulaCandidate
    candidate = FormulaCandidate(
        candidate_id="eq-" + "a" * 16, path="arxiv-html:S4.E9",
        environment="equation", latex="x", label="(9)", section="4 Methodology",
    )
    assert candidate.label == "(9)"
    plain = FormulaCandidate(
        candidate_id="eq-" + "b" * 16, path="main.tex", environment="equation", latex="x",
    )
    assert plain.label == "" and plain.section == ""
```

Append to `tests/test_judge.py`:

```python
def test_formula_prompt_carries_equation_label_and_section():
    from radar.formulas import FormulaCandidate
    from radar.judge import build_formula_selection_prompt
    from radar.models import Paper
    paper = Paper(arxiv_id="2605.13790", title="T", abstract="A", authors=["X"],
                  categories=["cs.LG"], published="2026-05-13")
    prompt = build_formula_selection_prompt(paper, [FormulaCandidate(
        candidate_id="eq-" + "c" * 16, path="arxiv-html:S4.E9",
        environment="equation", latex="Loss=1", label="(9)", section="4 Methodology",
    )])
    assert '"label": "(9)"' in prompt
    assert '"section": "4 Methodology"' in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_formulas.py tests/test_judge.py -q -k "label"`
Expected: FAIL with `ValidationError: Extra inputs are not permitted`

- [ ] **Step 3: Add the fields and prompt keys**

In `src/radar/formulas.py`, add to `FormulaCandidate` after `context_after`:

```python
    label: str = Field(default="", max_length=40)
    section: str = Field(default="", max_length=200)
```

In `src/radar/judge.py`, extend the `candidate_payload` dictionary in `build_formula_selection_prompt`:

```python
            "context_after": item.context_after,
            "label": item.label,
            "section": item.section,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_formulas.py tests/test_judge.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add src/radar/formulas.py src/radar/judge.py tests/test_formulas.py tests/test_judge.py
git commit -m "feat: give the formula selector each candidate's number and section"
```

---

### Task 6: Collection step

**Files:**
- Create: `src/radar/equations.py`
- Test: `tests/test_equations.py`

**Interfaces:**
- Produces: `html_candidates(equations: list[HtmlEquation]) -> list[FormulaCandidate]`; `collect_equations(store, papers: list[Paper], *, fetch_html, selector, today: str, selector_model: str) -> Counter[str]`; `EquationsStatus` literal; `MAX_SELECTED = 3`.
- Consumes: `fetch_arxiv_html`, `parse_arxiv_html`, `HtmlEquation` (Tasks 1–3); `Store.record_equations` (Task 4); `FormulaCandidate`, `FormulaSelection`, `rank_formula_candidates`, `verify_formula_selection` from `formulas.py`; `EquationView` (Task 4). `fetch_html(arxiv_id) -> HtmlFetch`; `selector.select(paper, candidates) -> FormulaSelection`.

- [ ] **Step 1: Write the failing collection tests**

Create `tests/test_equations.py`:

```python
from collections import Counter
from pathlib import Path

import pytest

from radar.arxiv_html import HtmlFetch, parse_arxiv_html
from radar.equations import collect_equations, html_candidates
from radar.formulas import FormulaSelection, FormulaSelectionItem
from radar.models import Paper
from radar.store import Store

SAMPLE = (Path(__file__).parent / "fixtures" / "arxiv_html_sample.html").read_text(
    encoding="utf-8")
PAPER = Paper(arxiv_id="2605.13790", title="Di-BiLPS", abstract="Latent PDE solver.",
              authors=["A"], categories=["cs.LG"], published="2026-05-13")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    s.upsert_paper(PAPER, seen_at="2026-09-08", scope="teste")
    return s


class FakeSelector:
    def __init__(self, selection=None, error=None):
        self.selection, self.error, self.calls = selection, error, []

    def select(self, paper, candidates):
        self.calls.append((paper, candidates))
        if self.error:
            raise self.error
        return self.selection


def _available(arxiv_id):
    return HtmlFetch(status="available", text=SAMPLE, sha256="d" * 64)


def test_html_candidates_are_exact_ids_with_label_and_section():
    candidates = html_candidates(parse_arxiv_html(SAMPLE))
    assert [c.path for c in candidates] == [
        "arxiv-html:S3.E1", "arxiv-html:S4.E9", "arxiv-html:S4.Ex1", "arxiv-html:A3.E19"]
    assert candidates[1].label == "(9)" and candidates[1].section == "4 Methodology"
    assert candidates[1].latex.startswith("Loss=")
    assert candidates[1].context_before.endswith("as follows:")
    assert candidates[1].environment == "equation"
    assert len({c.candidate_id for c in candidates}) == 4
    assert html_candidates(parse_arxiv_html(SAMPLE)) == candidates


def test_selected_equations_are_stored_with_roles_in_selection_order(store):
    candidates = html_candidates(parse_arxiv_html(SAMPLE))
    by_anchor = {c.path.split(":")[1]: c.candidate_id for c in candidates}
    selector = FakeSelector(FormulaSelection(kind="formula", selected=[
        FormulaSelectionItem(candidate_id=by_anchor["S4.E9"], role="loss"),
        FormulaSelectionItem(candidate_id=by_anchor["S3.E1"], role="baseline"),
    ]))
    outcome = collect_equations(
        store, [PAPER], fetch_html=_available, selector=selector,
        today="2026-09-08", selector_model="kimi-k2.6")
    assert outcome == Counter({"selected": 1})
    rows = store.equations_for(PAPER.arxiv_id)
    assert [(e.anchor, e.role, e.label) for e in rows] == [
        ("S4.E9", "loss", "(9)"), ("S3.E1", "baseline", "(1)")]
    assert rows[0].context == "The loss function can be expressed as follows:"
    assert rows[0].mathml.startswith('<math display="block">')
    source = store.equation_source(PAPER.arxiv_id)
    assert source["status"] == "selected" and source["core_kind"] == "formula"
    assert source["html_sha256"] == "d" * 64 and source["selector_model"] == "kimi-k2.6"
    assert selector.calls[0][0] == PAPER


def test_non_formula_core_is_recorded_without_equations(store):
    selector = FakeSelector(FormulaSelection(kind="algorithm", selected=[]))
    outcome = collect_equations(
        store, [PAPER], fetch_html=_available, selector=selector,
        today="2026-09-08", selector_model="kimi-k2.6")
    assert outcome == Counter({"not_formula": 1})
    source = store.equation_source(PAPER.arxiv_id)
    assert source["status"] == "not_formula" and source["core_kind"] == "algorithm"
    assert store.equations_for(PAPER.arxiv_id) == []


@pytest.mark.parametrize("status", ["unavailable", "rejected"])
def test_missing_html_is_recorded_before_any_selection(store, status):
    selector = FakeSelector()
    outcome = collect_equations(
        store, [PAPER], fetch_html=lambda _id: HtmlFetch(status=status),
        selector=selector, today="2026-09-08", selector_model="kimi-k2.6")
    assert outcome == Counter({status: 1})
    assert store.equation_source(PAPER.arxiv_id)["status"] == status
    assert selector.calls == []


def test_a_page_without_display_equations_skips_the_selector(store):
    selector = FakeSelector()
    outcome = collect_equations(
        store, [PAPER],
        fetch_html=lambda _id: HtmlFetch(
            status="available", sha256="e" * 64,
            text='<div class="ltx_page_main"><p class="ltx_p">prose</p></div>'),
        selector=selector, today="2026-09-08", selector_model="kimi-k2.6")
    assert outcome == Counter({"no_equations": 1})
    assert selector.calls == []


def test_selector_errors_and_unknown_ids_are_recorded_not_raised(store):
    failing = FakeSelector(error=RuntimeError("kimi down"))
    outcome = collect_equations(
        store, [PAPER], fetch_html=_available, selector=failing,
        today="2026-09-08", selector_model="kimi-k2.6")
    assert outcome == Counter({"selector_failed": 1})
    assert store.equation_source(PAPER.arxiv_id)["status"] == "selector_failed"

    unknown = FakeSelector(FormulaSelection(kind="formula", selected=[
        FormulaSelectionItem(candidate_id="eq-" + "f" * 16, role="loss")]))
    outcome = collect_equations(
        store, [PAPER], fetch_html=_available, selector=unknown,
        today="2026-09-09", selector_model="kimi-k2.6")
    assert outcome == Counter({"selector_failed": 1})


def test_a_fetch_exception_leaves_no_row_so_backfill_retries(store):
    def broken(_id):
        raise RuntimeError("network")

    outcome = collect_equations(
        store, [PAPER], fetch_html=broken, selector=FakeSelector(),
        today="2026-09-08", selector_model="kimi-k2.6")
    assert outcome == Counter({"fetch_error": 1})
    assert store.equation_source(PAPER.arxiv_id) is None
    assert store.papers_without_equations() == [PAPER]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_equations.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'radar.equations'`

- [ ] **Step 3: Write the collection module**

Create `src/radar/equations.py`:

```python
"""Central equations for research pages: parse, select, store.

The step never raises for one paper. Every outcome becomes a status row so
the page can state it and the backfill can retry what was never fetched.
"""
from __future__ import annotations

import hashlib
import logging
from collections import Counter
from typing import Literal

from .arxiv_html import HtmlEquation, HtmlFetch, parse_arxiv_html
from .formulas import (FormulaCandidate, FormulaSelection, FormulaSelector,
                       rank_formula_candidates, verify_formula_selection)
from .models import Paper
from .site_data import EquationView

log = logging.getLogger(__name__)

MAX_SELECTED = 3
EquationsStatus = Literal[
    "not_fetched", "unavailable", "rejected", "no_equations", "not_formula",
    "selected", "selector_failed",
]


def html_candidates(equations: list[HtmlEquation]) -> list[FormulaCandidate]:
    """Exact candidates the selector may choose only by ID."""
    candidates: list[FormulaCandidate] = []
    for equation in equations:
        digest = hashlib.sha256(
            f"arxiv-html\0{equation.anchor}\0{equation.latex}".encode("utf-8")
        ).hexdigest()[:16]
        candidates.append(FormulaCandidate(
            candidate_id=f"eq-{digest}",
            path=f"arxiv-html:{equation.anchor}",
            environment="equation",
            latex=equation.latex,
            context_before=equation.context_before,
            context_after=equation.context_after,
            label=equation.label,
            section=equation.section,
        ))
    return candidates


def _views(
    selection: FormulaSelection, ranked: list[FormulaCandidate],
    by_id: dict[str, HtmlEquation],
) -> list[EquationView]:
    """Only IDs the model actually received resolve; anything else raises."""
    views: list[EquationView] = []
    for item, candidate in verify_formula_selection(selection, ranked)[:MAX_SELECTED]:
        equation = by_id[candidate.candidate_id]
        views.append(EquationView(
            anchor=equation.anchor, label=equation.label,
            section=equation.section, role=item.role, latex=equation.latex,
            mathml=equation.mathml, context=equation.context_before,
        ))
    return views


def collect_equations(
    store, papers: list[Paper], *, fetch_html, selector: FormulaSelector,
    today: str, selector_model: str,
) -> Counter[str]:
    """Fetch, parse, select and store for each paper; returns outcome counts."""
    outcome: Counter[str] = Counter()
    for paper in papers:
        try:
            fetched: HtmlFetch = fetch_html(paper.arxiv_id)
        except Exception as exc:  # noqa: BLE001 - one paper must not stop the day
            log.warning("arXiv HTML fetch failed for %s: %s", paper.arxiv_id, exc)
            outcome["fetch_error"] += 1
            continue

        def record(status: str, *, core_kind=None, model=None, views=()):
            store.record_equations(
                paper.arxiv_id, fetched_at=today, status=status,
                html_sha256=fetched.sha256 or None, core_kind=core_kind,
                selector_model=model, equations=list(views))
            outcome[status] += 1

        if fetched.status != "available":
            record(fetched.status)
            continue
        equations = parse_arxiv_html(fetched.text)
        if not equations:
            record("no_equations")
            continue
        all_candidates = html_candidates(equations)
        by_id = {c.candidate_id: e for c, e in zip(all_candidates, equations)}
        ranked = rank_formula_candidates(all_candidates)
        try:
            selection = selector.select(paper, ranked)
            views = _views(selection, ranked, by_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("equation selection failed for %s: %s", paper.arxiv_id, exc)
            record("selector_failed", model=selector_model)
            continue
        if selection.kind != "formula":
            record("not_formula", core_kind=selection.kind, model=selector_model)
            continue
        record("selected", core_kind="formula", model=selector_model, views=views)
    return outcome
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_equations.py -q`
Expected: 8 passed

- [ ] **Step 5: Run the whole suite and commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add src/radar/equations.py tests/test_equations.py
git commit -m "feat: collect central equations per paper with explicit statuses"
```

---

### Task 7: Page model and JSON

**Files:**
- Modify: `src/radar/public_labels.py` (add `CORE_KIND_PHRASES`)
- Modify: `src/radar/public_research.py:79-145` (`ResearchEquation`, page fields, invariant) and `:239-300` (`build_research_page`)
- Test: `tests/test_public_research.py`

**Interfaces:**
- Produces: `ResearchEquation(anchor, label, section, role, latex, mathml, context)` frozen Pydantic model; `ResearchPage.equations: tuple[ResearchEquation, ...] = ()`; `ResearchPage.equations_status: EquationsStatus = "not_fetched"`; `ResearchPage.core_kind: str = ""`; `ResearchPage.equations_fetched_at: str = ""`; `CORE_KIND_PHRASES: dict[str, str]`.
- Consumes: `Ponto.equations`, `Ponto.equations_status`, `Ponto.equations_fetched_at` (Task 4); `EquationsStatus` (Task 6).

- [ ] **Step 1: Write the failing page-model tests**

Append to `tests/test_public_research.py`:

```python
from radar.site_data import EquationView


def _equation_view(anchor="S4.E9", role="loss") -> EquationView:
    return EquationView(
        anchor=anchor, label="(9)", section="4 Methodology", role=role,
        latex=r"Loss=\operatorname{CE}(S^{F},I)",
        mathml='<math display="block"><mi>L</mi></math>',
        context="The loss function can be expressed as follows:")


def test_indexed_page_exports_selected_equations():
    page = build_research_page(
        _paper(equations=(_equation_view(),), equations_status="selected",
               equations_fetched_at="2026-09-08"),
        as_of="2026-09-08")
    assert page.equations_status == "selected"
    assert page.equations_fetched_at == "2026-09-08"
    assert page.equations[0].mathml == '<math display="block"><mi>L</mi></math>'
    assert page.equations[0].role == "loss"
    payload = page.model_dump(mode="json")
    assert payload["equations"][0]["latex"].startswith("Loss=")
    assert payload["schema_version"] == 1


def test_page_without_the_step_says_equations_were_not_fetched():
    page = build_research_page(_paper(), as_of="2026-09-08")
    assert page.equations == () and page.equations_status == "not_fetched"


def test_selected_status_requires_at_least_one_equation():
    with pytest.raises(ValidationError):
        build_research_page(_paper(equations_status="selected"), as_of="2026-09-08")


def test_absent_status_cannot_carry_equations():
    with pytest.raises(ValidationError):
        build_research_page(
            _paper(equations=(_equation_view(),), equations_status="unavailable"),
            as_of="2026-09-08")


def test_core_kind_phrases_cover_every_non_formula_kind():
    from radar.public_labels import CORE_KIND_PHRASES
    assert set(CORE_KIND_PHRASES) == {
        "algorithm", "system", "evaluation_protocol", "concept", "none"}
    assert CORE_KIND_PHRASES["algorithm"] == "an algorithm"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_public_research.py -q`
Expected: FAIL with `ValidationError` mentioning `equations` (extra field) or `AttributeError: 'ResearchPage' object has no attribute 'equations_status'`

- [ ] **Step 3: Add labels, model, and builder fields**

In `src/radar/public_labels.py`, after `FORMULA_ROLE_LABELS`:

```python
CORE_KIND_PHRASES = {
    "algorithm": "an algorithm",
    "system": "a system design",
    "evaluation_protocol": "an evaluation protocol",
    "concept": "a concept",
    "none": "not classified",
}
```

In `src/radar/public_research.py`, import the status type and add the model after `IndependentTest`:

```python
from .equations import EquationsStatus
```

```python
class ResearchEquation(BaseModel):
    """One central equation, MathML already sanitized by the collector."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor: str = Field(min_length=1)
    label: str = ""
    section: str = ""
    role: str = Field(min_length=1)
    latex: str = Field(min_length=1)
    mathml: str = Field(pattern=r"^<math display=\"block\">")
    context: str = ""
```

Add to `ResearchPage` after `infrastructure_basis`:

```python
    equations: tuple[ResearchEquation, ...] = ()
    equations_status: EquationsStatus = "not_fetched"
    core_kind: str = ""
    equations_fetched_at: str = ""
```

Extend the `exposure_map_is_complete` validator, before its final `return self`:

```python
        if self.equations_status == "selected" and not self.equations:
            raise ValueError("selected equations status requires at least one equation")
        if self.equations_status != "selected" and self.equations:
            raise ValueError("only the selected status may carry equations")
```

In `build_research_page`, add to the `ResearchPage(...)` call after `infrastructure_basis=infrastructure_basis,`:

```python
        equations=tuple(
            ResearchEquation(
                anchor=e.anchor, label=e.label, section=e.section, role=e.role,
                latex=e.latex, mathml=e.mathml, context=e.context)
            for e in paper.equations
        ),
        equations_status=paper.equations_status,
        equations_fetched_at=paper.equations_fetched_at,
```

`core_kind` is filled in Task 8 from the store row; leave its default here.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_public_research.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add src/radar/public_labels.py src/radar/public_research.py tests/test_public_research.py
git commit -m "feat: publish central equations in the research page model"
```

---

### Task 8: Core kind on points and pages

**Files:**
- Modify: `src/radar/site_data.py` (`Ponto.core_kind`)
- Modify: `src/radar/store.py` (`site_data` fills it)
- Modify: `src/radar/public_research.py` (`build_research_page` passes it)
- Test: `tests/test_store.py`, `tests/test_public_research.py`

**Interfaces:**
- Produces: `Ponto.core_kind: str = ""`; `ResearchPage.core_kind` filled from the store's `core_kind` column.
- Consumes: Task 4 and Task 7 fields.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_site_data_carries_the_selector_core_kind(store):
    from datetime import date

    from radar.models import Judgment, Signal
    store.upsert_paper(P, seen_at="2026-09-08", scope="teste")
    store.record_judgment(
        P.arxiv_id,
        Judgment(technique="T", familia="cache_kv", pratica="testar",
                 ganho_eixo="nenhum", ganho_fator=None, ganho_texto="",
                 resumo="R", porque="P"),
        model="kimi-k3", judged_at="2026-09-08")
    store.record_signal(
        P.arxiv_id,
        Signal(total_impls=1, independent_impls=1, velocity_14d=0,
               stars_total=0, citations=None),
        score=0.5, checked_at="2026-09-08")
    store.record_equations(
        P.arxiv_id, fetched_at="2026-09-08", status="not_formula",
        html_sha256="c" * 64, core_kind="algorithm", selector_model="kimi-k2.6",
        equations=[])
    ponto = store.site_data(date(2026, 9, 8)).pontos[0]
    assert ponto.equations_status == "not_formula" and ponto.core_kind == "algorithm"
```

Append to `tests/test_public_research.py`:

```python
def test_page_names_the_non_formula_core_kind():
    page = build_research_page(
        _paper(equations_status="not_formula", core_kind="algorithm"), as_of="2026-09-08")
    assert page.core_kind == "algorithm"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_store.py tests/test_public_research.py -q -k core_kind`
Expected: FAIL with `TypeError: Ponto.__init__() got an unexpected keyword argument 'core_kind'`

- [ ] **Step 3: Thread the field through**

In `src/radar/site_data.py`, add after `equations_fetched_at`:

```python
    core_kind: str = ""
```

In `src/radar/store.py` `site_data`, add to the `Ponto(...)` construction:

```python
                core_kind=sources.get(r["arxiv_id"], {}).get("core_kind") or "",
```

In `src/radar/public_research.py` `build_research_page`, add to the `ResearchPage(...)` call:

```python
        core_kind=paper.core_kind,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_store.py tests/test_public_research.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add src/radar/site_data.py src/radar/store.py src/radar/public_research.py tests/test_store.py tests/test_public_research.py
git commit -m "feat: carry the selector's core kind to the research page"
```

---

### Task 9: Equations section, jump link, and CSS

**Files:**
- Modify: `src/radar/site.py` (`_render_research_jumps`, `render_research_page`, new `_render_equations`)
- Modify: `src/radar/site_assets.py` (equation CSS near `.research-empty`, line 734)
- Test: `tests/test_site.py`, `tests/test_site_assets.py`

**Interfaces:**
- Produces: `<section id="equations" class="research-section">` on every research page; `_render_equations(page: ResearchPage) -> str`; CSS classes `.equation`, `.equation-context`, `.equation-display`, `.equation-eyebrow`, `.equations-provenance`.
- Consumes: `ResearchPage.equations`, `equations_status`, `core_kind`, `equations_fetched_at` (Tasks 7–8); `FORMULA_ROLE_LABELS`, `CORE_KIND_PHRASES`.

- [ ] **Step 1: Write the failing render tests**

Append to `tests/test_site.py`:

```python
def _page_with_equations(**updates):
    from radar.public_research import build_research_page
    from radar.site_data import EquationView
    equation = EquationView(
        anchor="S4.E9", label="(9)", section="4 Methodology", role="loss",
        latex=r"Loss=\operatorname{CE}(S^{F},I)",
        mathml='<math display="block"><mrow><mi>L</mi><mo>=</mo><mi>Ω</mi></mrow></math>',
        context="The loss function can be expressed as follows:")
    values = dict(equations=(equation,), equations_status="selected",
                  equations_fetched_at="2026-09-08")
    values.update(updates)
    return build_research_page(ponto(**values), as_of="2026-09-08")


def test_a_pagina_de_pesquisa_mostra_equacoes_centrais_como_mathml():
    html = render_research_page(_page_with_equations())
    assert '<section id="equations" class="research-section">' in html
    assert "Central equations" in html
    assert '<div class="equation-display"><math display="block">' in html
    assert "<mi>Ω</mi>" in html
    assert '<p class="equation-context">The loss function can be expressed as follows:</p>' in html
    assert '<p class="equation-eyebrow">equation (9) · §4 Methodology · loss function</p>' in html
    assert "equations from arXiv HTML · fetched 2026-09-08" in html
    assert 'href="#equations">equations</a>' in html
    assert "arxiv.org/html" not in html
    assert html.count("arxiv.org/abs/2608.11111") == 1


def test_a_secao_de_equacoes_diz_quando_o_nucleo_nao_e_uma_formula():
    html = render_research_page(
        _page_with_equations(equations=(), equations_status="not_formula",
                             core_kind="algorithm"))
    assert "The technical core is an algorithm, not an equation." in html
    assert '<div class="equation-display">' not in html
    assert 'href="#equations"' not in html


def test_a_secao_de_equacoes_explica_cada_ausencia_em_ingles():
    cases = {
        "not_fetched": "Equations have not been fetched yet.",
        "selector_failed": "Equations have not been fetched yet.",
        "unavailable": "arXiv has no HTML rendering for this paper.",
        "rejected": "arXiv has no HTML rendering for this paper.",
        "no_equations": "No display equations were found in the arXiv HTML.",
    }
    for status, copy in cases.items():
        html = render_research_page(
            _page_with_equations(equations=(), equations_status=status,
                                 equations_fetched_at=""))
        assert copy in html, status
        assert "equations from arXiv HTML" not in html, status


def test_equacao_sem_numero_omite_o_rotulo_e_a_secao_vazia():
    from radar.site_data import EquationView
    equation = EquationView(anchor="S4.Ex1", label="", section="", role="proposed_method",
                            latex="x", mathml='<math display="block"><mi>x</mi></math>',
                            context="")
    html = render_research_page(_page_with_equations(equations=(equation,)))
    assert '<p class="equation-eyebrow">unnumbered equation · proposed method</p>' in html
    assert '<p class="equation-context">' not in html
```

Append to `tests/test_site_assets.py`:

```python
def test_equacoes_tem_tipografia_propria_sem_link_externo():
    assert ".equation-display{" in STYLES
    assert ".equation-display math{" in STYLES
    assert "overflow-x:auto" in STYLES.split(".equation-display{")[1].split("}")[0]
    assert ".equation-eyebrow{" in STYLES
    assert ".equation-context{" in STYLES
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_site.py tests/test_site_assets.py -q -k "equac"`
Expected: FAIL with `AssertionError` on the section markup

- [ ] **Step 3: Render the section**

In `src/radar/site.py`, extend the imports from `public_labels` with `CORE_KIND_PHRASES` and `FORMULA_ROLE_LABELS` (the file already aliases the latter as `ROTULOS_PAPEL_FORMULA`; use that alias). Add before `_render_research_jumps`:

```python
EQUATIONS_ABSENT = {
    "not_fetched": "Equations have not been fetched yet.",
    "selector_failed": "Equations have not been fetched yet.",
    "unavailable": "arXiv has no HTML rendering for this paper.",
    "rejected": "arXiv has no HTML rendering for this paper.",
    "no_equations": "No display equations were found in the arXiv HTML.",
}


def _render_equations(page: ResearchPage) -> str:
    head = (
        '<div class="section-head"><h2>Central equations</h2>'
        '<p class="sub">The equations the paper builds on, copied from '
        "arXiv's HTML rendering and typeset here.</p></div>"
    )
    if page.equations_status != "selected":
        if page.equations_status == "not_formula":
            phrase = CORE_KIND_PHRASES.get(page.core_kind, "not classified")
            copy = f"The technical core is {phrase}, not an equation."
        else:
            copy = EQUATIONS_ABSENT[page.equations_status]
        return (
            '<section id="equations" class="research-section">'
            f'{head}<p class="research-empty">{escape(copy)}</p></section>'
        )
    items = []
    for equation in page.equations:
        role = ROTULOS_PAPEL_FORMULA.get(equation.role, equation.role)
        parts = [f"equation {equation.label}" if equation.label else "unnumbered equation"]
        if equation.section:
            parts.append(f"§{equation.section}")
        parts.append(role)
        context = (
            f'<p class="equation-context">{escape(equation.context)}</p>'
            if equation.context else ""
        )
        items.append(
            '<article class="equation">'
            f'{context}'
            f'<div class="equation-display">{equation.mathml}</div>'
            f'<p class="equation-eyebrow">{escape(" · ".join(parts))}</p>'
            '</article>'
        )
    return (
        '<section id="equations" class="research-section">'
        f'{head}<div class="equation-stack">{"".join(items)}</div>'
        '<p class="equations-provenance">equations from arXiv HTML · fetched '
        f'{escape(page.equations_fetched_at)}</p></section>'
    )
```

`equation.mathml` is inserted without escaping on purpose: it is the sanitizer's output, and `ResearchEquation.mathml` enforces the `<math display="block">` prefix.

In `_render_research_jumps`, insert after the `("decision", "shortlist reason")` tuple:

```python
    ]
    if page.equations_status == "selected":
        links.insert(1, ("equations", "equations"))
    links += [
```

so the list reads `decision`, then `equations` when present, then the rest. Concretely rewrite the function head as:

```python
    links = [("decision", "shortlist reason")]
    if page.equations_status == "selected":
        links.append(("equations", "equations"))
    links += [
        ("claims", "evidence"),
        ("exposure", "constraints"),
        ("risks", "risks"),
        ("minimum-test", "test plan"),
    ]
```

In `render_research_page`, insert `f'{_render_equations(page)}'` immediately after the decision section's closing `f'</dl>{rationale}</section>'` and before `'<section id="signal" class="research-section">'`.

- [ ] **Step 4: Add the CSS**

In `src/radar/site_assets.py`, immediately before the `.research-inference,.research-empty{` rule (line 734), add:

```css
.equation-stack{display:grid;gap:34px;max-width:72ch}
.equation-context{max-width:62ch;margin:0 0 14px;color:var(--fraco);font-size:15px;line-height:1.6}
.equation-display{max-width:100%;margin:0;padding:22px 26px;overflow-x:auto;
border:1px solid var(--linha);border-radius:18px;background:var(--superficie)}
.equation-display math{display:block;margin:0 auto;font-family:"AI Radar Math","STIX Two Math","Latin Modern Math","Cambria Math",math;font-size:1.15em;line-height:1.5;color:var(--texto)}
.equation-display math+math{margin-top:10px}
.equation-eyebrow{margin:12px 0 0;color:var(--apagado);font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.13em}
.equations-provenance{margin:26px 0 0;color:var(--apagado);font:9px var(--mono)}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_site.py tests/test_site_assets.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add src/radar/site.py src/radar/site_assets.py tests/test_site.py tests/test_site_assets.py
git commit -m "feat: render central equations as native MathML on research pages"
```

---

### Task 10: Math font, font-face, and publishing

**Files:**
- Create: `assets/fonts/stix-two-math.woff2`, `assets/fonts/STIXTwoMath-OFL.txt`
- Modify: `src/radar/site_assets.py` (add `math_font_face`)
- Modify: `src/radar/site.py` (`_pagina_estatica` gains `extra_style`; research page passes the font face)
- Modify: `src/radar/publish.py:19-24, 40-46` (copy fonts)
- Test: `tests/test_site_assets.py`, `tests/test_site.py`, `tests/test_publish.py`

**Interfaces:**
- Produces: `math_font_face(font_url: str) -> str` in `site_assets.py`; `FONT_ASSETS: tuple[Path, ...]` in `publish.py`; `_pagina_estatica(..., extra_style: str = "")`.
- Consumes: `render_research_page` (Task 9).

- [ ] **Step 1: Build the font subset and copy the license**

The subset was measured at 390 KB with the `MATH` table intact. Rebuild it from the system font so the repo holds a reproducible artifact:

```bash
cd /Users/luskoliveira/ai-radar && mkdir -p assets/fonts
pyftsubset /System/Library/Fonts/Supplemental/STIXTwoMath.otf \
  --unicodes="U+0020-007E,U+00A0-00FF,U+0370-03FF,U+2000-206F,U+2070-209F,U+20A0-20CF,U+2100-214F,U+2190-21FF,U+2200-22FF,U+2300-23FF,U+25A0-25FF,U+27C0-27EF,U+2980-29FF,U+2A00-2AFF,U+1D400-1D7FF,U+0300-036F" \
  --flavor=woff2 --layout-features='*' \
  --output-file=assets/fonts/stix-two-math.woff2
cp /private/tmp/claude-501/-Users-luskoliveira-frontend-lab/6fcc2c18-20bd-44a3-87b5-2c30406e7e64/scratchpad/STIXTwoMath-OFL.txt assets/fonts/STIXTwoMath-OFL.txt
python3 -c "from fontTools.ttLib import TTFont; f=TTFont('assets/fonts/stix-two-math.woff2'); print('MATH' in f, len(f.getGlyphOrder()))"
```

Expected: `True 4622` (glyph count may differ slightly by macOS version; `MATH` must be `True`). The license file must start with `Copyright 2001-2021 The STIX Fonts Project Authors`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_site_assets.py`:

```python
def test_a_fonte_matematica_prefere_a_copia_local_e_nunca_um_cdn():
    from radar.site_assets import math_font_face
    css = math_font_face("/ai-radar/assets/fonts/stix-two-math.woff2")
    assert css.startswith('@font-face{font-family:"AI Radar Math";')
    assert 'local("STIX Two Math"),local("STIXTwoMath-Regular"),' in css
    assert 'url(/ai-radar/assets/fonts/stix-two-math.woff2) format("woff2")' in css
    assert "font-display:swap" in css
    assert "fonts.gstatic.com" not in css and "https://" not in css
```

Append to `tests/test_site.py`:

```python
def test_a_pagina_com_equacoes_declara_a_fonte_matematica_no_head():
    html = render_research_page(_page_with_equations())
    head = html.split("</head>")[0]
    assert '@font-face{font-family:"AI Radar Math"' in head
    assert "url(/ai-radar/assets/fonts/stix-two-math.woff2)" in head
    sem = render_research_page(_page_with_equations(equations=(), equations_status="unavailable",
                                                    equations_fetched_at=""))
    assert "AI Radar Math" not in sem.split("</head>")[0]
```

Append to `tests/test_publish.py`:

```python
def test_publish_copies_the_math_font_and_its_license_stays_in_the_repo(tmp_path):
    store = _store(tmp_path / "radar.db")
    publish_site(store, tmp_path / "site", date(2026, 9, 8))
    font = tmp_path / "site" / "assets" / "fonts" / "stix-two-math.woff2"
    assert font.exists()
    assert font.read_bytes()[:4] == b"wOF2"
    from pathlib import Path
    assert (Path(__file__).resolve().parents[1] / "assets" / "fonts" /
            "STIXTwoMath-OFL.txt").read_text().startswith("Copyright 2001-2021 The STIX Fonts Project Authors")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_site_assets.py tests/test_site.py tests/test_publish.py -q -k "fonte or font"`
Expected: FAIL with `ImportError: cannot import name 'math_font_face'`

- [ ] **Step 4: Implement the font face, the head hook, and the copy**

In `src/radar/site_assets.py`, add after `_FONT_FACE`:

```python
def math_font_face(font_url: str) -> str:
    """Math face for pages with equations: the reader's local copy first."""
    return (
        '@font-face{font-family:"AI Radar Math";font-style:normal;font-weight:400;'
        'font-display:swap;src:local("STIX Two Math"),local("STIXTwoMath-Regular"),'
        f'url({font_url}) format("woff2")}}'
    )
```

In `src/radar/site.py`, add the keyword parameter `extra_style: str = ""` to `_pagina_estatica` after `extra_script: str = ""`, and where the returned HTML places `{styles}` in the head, append `{extra_style_tag}` right after it, with:

```python
    extra_style_tag = f'<style>{extra_style}</style>' if extra_style else ""
```

Then in `render_research_page`, import `math_font_face` from `.site_assets` and pass:

```python
        shared_assets=True, public_config=public_config,
        extra_style=(
            math_font_face(public_config.path("assets/fonts/stix-two-math.woff2"))
            if page.equations else ""
        ),
```

In `src/radar/publish.py`, after `VENDOR_ASSETS`:

```python
FONT_ASSETS = tuple(sorted(
    (Path(__file__).resolve().parents[2] / "assets" / "fonts").glob("*.woff2")
))
```

and in `publish_site`, after the vendor copy loop:

```python
    fonts_root = assets_root / "fonts"
    fonts_root.mkdir(parents=True, exist_ok=True)
    for asset in FONT_ASSETS:
        copyfile(asset, fonts_root / asset.name)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_site_assets.py tests/test_site.py tests/test_publish.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add assets/fonts src/radar/site_assets.py src/radar/site.py src/radar/publish.py tests/test_site_assets.py tests/test_site.py tests/test_publish.py
git commit -m "feat: typeset equations with a vendored STIX Two Math subset, local copy first"
```

---

### Task 11: Daily step and backfill script

**Files:**
- Modify: `src/radar/cli.py:41-150` (`_executar`)
- Create: `scripts/backfill_equations.py`
- Test: `tests/test_cli.py`, `tests/test_equations.py`

**Interfaces:**
- Produces: `_arxiv_html_fetch(arxiv_id) -> HtmlFetch` in `cli.py`; the daily step call; `scripts/backfill_equations.py` with `main(argv) -> int` and `--db`, `--arxiv-id`, `--limit`, `--today`.
- Consumes: `collect_equations` (Task 6), `KimiFormulaSelector`, `load_formula_model`, `load_formula_thinking`, `Store.papers_without_equations` (Task 4), `DayResult` fields from `pipeline.py` (`r.radar`, `r.feed` hold the day's judged papers).

- [ ] **Step 1: Inspect what `DayResult` exposes**

Run: `cd /Users/luskoliveira/ai-radar && sed -n '36,44p' src/radar/pipeline.py`

Expected: a dataclass with `radar`, `feed`, `cuts`, `push` (names as printed). The step below uses the `Paper` objects of `radar` and `feed`; if those lists hold judgment tuples instead of `Paper`, take `.paper` from each item and adjust the test accordingly.

- [ ] **Step 2: Write the failing CLI test**

Append to `tests/test_cli.py` (reuse the module's existing `ambiente` fixture and the Kimi monkeypatch pattern from `test_a_cli_uses_kimi_when_configured`):

```python
def test_a_cli_collects_equations_for_the_day_when_kimi_is_configured(ambiente, monkeypatch):
    from radar import cli
    calls = {}

    def fake_collect(store, papers, *, fetch_html, selector, today, selector_model):
        calls["papers"] = [p.arxiv_id for p in papers]
        calls["today"] = today
        calls["model"] = selector_model
        from collections import Counter
        return Counter({"selected": len(papers)})

    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_API_KEY", "k")
    monkeypatch.setattr(cli, "collect_equations", fake_collect)
    monkeypatch.setattr(cli, "KimiFormulaSelector", lambda *a, **k: object())
    ambiente.run()
    assert calls["model"] == "kimi-k2.6"
    assert calls["today"] == ambiente.today
    assert set(calls["papers"]) == set(ambiente.judged_ids)


def test_dry_run_never_collects_equations(ambiente, monkeypatch):
    from radar import cli
    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_API_KEY", "k")
    monkeypatch.setattr(cli, "collect_equations",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    ambiente.run(dry_run=True)
```

Before writing these two tests, read the `ambiente` fixture (`tests/test_cli.py:1-80`) and adapt `ambiente.run(...)`, `ambiente.today`, and `ambiente.judged_ids` to the names it actually provides; if it lacks a judged-id accessor, assert instead that `calls["papers"]` equals the ids the fixture's fake arXiv discovery returns.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_cli.py -q -k equations`
Expected: FAIL with `AttributeError: module 'radar.cli' has no attribute 'collect_equations'`

- [ ] **Step 4: Add the daily step**

In `src/radar/cli.py`, add imports:

```python
from .arxiv_html import fetch_arxiv_html
from .config import load_formula_model, load_formula_thinking
from .equations import collect_equations
from .judge import KimiFormulaSelector
```

Add an adapter next to the other `_..._fetch` helpers:

```python
def _arxiv_html_fetch(arxiv_id: str):
    return fetch_arxiv_html(arxiv_id, get=httpx.get)
```

In `_executar`, after the scope loop and before `markdown = compose_day(...)`, insert:

```python
    if not args.dry_run and provider == "kimi":
        # Equacoes centrais do HTML do arXiv para os papers julgados hoje.
        # Corre depois do julgamento e antes do jornal; uma falha vira estado
        # gravado por paper, nunca uma excecao que derrube o dia.
        judged = {p.arxiv_id: p for r in resultados.values() for p in (*r.radar, *r.feed)}
        selector = KimiFormulaSelector(
            os.environ.get("KIMI_API_KEY", ""), load_formula_model(),
            thinking=load_formula_thinking(),
            request_interval=load_kimi_request_interval(),
            base_url=load_kimi_base_url(),
        )
        outcome = collect_equations(
            store, list(judged.values()), fetch_html=_arxiv_html_fetch,
            selector=selector, today=today.isoformat(),
            selector_model=load_formula_model(),
        )
        print(f"equacoes: {dict(outcome)}", flush=True)
```

If Step 1 showed `radar`/`feed` items are not `Paper` objects, replace `p.arxiv_id: p` with the accessor that yields the `Paper`.

- [ ] **Step 5: Write the backfill script and its test**

Create `scripts/backfill_equations.py`:

```python
#!/usr/bin/env python3
"""Collect central equations for papers that never had the step run.

Requires KIMI_API_KEY for the selector. Safe to re-run: only papers without an
equation_sources row are processed unless --arxiv-id forces one.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from radar.arxiv_html import fetch_arxiv_html
from radar.config import (load_database_path, load_formula_model,
                          load_formula_thinking, load_kimi_base_url,
                          load_kimi_request_interval)
from radar.equations import collect_equations
from radar.judge import KimiFormulaSelector
from radar.store import Store


def main(argv: list[str] | None = None, *, selector=None, fetch_html=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=load_database_path())
    parser.add_argument("--arxiv-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--today", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args(argv)

    store = Store(args.db)
    try:
        store.init_schema()
        if args.arxiv_id:
            papers = [p for p in (store.get_paper(i) for i in args.arxiv_id) if p]
        else:
            papers = store.papers_without_equations()[:args.limit]
        if not papers:
            print("nothing to backfill")
            return 0
        if selector is None:
            api_key = os.environ.get("KIMI_API_KEY", "")
            if not api_key:
                print("KIMI_API_KEY is required for the selector", file=sys.stderr)
                return 2
            selector = KimiFormulaSelector(
                api_key, load_formula_model(), thinking=load_formula_thinking(),
                request_interval=load_kimi_request_interval(),
                base_url=load_kimi_base_url())
        outcome = collect_equations(
            store, papers,
            fetch_html=fetch_html or (lambda i: fetch_arxiv_html(i, get=httpx.get)),
            selector=selector, today=args.today, selector_model=load_formula_model())
        print(f"backfilled {len(papers)} papers: {dict(outcome)}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
```

Append to `tests/test_equations.py`:

```python
def test_backfill_script_processes_only_unfetched_papers(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "backfill_equations",
        Path(__file__).resolve().parents[1] / "scripts" / "backfill_equations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    db = tmp_path / "radar.db"
    s = Store(db)
    s.init_schema()
    s.upsert_paper(PAPER, seen_at="2026-09-08", scope="teste")
    done = Paper(arxiv_id="2508.22222", title="U", abstract="A", authors=["B"],
                 categories=["cs.LG"], published="2026-08-21")
    s.upsert_paper(done, seen_at="2026-09-08", scope="teste")
    s.record_equations(done.arxiv_id, fetched_at="2026-09-01", status="unavailable",
                       html_sha256=None, core_kind=None, selector_model=None, equations=[])
    s.close()

    selector = FakeSelector(FormulaSelection(kind="concept", selected=[]))
    code = module.main(["--db", str(db), "--today", "2026-09-08"],
                       selector=selector, fetch_html=_available)
    assert code == 0
    assert [paper.arxiv_id for paper, _ in selector.calls] == [PAPER.arxiv_id]
    s = Store(db)
    assert s.equation_source(PAPER.arxiv_id)["status"] == "not_formula"
    assert s.equation_source(done.arxiv_id)["fetched_at"] == "2026-09-01"
    s.close()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /Users/luskoliveira/ai-radar && python3 -m pytest tests/test_cli.py tests/test_equations.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q
git add src/radar/cli.py scripts/backfill_equations.py tests/test_cli.py tests/test_equations.py
git commit -m "feat: collect equations in the daily run and backfill the archive"
```

---

### Task 12: Documentation, backfill, republish

**Files:**
- Modify: `README.md` (the "How it works" list near line 90, the "no remote font" paragraph at line 167, the typography paragraph at line 496), `CONTEXT.md`
- Modify: `data/radar-state.db`, `site/` (generated)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Update the README**

After the sentence at README line 90 that begins "Every brief has a permanent `/papers/<arxiv-id>/` research page", add:

```markdown
   Each research page also shows up to three central equations taken from
   arXiv's HTML rendering: the equation number, its section, the sentence
   that introduces it, and the equation itself as native MathML. When the
   selector classifies the technical core as an algorithm, system, protocol,
   or concept, the page says so instead of showing an equation.
```

In the paragraph at line 167 ("Everything starts as semantic HTML..."), append after "CDN request.":

```markdown
Equations are MathML rendered by the browser, typeset with a subset of STIX
Two Math served from the site's own assets only when the reader's machine
lacks the font.
```

In the typography paragraph at line 496, append after the Be Vietnam Pro license sentence:

```markdown
Mathematics uses a subset of STIX Two Math with its `MATH` layout table
(`assets/fonts/stix-two-math.woff2`, OFL 1.1 in
`assets/fonts/STIXTwoMath-OFL.txt`); the `@font-face` lists the local font
first, so the file is fetched only when needed and only on pages with
equations.
```

In the Architecture section, after the sentence describing `fulltext.py` (line 500), add:

```markdown
`arxiv_html.py` fetches and parses arXiv's LaTeXML HTML into equations with
sanitized MathML; `equations.py` runs the daily collection step and records
one status per paper in `equation_sources`, with selected rows in
`equations`. `scripts/backfill_equations.py` repeats the step for papers the
daily run never reached.
```

- [ ] **Step 2: Update CONTEXT.md**

Append after the "Technical core" entry:

```markdown
**Central equation**:
One of up to three equations selected from arXiv's HTML rendering and shown
on a research page as typeset mathematics, with its number and section.
_Avoid_: Formula walkthrough, key formula, derived equation
```

- [ ] **Step 3: Run the backfill for the published archive**

This step spends Kimi tokens (about 3,000 to 6,000 input tokens per paper for 20 papers) and needs `KIMI_API_KEY` in the environment. Confirm with the user before running if the key is not already exported in the session.

```bash
cd /Users/luskoliveira/ai-radar && python3 scripts/backfill_equations.py --db data/radar-state.db --today "$(date -u +%F)"
```

Expected: `backfilled 20 papers: {...}` with `selected` for most and `unavailable` for `2608.24070`.

- [ ] **Step 4: Regenerate the site and check it**

```bash
cd /Users/luskoliveira/ai-radar && python3 - <<'EOF'
import pathlib
from datetime import date
from radar.publish import publish_site
from radar.store import Store
store = Store(pathlib.Path("data/radar-state.db"))
try:
    day = date.fromisoformat(open("site/index.html").read().split("AI Radar · ")[1][:10])
    publish_site(store, pathlib.Path("site"), day, cuts=None)
finally:
    store.close()
print("published for", day)
EOF
grep -c '<section id="equations"' site/papers/*/index.html | head -3
grep -l '<math display="block">' site/papers/*/index.html | wc -l
ls -la site/assets/fonts/
```

Expected: every paper page has the section, most contain MathML, and `site/assets/fonts/stix-two-math.woff2` exists.

- [ ] **Step 5: Visual check**

Serve `site/` on the local server and open one paper page with equations in headless Chrome; confirm Greek letters and fractions render and nothing overflows the card at 1280 px and at 390 px width.

```bash
SCR=/private/tmp/claude-501/-Users-luskoliveira-frontend-lab/6fcc2c18-20bd-44a3-87b5-2c30406e7e64/scratchpad
(pgrep -f "http.server 8765" >/dev/null || (python3 -m http.server 8765 --directory "$SCR/serve" > "$SCR/serve.log" 2>&1 &)); sleep 1
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --window-size=1280,2400 --screenshot="$SCR/equations-desktop.png" "http://127.0.0.1:8765/ai-radar/papers/2605.13790/#equations"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --window-size=390,2400 --screenshot="$SCR/equations-mobile.png" "http://127.0.0.1:8765/ai-radar/papers/2605.13790/#equations"
```

- [ ] **Step 6: Commit and push**

```bash
cd /Users/luskoliveira/ai-radar && python3 -m pytest -q && python3 scripts/verify_public_research_baseline.py
git add README.md CONTEXT.md data/radar-state.db site
git commit -m "feat: publish central equations for the research archive"
git pull --rebase origin main && git push origin main
```

If the rebase conflicts on `site/` files because a bot digest landed, take the remote version, re-run Step 4 with the remote's edition date, `git add site`, and continue the rebase.
