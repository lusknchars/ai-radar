from pathlib import Path

import radar.workflow as workflow


def test_configured_provider_runs_the_paid_pipeline(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_API_KEY", "configured")
    monkeypatch.setattr(
        workflow, "run_radar", lambda argv: calls.append(argv) or 7,
    )
    monkeypatch.setattr(
        workflow, "prepare_evaluation_database",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("baseline should not be prepared")
        ),
    )

    assert workflow.main(["--dry-run"]) == 7
    assert calls == [["--dry-run"]]


def test_missing_credential_publishes_no_cost_baseline(
    monkeypatch, tmp_path, capsys,
):
    database = tmp_path / "radar-state.db"
    calls = []
    monkeypatch.setenv("RADAR_DB", str(database))
    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workflow, "load_evaluation_manifest", lambda p: "manifest")

    def prepare(manifest, **kwargs):
        calls.append((manifest, kwargs))
        from radar.store import Store
        Store(kwargs["destination"]).init_schema()

    monkeypatch.setattr(workflow, "prepare_evaluation_database", prepare)
    monkeypatch.setattr(
        workflow, "publish_site",
        lambda store, root, today: calls.append((root, today)),
    )
    monkeypatch.setattr(workflow, "HISTORICAL_DATABASE", Path("source.db"))
    monkeypatch.setattr(workflow, "EVALUATION_JUDGMENTS", Path("judgments.jsonl"))
    monkeypatch.setattr(workflow, "EVALUATION_MANIFEST", Path("manifest.json"))

    assert workflow.main([]) == 0
    assert database.exists()
    assert calls[0][0] == "manifest"
    assert calls[0][1]["source_database"] == Path("source.db")
    assert calls[1][0] == Path("site")
    output = capsys.readouterr().out
    assert "without network requests" in output
    assert "KIMI_API_KEY is not configured" in output


def test_existing_state_is_republished_without_rebuilding(monkeypatch, tmp_path):
    from radar.store import Store

    database = tmp_path / "radar-state.db"
    Store(database).init_schema()
    monkeypatch.setenv("RADAR_DB", str(database))
    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        workflow, "prepare_evaluation_database",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("existing state must be preserved")
        ),
    )
    published = []
    monkeypatch.setattr(
        workflow, "publish_site",
        lambda *args: published.append(args),
    )

    assert workflow.main([]) == 0
    assert len(published) == 1
