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
