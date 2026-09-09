"""Central equations for research pages: parse, select, store.

The step never raises for one paper. Every outcome becomes a status row so
the page can state it and the backfill can retry what was never fetched.
"""
from __future__ import annotations

import hashlib
import logging
from html import escape
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
    "selected", "selector_failed", "parse_failed",
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
            mathml=equation.mathml,
            context=equation.context_html or escape(equation.context_before, quote=False),
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
        try:
            equations = parse_arxiv_html(fetched.text)
            all_candidates = html_candidates(equations)
            ranked = rank_formula_candidates(all_candidates)
        except Exception as exc:  # noqa: BLE001 - markup we have never seen
            log.warning("arXiv HTML parse failed for %s: %s", paper.arxiv_id, exc)
            record("parse_failed")
            continue
        if not equations:
            record("no_equations")
            continue
        by_id = {c.candidate_id: e for c, e in zip(all_candidates, equations)}
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
