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
    # Replaced by the sanitizer in the next slice; kept so this one stands alone.
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
