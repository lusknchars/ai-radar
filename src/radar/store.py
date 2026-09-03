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


class SchemaMigrationRequired(RuntimeError):
    """O banco existe, mas nao pode ser lido pelo codigo atual."""


EXPECTED_JUDGMENT_COLUMNS = {
    "arxiv_id", "judged_at", "model", "technique", "familia", "pratica",
    "ganho_eixo", "ganho_fator", "ganho_texto", "resumo", "porque",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    abstract     TEXT NOT NULL,
    authors      TEXT NOT NULL,
    categories   TEXT NOT NULL,
    published    TEXT NOT NULL,
    first_seen   TEXT NOT NULL,
    last_checked TEXT,
    scope        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    arxiv_id          TEXT NOT NULL REFERENCES papers(arxiv_id),
    checked_at        TEXT NOT NULL,
    total_impls       INTEGER NOT NULL,
    independent_impls INTEGER NOT NULL,
    velocity_14d      INTEGER NOT NULL,
    stars_total       INTEGER NOT NULL,
    citations         INTEGER,          -- NULL = desconhecido, != 0
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
    familia      TEXT NOT NULL,
    pratica      TEXT NOT NULL,
    ganho_eixo   TEXT NOT NULL,
    ganho_fator  REAL,              -- NULL e legitimo: nem todo paper alega
    ganho_texto  TEXT NOT NULL,
    resumo       TEXT NOT NULL,
    porque       TEXT NOT NULL,
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

    def close(self) -> None:
        self._conn.close()

    def init_schema(self) -> None:
        existing = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(judgments)")
        }
        if existing and existing != EXPECTED_JUDGMENT_COLUMNS:
            self._raise_schema_mismatch(existing)
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(judgments)")
        }
        if columns != EXPECTED_JUDGMENT_COLUMNS:
            self._raise_schema_mismatch(columns)

    def _raise_schema_mismatch(self, columns: set[str]) -> None:
        legacy = {"summary", "runs_on_3090", "rationale"} <= columns
        detail = "schema legado" if legacy else f"colunas inesperadas: {sorted(columns)}"
        raise SchemaMigrationRequired(
            f"{self.path} usa {detail}; rode "
            "'python scripts/migrar_e_rejulgar.py' antes do pipeline"
        )

    # ---------- papers ----------

    def upsert_paper(self, paper, seen_at: str, scope: str) -> None:
        """`scope` e obrigatorio e nao tem default de proposito.

        Um default deixaria um chamador novo gravar linha sem escopo em
        silencio, e a coluna existe justamente para fatiar o acervo entre as
        duas literaturas. O ON CONFLICT tambem NAO atualiza `scope`: o primeiro
        escopo que descobre o paper fica com ele.
        """
        # first_seen so e gravado na insercao; ON CONFLICT nao o toca.
        self._conn.execute(
            """INSERT INTO papers
                 (arxiv_id, title, abstract, authors, categories, published,
                  first_seen, scope)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(arxiv_id) DO UPDATE SET
                 title=excluded.title, abstract=excluded.abstract""",
            (paper.arxiv_id, paper.title, paper.abstract, json.dumps(paper.authors),
             json.dumps(paper.categories), paper.published, seen_at, scope),
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

    def get_paper(self, arxiv_id: str) -> Paper | None:
        row = self._conn.execute(
            "SELECT * FROM papers WHERE arxiv_id=?", (arxiv_id,)
        ).fetchone()
        if row is None:
            return None
        return Paper(
            arxiv_id=row["arxiv_id"], title=row["title"], abstract=row["abstract"],
            authors=json.loads(row["authors"]),
            categories=json.loads(row["categories"]), published=row["published"],
        )

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

        `limit` nao-positivo devolve nada. Sem esta guarda, `LIMIT -1` no SQLite
        significa ILIMITADO: `RADAR_RECHECK_LIMIT=-1` -- que e como uma pessoa
        naturalmente tenta dizer "desliga a re-consulta" -- re-consultaria o
        banco INTEIRO num dia, uma busca no GitHub por paper guardado.
        """
        if limit <= 0:
            return []
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
                 (arxiv_id, judged_at, model, technique, familia, pratica,
                  ganho_eixo, ganho_fator, ganho_texto, resumo, porque)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (arxiv_id, judged_at, model, j.technique, j.familia, j.pratica,
             j.ganho_eixo, j.ganho_fator, j.ganho_texto, j.resumo, j.porque),
        )
        self._conn.commit()

    def latest_judgment(self, arxiv_id: str) -> Judgment | None:
        row = self._conn.execute(
            "SELECT * FROM judgments WHERE arxiv_id=? ORDER BY judged_at DESC LIMIT 1",
            (arxiv_id,)).fetchone()
        if row is None:
            return None
        return Judgment(
            technique=row["technique"], familia=row["familia"],
            pratica=row["pratica"], ganho_eixo=row["ganho_eixo"],
            ganho_fator=row["ganho_fator"], ganho_texto=row["ganho_texto"],
            resumo=row["resumo"], porque=row["porque"],
        )

    def papers_por_familia(self) -> dict[str, int]:
        """Contagem por familia sobre o julgamento MAIS RECENTE de cada paper.

        Contar a tabela inteira somaria o historico: um paper re-julgado
        apareceria duas vezes, e ainda contaria na familia antiga.
        """
        linhas = self._conn.execute("""
            SELECT j.familia, COUNT(*) FROM judgments j
            JOIN (SELECT arxiv_id, MAX(judged_at) m FROM judgments
                  GROUP BY arxiv_id) u
              ON j.arxiv_id = u.arxiv_id AND j.judged_at = u.m
            GROUP BY j.familia
        """)
        return {familia: n for familia, n in linhas}

    def site_data(self, hoje, delivered_on: str | None = None):
        """Monta o `SiteData` do acervo inteiro.

        `hoje` entra por argumento e nao de `date.today()`: o relogio dentro
        da leitura faria o teste mudar de resultado todo dia, e a pagina
        mentir sobre idade quando gerada com atraso.

        Papers sem julgamento nao viram ponto -- nao ha o que agrupar nem o
        que desenhar. Julgamento e sinal sao sempre os MAIS RECENTES.
        """
        from datetime import date as _date

        from .site_data import Ponto, SiteData

        limite_julgamento = "AND judged_at <= :dia" if delivered_on else ""
        limite_sinal = "AND checked_at <= :dia" if delivered_on else ""
        filtro_entrega = (
            "WHERE EXISTS (SELECT 1 FROM deliveries d "
            "WHERE d.arxiv_id = p.arxiv_id AND d.delivered_at = :dia)"
            if delivered_on else ""
        )
        linhas = self._conn.execute(f"""
            SELECT p.arxiv_id, p.title, p.published, p.scope,
                   j.familia, j.pratica, j.ganho_eixo, j.ganho_fator,
                   j.ganho_texto, j.resumo, j.technique, j.porque,
                   s.independent_impls, s.total_impls, s.stars_total,
                   s.citations, s.score
              FROM papers p
              JOIN judgments j ON j.arxiv_id = p.arxiv_id
              JOIN (SELECT arxiv_id, MAX(judged_at) m FROM judgments
                    WHERE 1 = 1 {limite_julgamento}
                    GROUP BY arxiv_id) uj
                ON uj.arxiv_id = j.arxiv_id AND uj.m = j.judged_at
              JOIN signals s ON s.arxiv_id = p.arxiv_id
              JOIN (SELECT arxiv_id, MAX(checked_at) m FROM signals
                    WHERE 1 = 1 {limite_sinal}
                    GROUP BY arxiv_id) us
                ON us.arxiv_id = s.arxiv_id AND us.m = s.checked_at
              {filtro_entrega}
        """, {"dia": delivered_on} if delivered_on else {})

        pontos = []
        for r in linhas:
            publicado = _date.fromisoformat(r["published"][:10])
            pontos.append(Ponto(
                arxiv_id=r["arxiv_id"], titulo=r["title"],
                familia=r["familia"], pratica=r["pratica"],
                independent_impls=r["independent_impls"],
                total_impls=r["total_impls"], stars_total=r["stars_total"],
                citations=r["citations"],
                idade_dias=(hoje - publicado).days,
                ganho_eixo=r["ganho_eixo"], ganho_fator=r["ganho_fator"],
                ganho_texto=r["ganho_texto"], resumo=r["resumo"],
                publicado=r["published"], score=r["score"] or 0.0,
                scope=r["scope"],
                technique=r["technique"], porque=r["porque"],
            ))
        dia = delivered_on or hoje.isoformat()
        destaque = max(pontos, key=lambda p: p.score, default=None)
        repos = self.repos_for(destaque.arxiv_id) if destaque else []
        limite_historico = "WHERE checked_at <= :dia" if delivered_on else ""
        params = {"dia": delivered_on} if delivered_on else {}
        dias_de_coleta = self._conn.execute(
            f"SELECT COUNT(DISTINCT checked_at) FROM signals {limite_historico}",
            params).fetchone()[0]
        # Compara as DUAS ultimas observacoes, nao maximo e minimo historicos.
        # Um paper que subiu uma vez e depois ficou parado nao pode continuar
        # contado como movimento em toda edicao futura.
        papers_que_moveram = self._conn.execute(f"""
            WITH ranked AS (
                SELECT arxiv_id, independent_impls,
                       ROW_NUMBER() OVER (
                           PARTITION BY arxiv_id ORDER BY checked_at DESC) AS rn
                  FROM signals
                  {limite_historico}
            ), pares AS (
                SELECT arxiv_id,
                       MAX(CASE WHEN rn = 1 THEN independent_impls END) atual,
                       MAX(CASE WHEN rn = 2 THEN independent_impls END) anterior
                  FROM ranked
                 WHERE rn <= 2
                 GROUP BY arxiv_id
            )
            SELECT COUNT(*) FROM pares
             WHERE anterior IS NOT NULL AND atual > anterior
        """, params).fetchone()[0]
        return SiteData(pontos=pontos, dia=dia, cortes=None, rechecked_total=0,
                        dias_de_coleta=dias_de_coleta,
                        papers_que_moveram=papers_que_moveram,
                        repos_do_destaque=repos)

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

    def delivery_days(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT delivered_at FROM deliveries "
            "ORDER BY delivered_at DESC")
        return [row["delivered_at"] for row in rows]

    def feed_items(self, limit: int = 100):
        """Um item por paper, na data da primeira entrega.

        Telegram e markdown registram o mesmo paper em canais diferentes. O
        RSS nao pode duplicar o item por causa disso, entao a data vem de
        `MIN(delivered_at)` e o agrupamento acontece antes dos joins.
        """
        from .feed import ItemFeed

        rows = self._conn.execute("""
            SELECT p.arxiv_id, p.title, d.delivered_at,
                   j.resumo, j.familia, j.pratica,
                   s.independent_impls, s.stars_total
              FROM papers p
              JOIN (SELECT arxiv_id, MIN(delivered_at) delivered_at
                      FROM deliveries GROUP BY arxiv_id) d
                ON d.arxiv_id = p.arxiv_id
              JOIN judgments j ON j.arxiv_id = p.arxiv_id
              JOIN (SELECT arxiv_id, MAX(judged_at) m FROM judgments
                    GROUP BY arxiv_id) uj
                ON uj.arxiv_id = j.arxiv_id AND uj.m = j.judged_at
              JOIN signals s ON s.arxiv_id = p.arxiv_id
              JOIN (SELECT arxiv_id, MAX(checked_at) m FROM signals
                    GROUP BY arxiv_id) us
                ON us.arxiv_id = s.arxiv_id AND us.m = s.checked_at
             ORDER BY d.delivered_at DESC, p.arxiv_id
             LIMIT ?
        """, (max(limit, 0),))
        return [ItemFeed(
            arxiv_id=r["arxiv_id"], titulo=r["title"], resumo=r["resumo"],
            familia=r["familia"], pratica=r["pratica"],
            independent_impls=r["independent_impls"],
            stars_total=r["stars_total"], entregue_em=r["delivered_at"],
        ) for r in rows]
