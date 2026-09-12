#!/usr/bin/env python3
"""Gera um relatorio profundo e republica o site sem rodar o radar diario."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from radar.config import (load_formula_model, load_formula_thinking,
                          load_database_path, load_kimi_base_url,
                          load_kimi_request_interval, load_llm_provider,
                          load_model, load_pdf_extractor)
from radar.formulas import extract_technical_core
from radar.fulltext import build_pdf_extractor, fetch_paper_source
from radar.judge import KimiFormulaSelector, KimiJudge
from radar.publish import publish_site
from radar.public_research_eval import load_evaluation_manifest
from radar.report import SourceProvenance, generate_report, save_report
from radar.store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gerar_relatorio")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--arxiv-id", action="append")
    target.add_argument(
        "--manifest", type=Path,
        help="generate every paper in a public research evaluation manifest",
    )
    target.add_argument(
        "--all", action="store_true",
        help="discover every paper currently in the archive",
    )
    parser.add_argument(
        "--plan", action="store_true",
        help="print the discovered queue without downloading PDFs or spending credits",
    )
    parser.add_argument(
        "--continue-on-error", action="store_true",
        help="record a per-paper failure and continue the discovered queue",
    )
    parser.add_argument(
        "--limit", type=int,
        help="limit manifest execution while testing the paid path",
    )
    parser.add_argument("--db", type=Path, default=load_database_path())
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    store = Store(args.db)
    store.init_schema()
    if args.all:
        target_ids = sorted(row["arxiv_id"] for row in store.all_papers())
        if not target_ids:
            raise SystemExit("the archive contains no papers")
    elif args.manifest:
        target_ids = [
            case.arxiv_id for case in load_evaluation_manifest(args.manifest).cases
        ]
    else:
        target_ids = args.arxiv_id
    if len(target_ids) != len(set(target_ids)):
        parser.error("target list contains duplicate arXiv IDs")
    if args.limit is not None:
        target_ids = target_ids[:args.limit]

    papers = []
    for arxiv_id in target_ids:
        paper = store.get_paper(arxiv_id)
        if paper is None:
            raise SystemExit(f"paper {arxiv_id!r} nao existe no acervo")
        papers.append(paper)

    pending = [
        paper for paper in papers
        if not (args.reports_dir / f"{paper.arxiv_id}.json").exists()
    ]
    if args.plan:
        print(f"Paperraft assistant queue: {len(pending)} pending of {len(papers)} papers")
        for index, paper in enumerate(pending, 1):
            print(f"{index:02d} {paper.arxiv_id} {paper.title}")
        return 0
    if not pending:
        publish_site(
            store, args.site_dir, datetime.now(timezone.utc).date(),
            reports_root=args.reports_dir,
        )
        if len(papers) == 1:
            print(
                "relatorio ja existia: "
                f"{args.reports_dir / f'{papers[0].arxiv_id}.json'}"
            )
        else:
            print(f"todos os {len(papers)} relatorios ja existiam")
        return 0

    if load_llm_provider() != "kimi":
        raise SystemExit("relatorios sob demanda usam RADAR_LLM_PROVIDER=kimi")
    model = load_model()
    api_key = os.environ.get("KIMI_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "KIMI_API_KEY is required to generate a new deep report"
        )
    common = {
        "request_interval": load_kimi_request_interval(),
        "base_url": load_kimi_base_url(),
    }
    judge = KimiJudge(
        api_key, model, **common,
    )
    selector = KimiFormulaSelector(
        api_key, load_formula_model(),
        thinking=load_formula_thinking(), **common,
    )
    failures = []
    try:
        for index, paper in enumerate(pending, 1):
            if index > 1:
                judge.wait_between_requests()
            try:
                source = fetch_paper_source(
                    paper.arxiv_id,
                    extractor=build_pdf_extractor(load_pdf_extractor()),
                )
                technical_core = extract_technical_core(source, paper, selector)
                source_provenance = SourceProvenance(
                    pdf_sha256=source.pdf_sha256,
                    extracted_text_sha256=hashlib.sha256(
                        source.full_text.encode("utf-8")).hexdigest(),
                    extractor=source.pdf_extraction_method,
                    pages=len(source.pdf_pages),
                    fallback_from=source.pdf_fallback_from,
                    fallback_reason=source.pdf_fallback_reason,
                )
                document = generate_report(
                    paper, source.full_text, judge,
                    technical_core=technical_core,
                    source_provenance=source_provenance,
                    provider="kimi", model=model)
                destination = args.reports_dir / f"{paper.arxiv_id}.json"
                save_report(document, args.reports_dir)
                print(f"relatorio {index}/{len(pending)} gerado: {destination}", flush=True)
            except Exception as exc:
                if not (args.continue_on_error or args.all):
                    raise
                failures.append(paper.arxiv_id)
                failure_path = args.reports_dir / "failures" / f"{paper.arxiv_id}.json"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(json.dumps({
                    "arxiv_id": paper.arxiv_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }, indent=2) + "\n", encoding="utf-8")
                print(f"relatorio {index}/{len(pending)} falhou: {paper.arxiv_id} ({type(exc).__name__})", flush=True)
    finally:
        selector.close()
        judge.close()

    publish_site(
        store, args.site_dir, datetime.now(timezone.utc).date(),
        reports_root=args.reports_dir,
    )
    print(f"site republicado: {args.site_dir / 'index.html'}")
    if failures:
        print(f"falhas registradas: {len(failures)} em {args.reports_dir / 'failures'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
