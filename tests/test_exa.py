from datetime import date
from pathlib import Path
from types import SimpleNamespace

from radar.exa import ExaDiscovery, arxiv_id
from radar.config import ScopeConfig
from radar.models import Discovery

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
