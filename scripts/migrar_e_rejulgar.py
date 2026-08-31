"""Migra o seed antigo e re-julga o acervo com o schema atual.

Sem ``--execute`` este comando apenas inspeciona o banco. A execução paga faz
três verificações ao vivo antes de tocar no arquivo, cria uma cópia verificada,
migra dentro de uma transação e só então envia o lote completo.

Uso:
    python scripts/migrar_e_rejulgar.py
    RADAR_LLM_PROVIDER=kimi python scripts/migrar_e_rejulgar.py --canary 20
    python scripts/migrar_e_rejulgar.py --execute
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from radar.config import (load_kimi_base_url, load_kimi_request_interval,  # noqa: E402
                          load_llm_provider, load_model)
from radar.judge import (Judge, JudgmentSchema, KimiJudge,  # noqa: E402
                         collect_batch_results, submit_batch, wait_for_batch)
from radar.models import Judgment, Paper  # noqa: E402

DEFAULT_DB = ROOT / "data" / "radar.db"
DEFAULT_CHECKPOINT = ROOT / "data" / "rejudge-kimi.jsonl"
PRAZO_LOTE = 4 * 60 * 60
CANARY_SIZE = 20
TABELAS_PRESERVADAS = ("papers", "signals", "repos", "deliveries")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (*TABELAS_PRESERVADAS, "judgments")
    }


def status(db: Path) -> int:
    if not db.exists():
        print(f"banco ausente: {db}")
        return 2
    conn = sqlite3.connect(db)
    counts = _counts(conn)
    old = "summary" in _columns(conn, "judgments")
    print(f"banco: {db}")
    print(f"schema: {'antigo, precisa migrar' if old else 'atual'}")
    for table, count in counts.items():
        print(f"{table}: {count}")
    return 0


def _papers(conn: sqlite3.Connection) -> list[Paper]:
    return [
        Paper(
            arxiv_id=row[0], title=row[1], abstract=row[2],
            authors=json.loads(row[3]), categories=json.loads(row[4]),
            published=row[5],
        )
        for row in conn.execute(
            "SELECT arxiv_id, title, abstract, authors, categories, published "
            "FROM papers ORDER BY arxiv_id")
    ]


def _live_smoke(client, model: str, papers: list[Paper]) -> None:
    """Exercita os dois caminhos que a suite offline nao consegue provar."""
    sample = next((p for p in papers if p.arxiv_id == "2205.14135"), papers[0])
    one = Judge(client, model).judge_one(sample)
    print(f"smoke direto: {one.familia} | {one.pratica} | {one.ganho_fator}")

    batch = submit_batch(client, papers[:2], model)
    print(f"smoke batch: {batch.id}")
    if not wait_for_batch(client, batch.id, timeout_seconds=30 * 60):
        raise RuntimeError("o lote de fumaça não terminou em 30 minutos")
    results = collect_batch_results(client.messages.batches.results(batch.id))
    if set(results) != {p.arxiv_id for p in papers[:2]}:
        raise RuntimeError(
            f"o lote de fumaça devolveu {sorted(results)}, esperados "
            f"{[p.arxiv_id for p in papers[:2]]}")
    print("smoke batch: 2/2")


def _checkpoint_results(
    path: Path, *, provider: str, model: str,
) -> dict[str, Judgment]:
    if not path.exists():
        return {}
    results: dict[str, Judgment] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("provider") != provider or record.get("model") != model:
            raise RuntimeError(
                f"checkpoint {path} mistura provedor/modelo na linha {line_number}"
            )
        schema = JudgmentSchema.model_validate(record["judgment"])
        results[record["arxiv_id"]] = Judgment(**schema.model_dump())
    return results


def _append_checkpoint(
    path: Path, arxiv_id: str, judgment: Judgment, *, provider: str, model: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "arxiv_id": arxiv_id,
        "provider": provider,
        "model": model,
        "judgment": asdict(judgment),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def collect_kimi_with_checkpoint(
    papers: list[Paper], judge: KimiJudge, checkpoint: Path, *, model: str,
    limit: int | None = None,
) -> dict[str, Judgment]:
    """Retoma um re-julgamento direto sem pagar outra vez pelo que terminou."""
    results = _checkpoint_results(checkpoint, provider="kimi", model=model)
    target = papers if limit is None else papers[:max(limit, 0)]
    pending = [paper for paper in target if paper.arxiv_id not in results]
    for index, paper in enumerate(pending, 1):
        if results:
            judge.wait_between_requests()
        judgment = judge.judge_one(paper)
        _append_checkpoint(
            checkpoint, paper.arxiv_id, judgment, provider="kimi", model=model)
        results[paper.arxiv_id] = judgment
        print(f"Kimi: {len(results)}/{len(target)} ({paper.arxiv_id})", flush=True)
    return {paper.arxiv_id: results[paper.arxiv_id]
            for paper in target if paper.arxiv_id in results}


def _print_canary(papers: list[Paper], results: dict[str, Judgment]) -> None:
    for paper in papers:
        judgment = results.get(paper.arxiv_id)
        if judgment is None:
            print(f"{paper.arxiv_id}\tFALHOU")
            continue
        print(f"\n{paper.arxiv_id} | {paper.title}")
        print(f"{judgment.familia} | {judgment.pratica} | {judgment.ganho_eixo}")
        print(f"{judgment.technique}: {judgment.resumo}")
        print(f"porque: {judgment.porque}")


def _canary_papers(papers: list[Paper], count: int) -> list[Paper]:
    """Amostra o acervo inteiro em vez de pegar apenas os IDs mais antigos."""
    count = min(max(count, 0), len(papers))
    if count == 0:
        return []
    if count == 1:
        return [papers[len(papers) // 2]]
    return [
        papers[round(index * (len(papers) - 1) / (count - 1))]
        for index in range(count)
    ]


def _backup(db: Path, expected: dict[str, int]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.name}.bak-{stamp}")
    shutil.copy2(db, backup)
    copied = sqlite3.connect(backup)
    actual = _counts(copied)
    copied.close()
    if actual != expected:
        raise RuntimeError(f"cópia não confere: {actual} != {expected}")
    print(f"backup verificado: {backup}")
    return backup


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Preserva o ativo caro e substitui apenas o julgamento obsoleto."""
    if "summary" not in _columns(conn, "judgments"):
        raise RuntimeError("o banco não está no schema antigo esperado")
    with conn:
        conn.execute(
            "ALTER TABLE papers ADD COLUMN scope TEXT NOT NULL "
            "DEFAULT 'inferencia'")

        conn.execute("ALTER TABLE signals RENAME TO signals_old")
        conn.execute("""
            CREATE TABLE signals (
                arxiv_id TEXT NOT NULL REFERENCES papers(arxiv_id),
                checked_at TEXT NOT NULL,
                total_impls INTEGER NOT NULL,
                independent_impls INTEGER NOT NULL,
                velocity_14d INTEGER NOT NULL,
                stars_total INTEGER NOT NULL,
                citations INTEGER,
                score REAL,
                PRIMARY KEY (arxiv_id, checked_at)
            )
        """)
        conn.execute("INSERT INTO signals SELECT * FROM signals_old")
        conn.execute("DROP TABLE signals_old")

        conn.execute("DROP TABLE judgments")
        conn.execute("""
            CREATE TABLE judgments (
                arxiv_id TEXT NOT NULL REFERENCES papers(arxiv_id),
                judged_at TEXT NOT NULL,
                model TEXT NOT NULL,
                technique TEXT NOT NULL,
                familia TEXT NOT NULL,
                pratica TEXT NOT NULL,
                ganho_eixo TEXT NOT NULL,
                ganho_fator REAL,
                ganho_texto TEXT NOT NULL,
                resumo TEXT NOT NULL,
                porque TEXT NOT NULL,
                PRIMARY KEY (arxiv_id, judged_at)
            )
        """)


