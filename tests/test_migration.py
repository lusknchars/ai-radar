import json
import sqlite3

from scripts.migrar_e_rejulgar import (_append_checkpoint,
                                       _canary_papers,
                                       collect_kimi_with_checkpoint, execute,
                                       migrate_schema)
from radar.models import Judgment
from radar.store import Store


def _old_database(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE papers (
            arxiv_id TEXT PRIMARY KEY, title TEXT NOT NULL, abstract TEXT NOT NULL,
            authors TEXT NOT NULL, categories TEXT NOT NULL, published TEXT NOT NULL,
            first_seen TEXT NOT NULL, last_checked TEXT
        );
        CREATE TABLE signals (
            arxiv_id TEXT NOT NULL, checked_at TEXT NOT NULL,
            total_impls INTEGER NOT NULL, independent_impls INTEGER NOT NULL,
            velocity_14d INTEGER NOT NULL, stars_total INTEGER NOT NULL,
            citations INTEGER NOT NULL DEFAULT 0, score REAL,
            PRIMARY KEY (arxiv_id, checked_at)
        );
        CREATE TABLE repos (
            arxiv_id TEXT, full_name TEXT, owner TEXT, stars INTEGER,
            created_at TEXT, is_author INTEGER, is_author_reason TEXT
        );
        CREATE TABLE judgments (
            arxiv_id TEXT, judged_at TEXT, model TEXT, technique TEXT,
            summary TEXT, runs_on_3090 TEXT, rationale TEXT
        );
        CREATE TABLE deliveries (
            arxiv_id TEXT, delivered_at TEXT, channel TEXT, rank INTEGER
        );
    """)
    conn.execute(
        "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("2508.1", "T", "A", json.dumps([]), json.dumps(["cs.LG"]),
         "2026-08-01", "2026-08-29", None))
    conn.execute("INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 ("2508.1", "2026-08-29", 2, 2, 0, 3, 0, 0.4))
    conn.execute("INSERT INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?)",
                 ("2508.1", "2026-08-29", "old", "t", "s", "sim", "r"))
    conn.execute("INSERT INTO deliveries VALUES (?, ?, ?, ?)",
                 ("2508.1", "2026-08-29", "markdown", None))
    conn.commit()
    return conn


def test_a_migracao_preserva_o_acervo_e_descarta_so_o_julgamento(tmp_path):
    conn = _old_database(tmp_path / "old.db")
    migrate_schema(conn)
    assert conn.execute("SELECT scope FROM papers").fetchone()[0] == "inferencia"
    assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM judgments").fetchone()[0] == 0


def test_citacao_fica_nullable_depois_da_migracao(tmp_path):
    conn = _old_database(tmp_path / "old.db")
    migrate_schema(conn)
    conn.execute("UPDATE signals SET citations = NULL")
    conn.commit()
    assert conn.execute("SELECT citations FROM signals").fetchone()[0] is None


def _judgment():
    return Judgment(
        technique="T", familia="quantizacao", pratica="testar",
        ganho_eixo="nenhum", ganho_fator=None, ganho_texto="",
        resumo="R", porque="P",
    )


def test_o_banco_migrado_passa_no_preflight_do_pipeline(tmp_path):
    path = tmp_path / "old.db"
    conn = _old_database(path)
    migrate_schema(conn)
    conn.close()
    Store(path).init_schema()


def test_checkpoint_kimi_reaproveita_julgamentos_ja_pagos(tmp_path):
    path = tmp_path / "checkpoint.jsonl"
    paper = type("P", (), {"arxiv_id": "2508.1"})()
    _append_checkpoint(path, paper.arxiv_id, _judgment(),
                       provider="kimi", model="kimi-k3")

    class MustNotCall:
        def judge_one(self, paper):
            raise AssertionError("julgamento repetido")

        def wait_between_requests(self):
            raise AssertionError("espera sem chamada")

    result = collect_kimi_with_checkpoint(
        [paper], MustNotCall(), path, model="kimi-k3")
    assert result == {paper.arxiv_id: _judgment()}


def test_canario_cobre_do_inicio_ao_fim_do_acervo():
    papers = [type("P", (), {"arxiv_id": str(index)})() for index in range(100)]
    sample = _canary_papers(papers, 5)
    assert [paper.arxiv_id for paper in sample] == ["0", "25", "50", "74", "99"]


def test_gate_reprovado_restaura_o_banco_legado(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = _old_database(path)
    conn.close()
    checkpoint = tmp_path / "checkpoint.jsonl"
    _append_checkpoint(checkpoint, "2508.1", _judgment(),
                       provider="kimi", model="kimi-k3")
    monkeypatch.setenv("RADAR_LLM_PROVIDER", "kimi")
    monkeypatch.setenv("KIMI_API_KEY", "secret")
    monkeypatch.delenv("RADAR_MODEL", raising=False)
    monkeypatch.setattr("scripts.migrar_e_rejulgar._gate", lambda conn: False)

    assert execute(path, checkpoint) == 3
    restored = sqlite3.connect(path)
    columns = {row[1] for row in restored.execute("PRAGMA table_info(judgments)")}
    assert "summary" in columns
    assert restored.execute("SELECT COUNT(*) FROM judgments").fetchone()[0] == 1
