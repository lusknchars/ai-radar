from datetime import date

import pytest

from radar.models import Discovery
from radar.pipeline import run_day
from radar.store import Store
from tests.test_cli import ambiente, argv, cli
from tests.test_pipeline import SCOPE, T, fake_signal, judgment, paper


def test_judgment_budget_prioritizes_recent_papers_and_leaves_deferred_ids_unknown(tmp_path):
    store = Store(tmp_path / 'state.db')
    store.init_schema()
    papers = [paper(f'2508.{i:05d}') for i in range(4)]
    judged = []
    result = run_day(
        store, SCOPE, T, date(2026, 8, 30), 'test',
        fetch_papers=lambda scope: Discovery(papers),
        fetch_signal=lambda p, d: (fake_signal(2, 1), []),
        judge_all=lambda ps: judged.extend(ps) or {p.arxiv_id: judgment() for p in ps},
        new_paper_limit=2,
    )
    assert len(judged) == 2
    assert result.cuts['budget_deferred'] == 2
    assert len(store.known_ids()) == 2
    store.close()


def test_invalid_budget_stops_before_adapters_start(ambiente, monkeypatch):
    monkeypatch.setenv('RADAR_MAX_EQUATIONS_PER_RUN', '-1')
    monkeypatch.setattr(cli, 'ArxivClient', lambda **kw: pytest.fail('adapter started'))
    with pytest.raises(ValueError, match='RADAR_MAX_EQUATIONS'):
        cli.main(argv(ambiente))


def test_fatal_collection_failure_is_visible_in_republished_page(ambiente, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError('upstream unavailable')
    monkeypatch.setattr(cli, 'run_day', fail)
    with pytest.raises(RuntimeError, match='upstream unavailable'):
        cli.main(argv(ambiente))
    store = Store(ambiente / 'radar.db')
    assert store.collection_status('9999-12-31').outcome == 'failed'
    assert store.collection_status('9999-12-31').last_success is None
    store.close()
    assert 'Last successful collection: <strong>not recorded</strong>' in (ambiente / 'site/index.html').read_text()