def _write_judgments(conn: sqlite3.Connection, results, model: str, day: str) -> None:
    rows = [
        (arxiv_id, day, model, j.technique, j.familia, j.pratica,
         j.ganho_eixo, j.ganho_fator, j.ganho_texto, j.resumo, j.porque)
        for arxiv_id, j in results.items()
    ]
    with conn:
        conn.executemany(
            "INSERT INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows)


def _gate(conn: sqlite3.Connection) -> bool:
    total = conn.execute("SELECT COUNT(*) FROM judgments").fetchone()[0]
    print(f"julgamentos: {total}")
    ok = total > 0
    for field in ("pratica", "familia"):
        print(f"\n--- {field} ---")
        for value, count in conn.execute(
                f"SELECT {field}, COUNT(*) FROM judgments GROUP BY 1 ORDER BY 2 DESC"):
            pct = count / total
            failed = ((field == "pratica" and pct > 0.45)
                      or (field == "familia" and value == "outro" and pct > 0.10))
            ok = ok and not failed
            print(f"{value:32} {count:5} {pct:6.1%}"
                  f"{'  REPROVA' if failed else ''}")
    gains = conn.execute(
        "SELECT COUNT(*) FROM judgments WHERE ganho_eixo != 'nenhum'").fetchone()[0]
    coverage = gains / total
    gains_ok = coverage >= 0.35
    print(f"\ncobertura de ganho: {gains}/{total} = {coverage:.1%}"
          f"{'  REPROVA' if not gains_ok else ''}")
    return ok and gains_ok


def _validate_database(db: Path):
    conn = sqlite3.connect(db)
    before = _counts(conn)
    if "summary" not in _columns(conn, "judgments"):
        conn.close()
        print("o banco já usa o schema atual; nenhuma alteração feita")
        return None
    papers = _papers(conn)
    if not papers:
        conn.close()
        print("banco sem papers; nenhuma alteração feita")
        return None
    return conn, before, papers


def canary(db: Path, checkpoint: Path, count: int) -> int:
    provider = load_llm_provider()
    if provider != "kimi":
        print("--canary usa Kimi; defina RADAR_LLM_PROVIDER=kimi")
        return 2
    if not os.environ.get("KIMI_API_KEY"):
        print("KIMI_API_KEY ausente; nenhuma alteração feita")
        return 2
    validated = _validate_database(db)
    if validated is None:
        return 2
    conn, _, papers = validated
    conn.close()
    model = load_model()
    judge = KimiJudge(
        os.environ["KIMI_API_KEY"], model,
        request_interval=load_kimi_request_interval(),
        base_url=load_kimi_base_url(),
    )
    sample = _canary_papers(papers, count)
    try:
        results = collect_kimi_with_checkpoint(
            sample, judge, checkpoint, model=model)
    finally:
        judge.close()
    _print_canary(sample, results)
    print(f"canario: {len(results)}/{len(sample)}; banco nao foi alterado")
    return 0 if len(results) == len(sample) else 3


def execute(db: Path, checkpoint: Path = DEFAULT_CHECKPOINT) -> int:
    provider = load_llm_provider()
    secret_name = "KIMI_API_KEY" if provider == "kimi" else "ANTHROPIC_API_KEY"
    if not os.environ.get(secret_name):
        print(f"{secret_name} ausente; nenhuma alteração feita")
        return 2

    validated = _validate_database(db)
    if validated is None:
        return 2
    conn, before, papers = validated

    model = load_model()
    results: dict[str, Judgment] | None = None
    client = None
    if provider == "kimi":
        existing = _checkpoint_results(checkpoint, provider="kimi", model=model)
        expected_canary = min(CANARY_SIZE, len(papers))
        canary_ids = {
            paper.arxiv_id for paper in _canary_papers(papers, expected_canary)
        }
        if not canary_ids <= set(existing):
            conn.close()
            print(
                f"canario ausente: rode '--canary {expected_canary}' e revise "
                "o resultado antes de --execute; banco nao foi alterado"
            )
            return 2
        judge = KimiJudge(
            os.environ["KIMI_API_KEY"], model,
            request_interval=load_kimi_request_interval(),
            base_url=load_kimi_base_url(),
        )
        try:
            results = collect_kimi_with_checkpoint(
                papers, judge, checkpoint, model=model)
        finally:
            judge.close()
        if len(results) != len(papers):
            conn.close()
            print(
                f"checkpoint incompleto: {len(results)} de {len(papers)}; "
                "banco nao foi alterado"
            )
            return 3
    else:
        client = anthropic.Anthropic()
        _live_smoke(client, model, papers)

    backup = _backup(db, before)

    try:
        migrate_schema(conn)
        after_migration = _counts(conn)
        for table in TABELAS_PRESERVADAS:
            if after_migration[table] != before[table]:
                raise RuntimeError(
                    f"{table} mudou: {before[table]} -> {after_migration[table]}")
        if after_migration["judgments"] != 0:
            raise RuntimeError("judgments não ficou vazio depois da migração")

        if provider == "anthropic":
            batch = submit_batch(client, papers, model)
            print(f"lote completo: {batch.id} | {len(papers)} papers")
            if not wait_for_batch(client, batch.id, timeout_seconds=PRAZO_LOTE):
                raise RuntimeError("o lote completo não terminou em quatro horas")
            results = collect_batch_results(client.messages.batches.results(batch.id))
        assert results is not None
        if len(results) != len(papers):
            raise RuntimeError(
                f"lote incompleto: {len(results)} de {len(papers)} julgamentos")
        _write_judgments(
            conn, results, model, datetime.now(timezone.utc).date().isoformat())
    except Exception:
        conn.close()
        shutil.copy2(backup, db)
        print(f"falha: banco original restaurado de {backup}")
        raise

    passed = _gate(conn)
    conn.close()
    if not passed:
        shutil.copy2(backup, db)
        print(f"gate reprovou: banco original restaurado de {backup}")
        return 3
    print(f"backup preservado em: {backup}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--canary", type=int, metavar="N",
                        help="julga N papers com Kimi, salva checkpoint e nao toca no banco")
    parser.add_argument("--execute", action="store_true",
                        help="faz chamadas pagas, migra e re-julga o banco")
    args = parser.parse_args(argv)
    if args.canary is not None and args.execute:
        parser.error("use --canary e --execute em comandos separados")
    if args.canary is not None:
        return canary(args.db, args.checkpoint, args.canary)
    return execute(args.db, args.checkpoint) if args.execute else status(args.db)


if __name__ == "__main__":
    raise SystemExit(main())
