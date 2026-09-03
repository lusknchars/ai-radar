import sqlite3

from radar.doctor import main


def _ready_environment(monkeypatch, tmp_path):
    database = tmp_path / "local.db"
    monkeypatch.setenv("RADAR_DB", str(database))
    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_API_KEY", "test-only")
    monkeypatch.setenv("RADAR_REPOSITORY", "reader/research-radar")
    monkeypatch.delenv("RADAR_SITE_BASE_PATH", raising=False)
    monkeypatch.delenv("RADAR_SITE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    return database


def test_doctor_initialises_a_fresh_local_database(monkeypatch, tmp_path, capsys):
    database = _ready_environment(monkeypatch, tmp_path)

    assert main(["--init"]) == 0
    assert database.exists()
    output = capsys.readouterr().out
    assert "AI Radar is ready" in output
    assert "Telegram delivery is optional" in output


def test_doctor_does_not_create_a_database_without_init(monkeypatch, tmp_path):
    database = _ready_environment(monkeypatch, tmp_path)

    assert main([]) == 1
    assert not database.exists()


def test_doctor_rejects_a_legacy_database(monkeypatch, tmp_path, capsys):
    database = _ready_environment(monkeypatch, tmp_path)
    connection = sqlite3.connect(database)
    connection.execute("""CREATE TABLE judgments (
        arxiv_id TEXT, judged_at TEXT, model TEXT, technique TEXT,
        summary TEXT, runs_on_3090 TEXT, rationale TEXT
    )""")
    connection.commit()
    connection.close()

    assert main([]) == 1
    assert "schema is incompatible" in capsys.readouterr().out


def test_doctor_never_prints_the_api_key(monkeypatch, tmp_path, capsys):
    _ready_environment(monkeypatch, tmp_path)
    secret = "never-show-this-value"
    monkeypatch.setenv("KIMI_API_KEY", secret)

    main(["--init"])

    assert secret not in capsys.readouterr().out
