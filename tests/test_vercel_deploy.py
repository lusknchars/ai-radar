import io
import json
from urllib.error import HTTPError

import pytest

from scripts import deploy_vercel


@pytest.fixture
def configured(monkeypatch):
    for name, value in {"VERCEL_TOKEN": "private-test-value", "VERCEL_ORG_ID": "team_test", "VERCEL_PROJECT_ID": "prj_test"}.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_lookup_failure_stops_deploy_and_does_not_leak_credentials(configured, monkeypatch, capsys, status):
    def fail(request, timeout):
        assert request.full_url.endswith('/prj_test?teamId=team_test')
        assert request.get_header("Authorization") == "Bearer private-test-value"
        raise HTTPError(request.full_url, status, "private-test-value", {}, None)
    monkeypatch.setattr(deploy_vercel, "urlopen", fail)
    monkeypatch.setattr(deploy_vercel.subprocess, "run", lambda *a, **kw: pytest.fail("must not deploy"))
    assert deploy_vercel.main([]) == 1
    output = capsys.readouterr().out
    assert f"HTTP {status}" in output
    assert "private-test-value" not in output


def test_valid_access_can_be_checked_without_deploying(configured, monkeypatch):
    monkeypatch.setattr(deploy_vercel, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps({"id": "prj_test", "accountId": "team_test"}).encode()))
    monkeypatch.setattr(deploy_vercel.subprocess, "run", lambda *a, **kw: pytest.fail("check must not deploy"))
    assert deploy_vercel.main(["--check-only"]) == 0


def test_deploy_preserves_failure_and_uses_the_verified_team(configured, monkeypatch):
    monkeypatch.setattr(deploy_vercel, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps({"id": "prj_test", "accountId": "team_test"}).encode()))
    def deploy(command, check):
        assert command[-4:] == ["--scope", "team_test", "--token", "private-test-value"]
        return type("Result", (), {"returncode": 7})()
    monkeypatch.setattr(deploy_vercel.subprocess, "run", deploy)
    assert deploy_vercel.main([]) == 7


def test_wrong_team_never_deploys(configured, monkeypatch):
    monkeypatch.setattr(deploy_vercel, "urlopen", lambda *a, **kw: io.BytesIO(b'{"id":"prj_test","accountId":"team_other"}'))
    monkeypatch.setattr(deploy_vercel.subprocess, "run", lambda *a, **kw: pytest.fail("must not deploy"))
    assert deploy_vercel.main([]) == 1


def test_missing_configuration_fails_manual_check_but_can_skip_optional_deploy(monkeypatch):
    for key in ("VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID"):
        monkeypatch.delenv(key, raising=False)
    assert deploy_vercel.main([]) == 1
    assert deploy_vercel.main(["--optional"]) == 0
