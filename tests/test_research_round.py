from types import SimpleNamespace
import pytest

from radar.research_round import select_shortlist


def point(id, family, day='2026-09-12', practice='testar'):
    return SimpleNamespace(arxiv_id=id, familia=family, publicado=day, pratica=practice, score=1)


def test_shortlist_is_bounded_varied_and_skips_completed_reports(tmp_path):
    (tmp_path / 'done.json').write_text('{}')
    points = [point('done','a'), point('a1','a'), point('a2','a'), point('b','b'),
              point('c','c','2026-09-11'), point('ignored','d',practice='observar')]
    chosen = select_shortlist(points, reports_dir=tmp_path)
    assert len(chosen) == 3
    assert {p.familia for p in chosen} == {'a','b','c'}
    assert not {'done','ignored'} & {p.arxiv_id for p in chosen}


def test_shortlist_uses_available_candidates_without_padding(tmp_path):
    assert select_shortlist([], reports_dir=tmp_path) == []
    assert len(select_shortlist([point('one','a')], reports_dir=tmp_path)) == 1
    with pytest.raises(ValueError):
        select_shortlist([], reports_dir=tmp_path, limit=4)
