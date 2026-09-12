from datetime import date
import json

from radar.publish import publish_site
from radar.store import Store


def test_republishing_sample_never_claims_a_successful_collection(tmp_path):
    store = Store(tmp_path / "state.db")
    store.init_schema()
    run = store.begin_collection("2026-09-01", "sample")
    store.finish_collection(run, "unconfigured")
    publish_site(store, tmp_path / "site", date(2026, 9, 10))
    html = (tmp_path / "site/index.html").read_text()
    assert 'class="collection-status"' not in html
    status = json.loads((tmp_path / 'site/collection.json').read_text())
    assert status['mode'] == 'sample'
    assert status['last_success'] is None
    assert status['page_published'] == '2026-09-10'
    store.close()


def test_failed_and_sample_runs_preserve_last_success(tmp_path):
    store = Store(tmp_path / "state.db")
    store.init_schema()
    for day, mode, outcome in [("2026-09-07", "live", "success"),
                               ("2026-09-08", "live", "partial"),
                               ("2026-09-09", "sample", "unconfigured")]:
        store.finish_collection(store.begin_collection(day, mode), outcome)
    status = store.collection_status("2026-09-10")
    assert status.mode == "live"
    assert status.last_success == "2026-09-07"
    assert status.outcome == "unconfigured"
    assert store.collection_status("2026-09-07").outcome == "success"
    store.close()
