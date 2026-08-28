"""Estado em SQLite, versionado no repositorio.

`signals` e append-only de proposito: e da diferenca entre duas observacoes que
sai a deteccao de ressurreicao. Um paper antigo voltando a ser implementado nao
e uma descoberta nova -- e um delta numa entrada que ja existe.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from .models import Judgment, Paper, RepoClassification, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    abstract     TEXT NOT NULL,
    authors      TEXT NOT NULL,
    categories   TEXT NOT NULL,
    published    TEXT NOT NULL,
    first_seen   TEXT NOT NULL,
    last_checked TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    arxiv_id          TEXT NOT NULL REFERENCES papers(arxiv_id),
    checked_at        TEXT NOT NULL,
    total_impls       INTEGER NOT NULL,
    independent_impls INTEGER NOT NULL,
    velocity_14d      INTEGER NOT NULL,
    stars_total       INTEGER NOT NULL,
    citations         INTEGER NOT NULL DEFAULT 0,
    score             REAL,
    PRIMARY KEY (arxiv_id, checked_at)
);
CREATE TABLE IF NOT EXISTS repos (
    arxiv_id         TEXT NOT NULL REFERENCES papers(arxiv_id),
    full_name        TEXT NOT NULL,
    owner            TEXT NOT NULL,
    stars            INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    is_author        INTEGER NOT NULL,
    is_author_reason TEXT,
    PRIMARY KEY (arxiv_id, full_name)
);
CREATE TABLE IF NOT EXISTS judgments (
    arxiv_id     TEXT NOT NULL REFERENCES papers(arxiv_id),
    judged_at    TEXT NOT NULL,
    model        TEXT NOT NULL,
    technique    TEXT NOT NULL,
    summary      TEXT NOT NULL,
    runs_on_3090 TEXT NOT NULL,
    rationale    TEXT NOT NULL,
    PRIMARY KEY (arxiv_id, judged_at)
);
CREATE TABLE IF NOT EXISTS deliveries (
    arxiv_id     TEXT NOT NULL REFERENCES papers(arxiv_id),
    delivered_at TEXT NOT NULL,
    channel      TEXT NOT NULL,
    rank         INTEGER,
    PRIMARY KEY (arxiv_id, delivered_at, channel)
);
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---------- papers ----------

    def upsert_paper(self, paper, seen_at: str) -> None:
        # first_seen so e gravado na insercao; ON CONFLICT nao o toca.
        self._conn.execute(
            """INSERT INTO papers
                 (arxiv_id, title, abstract, authors, categories, published, first_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(arxiv_id) DO UPDATE SET
                 title=excluded.title, abstract=excluded.abstract""",
            (paper.arxiv_id, paper.title, paper.abstract, json.dumps(paper.authors),
             json.dumps(paper.categories), paper.published, seen_at),
        )
        self._conn.commit()

    def known_ids(self) -> set[str]:
        """So os ids. O filtro de "ja conhecido" roda todo dia sobre a tabela
        inteira; `all_papers()` traria titulo e abstract de cada paper ja visto
        para montar um conjunto de chaves."""
        return {row["arxiv_id"] for row in
                self._conn.execute("SELECT arxiv_id FROM papers")}

    def all_papers(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM papers")]

    def touch_checked(self, arxiv_id: str, at: str) -> None:
        self._conn.execute("UPDATE papers SET last_checked=? WHERE arxiv_id=?", (at, arxiv_id))
        self._conn.commit()

    def stalest_papers(self, limit: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM papers ORDER BY last_checked IS NOT NULL, last_checked ASC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def papers_to_recheck(self, limit: int) -> list[Paper]:
        """Os papers da vez na rotacao de re-consulta, ja como objetos.

        `authors` e `categories` viajam como JSON nesta tabela; quem codificou
        e quem decodifica. Devolver linhas cruas espalharia conhecimento do
        formato de armazenamento para o pipeline.
        """
        return [
            Paper(
                arxiv_id=row["arxiv_id"],
                title=row["title"],
                abstract=row["abstract"],
                authors=json.loads(row["authors"]),
                categories=json.loads(row["categories"]),
                published=row["published"],
            )
            for row in self.stalest_papers(limit)
        ]

    # ---------- signals ----------

    def record_signal(self, arxiv_id: str, signal: Signal, score, checked_at: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO signals
                 (arxiv_id, checked_at, total_impls, independent_impls,
                  velocity_14d, stars_total, citations, score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (arxiv_id, checked_at, signal.total_impls, signal.independent_impls,
             signal.velocity_14d, signal.stars_total, signal.citations, score),
        )
        self._conn.commit()

    def signal_history(self, arxiv_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM signals WHERE arxiv_id=? ORDER BY checked_at ASC", (arxiv_id,))
        return [dict(r) for r in rows]

    def signal_delta(self, arxiv_id: str) -> dict | None:
        history = self.signal_history(arxiv_id)
        if len(history) < 2:
            return None
        first, last = history[0], history[-1]
        return {
            "independent_from": first["independent_impls"],
            "independent_to": last["independent_impls"],
            "stars_from": first["stars_total"],
            "stars_to": last["stars_total"],
            "days": (date.fromisoformat(last["checked_at"])
                     - date.fromisoformat(first["checked_at"])).days,
        }

    # ---------- repos ----------

    def record_repos(self, arxiv_id: str, classifications: list[RepoClassification]) -> None:
        # Substituicao, nao acumulo. Esta tabela E a mitigacao da heuristica de
        # autoria: um repo que sumiu da classificacao de hoje nao cita mais o
        # paper, e deixa-lo aqui coloca contagem contraditoria no markdown do
        # dia -- a linha continua listada enquanto o sinal ja nao a conta.
        self._conn.execute("DELETE FROM repos WHERE arxiv_id=?", (arxiv_id,))
        self._conn.executemany(
            """INSERT OR REPLACE INTO repos
                 (arxiv_id, full_name, owner, stars, created_at, is_author, is_author_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(arxiv_id, c.repo.full_name, c.repo.owner, c.repo.stars,
              c.repo.created_at, int(c.is_author), c.reason) for c in classifications],
        )
        self._conn.commit()

    def repos_for(self, arxiv_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM repos WHERE arxiv_id=? ORDER BY stars DESC", (arxiv_id,))
        return [dict(r) for r in rows]

    # ---------- judgments ----------

    def record_judgment(self, arxiv_id: str, j: Judgment, model: str, judged_at: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO judgments
                 (arxiv_id, judged_at, model, technique, summary, runs_on_3090, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (arxiv_id, judged_at, model, j.technique, j.summary, j.runs_on_3090, j.rationale),
        )
        self._conn.commit()

    def latest_judgment(self, arxiv_id: str) -> Judgment | None:
        row = self._conn.execute(
            "SELECT * FROM judgments WHERE arxiv_id=? ORDER BY judged_at DESC LIMIT 1",
            (arxiv_id,)).fetchone()
        if row is None:
            return None
        return Judgment(technique=row["technique"], summary=row["summary"],
                        runs_on_3090=row["runs_on_3090"], rationale=row["rationale"])

    # ---------- deliveries ----------

    def mark_delivered(self, arxiv_id: str, channel: str, at: str, rank: int | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO deliveries VALUES (?, ?, ?, ?)",
            (arxiv_id, at, channel, rank))
        self._conn.commit()

    def was_delivered(self, arxiv_id: str, channel: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM deliveries WHERE arxiv_id=? AND channel=? LIMIT 1",
            (arxiv_id, channel)).fetchone()
        return row is not None
