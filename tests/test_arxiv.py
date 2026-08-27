from pathlib import Path

import pytest

from radar.arxiv import ARXIV_ENDPOINT, ArxivClient, build_query, parse_feed
from radar.config import DEFAULT_SCOPE, ScopeConfig

FIXTURE = (Path(__file__).parent / "fixtures" / "arxiv_response.xml").read_text()


def test_endpoint_is_https():
    """Em HTTP a API devolve corpo vazio com status 200 -- falha silenciosa."""
    assert ARXIV_ENDPOINT.startswith("https://")


def test_query_combines_categories_with_or_and_ands_the_term():
    q = build_query("quantization", ScopeConfig(categories=("cs.LG", "cs.AR"), terms=()))
    assert "cat:cs.LG OR cat:cs.AR" in q
    assert 'abs:"quantization"' in q
    assert " AND " in q


def test_parse_strips_version_from_the_arxiv_id():
    papers = parse_feed(FIXTURE)
    assert papers[0].arxiv_id == "2608.11111"


def test_parse_collapses_whitespace_in_title_and_abstract():
    p = parse_feed(FIXTURE)[0]
    assert p.title == "Fused INT4 Kernels for Ampere Inference"
    assert "  " not in p.abstract
    assert p.abstract.startswith("We present")


def test_parse_extracts_authors_in_order():
    assert parse_feed(FIXTURE)[0].authors == ("Elias Frantar", "Ji Lin")


def test_parse_extracts_all_categories():
    assert parse_feed(FIXTURE)[0].categories == ("cs.LG", "cs.AR")


def test_parse_keeps_published_as_iso_date():
    assert parse_feed(FIXTURE)[0].published == "2026-08-20"


def test_parse_returns_every_entry_without_filtering():
    """O parser nao filtra. Filtro de escopo e responsabilidade do cliente."""
    assert len(parse_feed(FIXTURE)) == 2


def test_empty_feed_returns_empty_list():
    empty = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert parse_feed(empty) == []


def test_client_filters_by_primary_category():
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return FIXTURE

    scope = ScopeConfig(categories=("cs.LG", "cs.AR"), terms=("quantization",))
    papers = ArxivClient(fetch=fake_fetch, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]
    assert len(seen) == 1


def test_client_unions_terms_and_deduplicates_by_id():
    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=lambda url: FIXTURE, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]


def test_client_sleeps_between_calls_for_arxiv_etiquette():
    naps = []
    scope = ScopeConfig(categories=("cs.LG",), terms=("a", "b", "c"))
    ArxivClient(fetch=lambda url: FIXTURE, sleep=naps.append).recent(scope)
    assert len(naps) == 2          # dorme entre chamadas, nao depois da ultima
    assert all(n >= 3 for n in naps)


def test_client_survives_one_failing_term():
    def flaky(url):
        if "sparsity" in url:
            raise RuntimeError("502")
        return FIXTURE

    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=flaky, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]
