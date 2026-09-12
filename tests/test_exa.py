from datetime import date
from pathlib import Path
from types import SimpleNamespace

from radar.exa import ExaDiscovery, arxiv_id
from radar.config import ScopeConfig
from radar.models import Discovery
from radar.arxiv import parse_feed

FEED = (Path(__file__).parent / 'fixtures/arxiv_response.xml').read_text()
SCOPE = ScopeConfig(name='inference', terms=('quantization',), categories=('cs.LG',))


def test_only_canonical_arxiv_sources_are_resolved():
    assert arxiv_id('https://arxiv.org/pdf/2608.11111v2.pdf') == '2608.11111'
    assert arxiv_id('https://arxiv.org.evil.test/abs/2608.11111') is None
    assert arxiv_id('https://example.com/abs/2608.11111') is None


def test_exa_metadata_comes_from_arxiv_and_duplicates_are_merged():
    calls = []
    def search(payload):
        calls.append(payload)
        return {'results': [
            {'url': 'https://arxiv.org/abs/2608.11111v2', 'title': 'untrusted title'},
            {'url': 'https://arxiv.org/pdf/2608.11111'},
            {'url': 'https://example.com/untrusted'},
        ]}
    adapter = ExaDiscovery(SimpleNamespace(recent=lambda scope: Discovery([])),
                           search=search, fetch=lambda url: FEED, today=date(2026,9,1))
    result = adapter.recent(SCOPE)
    assert len(result.papers) == 1
    assert result.papers[0].title == 'Fused INT4 Kernels for Ampere Inference'
    assert result.cuts == {'exa_invalid_source': 1}
    assert calls[0]['numResults'] == 10
    assert calls[0]['includeDomains'] == ['arxiv.org']


def test_failed_expansion_preserves_primary_discovery():
    primary = Discovery([], {'termo_falhou': 1})
    def fail(payload):
        raise RuntimeError('provider failure')
    adapter = ExaDiscovery(SimpleNamespace(recent=lambda scope: primary), search=fail,
                           fetch=lambda url: FEED, today=date(2026,9,1))
    assert adapter.recent(SCOPE).cuts == {'termo_falhou': 1, 'exa_search_failed': 1}


def test_stale_or_missing_metadata_does_not_enter_archive():
    adapter = ExaDiscovery(SimpleNamespace(recent=lambda scope: Discovery([])),
        search=lambda payload: {'results': [{'url':'https://arxiv.org/abs/2608.11111'},
                                           {'url':'https://arxiv.org/abs/2608.99999'}]},
        fetch=lambda url: FEED, today=date(2026,12,1))
    result = adapter.recent(SCOPE)
    assert not result.papers
    assert result.cuts == {'exa_outside_window': 1, 'exa_metadata_missing': 1}


def test_expanded_queries_are_distinct_and_one_failure_does_not_stop_others():
    payloads = []
    def search(payload):
        payloads.append(payload)
        if len(payloads) == 1:
            raise RuntimeError('temporary failure')
        return {'results':[{'url':'https://arxiv.org/abs/2608.11111'}]}
    scope = ScopeConfig(name='inference', categories=('cs.LG',),
                        terms=('quantization','attention','serving','cache','sparsity','decoding'))
    adapter = ExaDiscovery(SimpleNamespace(recent=lambda scope: Discovery([])),
        search=search, fetch=lambda url: FEED, today=date(2026,9,1), queries=3, lookback_days=90)
    result = adapter.recent(scope)
    assert len(payloads) == 3 and len({p['query'] for p in payloads}) == 3
    assert len(result.papers) == 1
    assert result.cuts == {'exa_search_failed':1}


def test_official_page_fallback_recovers_metadata_when_feed_is_unavailable():
    def unavailable(url):
        raise RuntimeError('feed unavailable')
    fetched = []
    def fetch_one(paper_id):
        fetched.append(paper_id)
        return parse_feed(FEED)[0]
    adapter = ExaDiscovery(SimpleNamespace(recent=lambda scope: Discovery([])),
        search=lambda _: {'results': [{'url': 'https://arxiv.org/abs/2608.11111'}]},
        fetch=unavailable, fetch_one=fetch_one, today=date(2026, 9, 1))
    result = adapter.recent(SCOPE)
    assert fetched == ['2608.11111']
    assert result.papers == [parse_feed(FEED)[0]]
    assert result.cuts == {}


def test_partial_feed_uses_fallback_only_for_missing_ids_and_counts_failures():
    fetched, sleeps = [], []
    def fetch_one(paper_id):
        fetched.append(paper_id)
        if paper_id == '2608.33333':
            raise RuntimeError('no metadata')
        return parse_feed(FEED)[0]  # A different ID must not be accepted.
    adapter = ExaDiscovery(SimpleNamespace(recent=lambda scope: Discovery([])),
        search=lambda _: {'results': [{'url': f'https://arxiv.org/abs/{paper_id}'}
                                     for paper_id in ('2608.11111', '2608.33333', '2608.44444')]},
        fetch=lambda _: FEED, fetch_one=fetch_one, sleep=sleeps.append,
        today=date(2026, 9, 1))
    result = adapter.recent(SCOPE)
    assert fetched == ['2608.33333', '2608.44444']
    assert sleeps == [3]
    assert [p.arxiv_id for p in result.papers] == ['2608.11111']
    assert result.cuts == {'exa_metadata_missing': 2}
