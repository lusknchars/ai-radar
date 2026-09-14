from dataclasses import asdict, replace
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from radar.community import (CommunityConfig, discussion_search, discussion_term,
                             load_community_config, render_paper_discussion)
from radar.config import PublicConfig
from radar.discovery_files import render_sitemap
from radar.site import render_community
from radar.site_data import SiteData


COMMUNITY = CommunityConfig('reader/papers', 'R_123', 'General', 'DIC_123')
CONFIG = PublicConfig('reader/papers', '', 'https://papers.example', community=COMMUNITY)


def test_uninstalled_embed_keeps_real_forum_links_without_loading_widget():
    html = render_paper_discussion(COMMUNITY, '2608.12345', '/assets/community.js')
    assert 'https://github.com/reader/papers/discussions' in html
    assert 'arXiv 2608.12345' in html
    assert '<script' not in html and '<button' not in html
    assert 'Comments are public and separate' in html


def test_enabled_embed_has_one_canonical_thread_even_when_site_moves():
    config = replace(COMMUNITY, embedded=True)
    first = render_paper_discussion(config, '2608.12345', '/assets/community.js')
    moved = render_paper_discussion(config, '2608.12345', '/new-site/assets/community.js')
    assert 'data-term="arXiv 2608.12345"' in first
    assert 'data-term="arXiv 2608.12345"' in moved
    assert '<script defer src="/assets/community.js"></script>' in first
    # Third-party requests need the reader's explicit load action.
    assert 'src="https://giscus.app' not in first


@pytest.mark.parametrize('arxiv_id', ['2608.12345v2', '../private', '"><script>', 'abc'])
def test_discussion_mapping_rejects_noncanonical_ids(arxiv_id):
    with pytest.raises(ValueError):
        discussion_term(arxiv_id)


def test_forum_search_preserves_exact_paper_term():
    url = discussion_search(COMMUNITY, '2608.12345')
    assert parse_qs(urlsplit(url).query) == {'discussions_q': ['"arXiv 2608.12345"']}
    assert parse_qs(urlsplit(COMMUNITY.sign_in_url).query) == {'return_to': ['/reader/papers/discussions']}


def test_forks_do_not_inherit_the_original_community(tmp_path):
    path = tmp_path / 'community.json'
    path.write_text(json.dumps(asdict(COMMUNITY)))
    assert load_community_config('reader/papers', path) == COMMUNITY
    assert load_community_config('someone/else', path) is None
    with pytest.raises(ValueError, match='Community must belong'):
        PublicConfig('someone/else', '', 'https://papers.example', community=COMMUNITY)


def test_configuration_rejects_injected_ids_and_string_flags():
    with pytest.raises(ValueError):
        replace(COMMUNITY, repository_id='R_123" onload="alert(1)')
    with pytest.raises(ValueError):
        replace(COMMUNITY, embedded='false')
    html = render_paper_discussion(replace(COMMUNITY, category='"Quoted"', embedded=True),
                                   '2608.12345', '/assets/community.js')
    assert 'data-category="&quot;Quoted&quot;"' in html


def test_reading_room_escapes_papers_and_links_to_their_discussion():
    point = SimpleNamespace(arxiv_id='2608.12345', publicado='2026-08-01',
                            titulo='<script>alert(1)</script>', familia='cache_kv')
    data = SiteData(pontos=[point], dia='2026-09-12', cortes={}, rechecked_total=0)
    html = render_community(data, CONFIG)
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert 'href="/papers/2608.12345/#discussion"' in html
    assert 'Join with GitHub' in html and 'Create a GitHub account' in html
    assert 'community-steps' in html
    assert 'What would this change in my product?' in html
    assert 'name="password"' not in html
    sitemap = render_sitemap(CONFIG, paper_ids=[], report_ids=[], edition_days=[])
    assert 'https://papers.example/community/' in sitemap
