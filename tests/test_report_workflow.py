from pathlib import Path


def test_public_report_requests_require_maintainer_approval():
    workflow = Path(".github/workflows/report.yml").read_text(encoding="utf-8")

    assert "types: [opened, edited]" in workflow
    assert "[report request]" in workflow
    assert "No API credits were spent" in workflow
    assert "github.event.sender.login == github.repository_owner" in workflow
    assert "startsWith(github.event.changes.title.from, '[report request] ')" in workflow
    assert "github.event.issue.user.login == github.repository_owner" not in workflow
