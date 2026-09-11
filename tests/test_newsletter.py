from dataclasses import replace
from datetime import date

import httpx
import pytest

from radar.config import DEFAULT_PUBLIC_CONFIG
from radar.newsletter import build_issue, write_issue
from radar.resend import ResendClient
from radar.selection import implementation_papers, recent_papers
from radar.site_data import CollectionStatus, SiteData
from tests.test_site import ponto


def data(*points):
    return SiteData(list(points), '2026-09-06', {}, 0,
                    collection=CollectionStatus('live', '2026-09-06', '2026-09-06', 'success'))


def test_new_paper_without_implementations_can_lead_the_weekly_issue():
    fresh = ponto(publicado='2026-09-06', independent_impls=0, score=0)
    old = ponto(arxiv_id='2607.11111', publicado='2026-07-01', score=10)
    irrelevant = ponto(arxiv_id='2609.22222', publicado='2026-09-06', pratica='nao_aplica')
    assert recent_papers([fresh, old, irrelevant], date(2026, 9, 6)) == [fresh]
    assert implementation_papers([fresh, old, irrelevant]) == [old]
    issue = build_issue(data(fresh, old, irrelevant), date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG)
    assert issue.paper_ids == [fresh.arxiv_id]
    assert '/papers/2608.11111/' in issue.html
    assert '{{{RESEND_UNSUBSCRIBE_URL}}}' in issue.html


def test_week_window_and_five_paper_cap():
    points = [ponto(arxiv_id=f'2609.{i:05d}', publicado='2026-09-05') for i in range(8)]
    points += [ponto(arxiv_id='2608.00000', publicado='2026-08-30'),
               ponto(arxiv_id='2609.99999', publicado='2026-09-07')]
    issue = build_issue(data(*points), date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG)
    assert len(issue.paper_ids) == 5
    assert '2608.00000' not in issue.paper_ids
    assert '2609.99999' not in issue.paper_ids


def test_missing_freshness_or_english_blocks_production_but_allows_labelled_preview():
    p = ponto(publicado='2026-09-06', resumo='Substitui o kernel com menos memoria.')
    with pytest.raises(ValueError, match='English'):
        build_issue(data(p), date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG)
    sample = replace(data(p), collection=CollectionStatus('sample'))
    with pytest.raises(ValueError, match='successful live collection'):
        build_issue(sample, date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG)
    issue = build_issue(sample, date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG, preview=True)
    assert '[SAMPLE PREVIEW]' in issue.subject


def test_draft_does_not_pad_an_empty_week_or_silently_change_an_existing_issue(tmp_path):
    assert build_issue(data(), date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG) is None
    issue = build_issue(data(ponto(publicado='2026-09-06')), date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG)
    path = write_issue(issue, tmp_path)
    assert write_issue(issue, tmp_path) == path
    with pytest.raises(ValueError, match='frozen'):
        write_issue(replace(issue, subject='Changed'), tmp_path)


def test_resend_recovers_existing_broadcast_and_never_sends():
    import json
    issue = build_issue(data(ponto(publicado='2026-09-06')), date(2026, 9, 6), DEFAULT_PUBLIC_CONFIG)
    calls, broadcasts = [], []

    def transport(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'data': broadcasts, 'has_more': False})
        body = json.loads(request.content)
        assert body['send'] is False
        broadcasts.append({'id': 'broadcast-1', 'name': body['name']})
        return httpx.Response(201, json={'id': 'broadcast-1'})

    client = ResendClient('fake', transport=httpx.MockTransport(transport))
    assert client.create_draft(issue, sender='radar@example.com', segment_id='s1') == 'broadcast-1'
    assert client.create_draft(issue, sender='radar@example.com', segment_id='s1') == 'broadcast-1'
    assert sum(r.method == 'POST' for r in calls) == 1
    with pytest.raises(ValueError, match='Sample'):
        client.create_draft(replace(issue, preview=True), sender='radar@example.com', segment_id='s1')
    client.close()
