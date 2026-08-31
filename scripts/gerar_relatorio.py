#!/usr/bin/env python3
"""Gera um relatorio profundo e republica o site sem rodar o radar diario."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from radar.config import (load_kimi_base_url, load_kimi_request_interval,
                          load_llm_provider, load_model)
from radar.fulltext import fetch_full_text
from radar.judge import KimiJudge
from radar.publish import publish_site
from radar.report import generate_report, save_report
from radar.store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gerar_relatorio")
    parser.add_argument("--arxiv-id", required=True)
    parser.add_argument("--db", type=Path, default=Path("data/radar.db"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    args = parser.parse_args(argv)

    store = Store(args.db)
    store.init_schema()
    paper = store.get_paper(args.arxiv_id)
    if paper is None:
        raise SystemExit(f"paper {args.arxiv_id!r} nao existe no acervo")

    destination = args.reports_dir / f"{paper.arxiv_id}.json"
    if destination.exists():
        publish_site(
            store, args.site_dir, datetime.now(timezone.utc).date(),
            reports_root=args.reports_dir,
        )
        print(f"relatorio ja existia: {destination}")
        return 0

    if load_llm_provider() != "kimi":
        raise SystemExit("relatorios sob demanda usam RADAR_LLM_PROVIDER=kimi")
    model = load_model()
    judge = KimiJudge(
        os.environ.get("KIMI_API_KEY", ""), model,
        request_interval=load_kimi_request_interval(),
        base_url=load_kimi_base_url(),
    )
    try:
        full_text = fetch_full_text(paper.arxiv_id)
        document = generate_report(
            paper, full_text, judge, provider="kimi", model=model)
    finally:
        judge.close()

    save_report(document, args.reports_dir)
    publish_site(
        store, args.site_dir, datetime.now(timezone.utc).date(),
        reports_root=args.reports_dir,
    )
    print(f"relatorio gerado: {destination}")
    print(f"pagina: {args.site_dir / 'reports' / paper.arxiv_id / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
