from datetime import date

from scripts import publish_public_research


def test_publishes_existing_state_without_network_or_model_calls(
    tmp_path, monkeypatch,
):
    calls = []

    class FakeStore:
        def __init__(self, path):
            calls.append(("store", path))

        def init_schema(self):
            calls.append(("schema",))

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(publish_public_research, "Store", FakeStore)
    monkeypatch.setattr(
        publish_public_research,
        "publish_site",
        lambda *args, **kwargs: calls.append(("publish", args, kwargs)),
    )

    database = tmp_path / "evaluation.db"
    reports = tmp_path / "reports"
    site = tmp_path / "site"
    assert publish_public_research.main([
        "--db", str(database),
        "--reports-dir", str(reports),
        "--site-dir", str(site),
        "--as-of", "2026-09-03",
    ]) == 0

    publish = next(call for call in calls if call[0] == "publish")
    assert publish[1][1:] == (site, date(2026, 9, 3))
    assert publish[2]["reports_root"] == reports
    assert calls[-1] == ("close",)
