from pathlib import Path
import json
import pytest

import radar.workflow as workflow


@pytest.mark.parametrize('outcome,exit_code,ready', [
    ('success', 0, True), ('partial', 1, True), ('failed', 1, False),
    ('unconfigured', 0, True), ('running', 1, False),
])
def test_actions_publishes_completed_partial_results_but_blocks_failed_runs(
    monkeypatch, tmp_path, outcome, exit_code, ready,
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / 'outputs'
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    def collect(argv):
        Path('site').mkdir()
        Path('site/collection.json').write_text(json.dumps({'outcome': outcome}))
        return exit_code
    monkeypatch.setattr(workflow, 'main', collect)
    assert workflow.actions_main([]) == exit_code
    assert f'publication_ready={str(ready).lower()}\n' in output.read_text()
    assert f'collection_outcome={outcome if ready else "unknown"}\n' in output.read_text()


def test_actions_cannot_reuse_previous_success_when_current_run_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / 'outputs'
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    Path('site').mkdir()
    Path('site/collection.json').write_text('{"outcome":"success"}')
    monkeypatch.setattr(workflow, 'main', lambda argv: 1)
    assert workflow.actions_main([]) == 1
    assert 'publication_ready=false' in output.read_text()


def test_actions_dry_run_preserves_publication_metadata(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / 'outputs'
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    Path('site').mkdir()
    status = Path('site/collection.json')
    status.write_text('{"outcome":"success"}')
    monkeypatch.setattr(workflow, 'main', lambda argv: 0)
    assert workflow.actions_main(['--dry-run']) == 0
    assert status.read_text() == '{"outcome":"success"}'
    assert not output.exists()


def test_live_mode_without_credentials_fails_instead_of_publishing_sample(monkeypatch):
    monkeypatch.setenv('RADAR_COLLECTION_MODE', 'live')
    monkeypatch.setenv('RADAR_LLM_PROVIDER', 'kimi')
    monkeypatch.delenv('KIMI_API_KEY', raising=False)
    with pytest.raises(ValueError, match='Live collection requires KIMI_API_KEY'):
        workflow.main([])


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
