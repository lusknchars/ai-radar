#!/usr/bin/env python3
"""Gera um relatorio profundo e republica o site sem rodar o radar diario."""
from __future__ import annotations

import argparse
import hashlib
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
    if args.manifest:
        target_ids = [
            case.arxiv_id for case in load_evaluation_manifest(args.manifest).cases
        ]
    else:
        target_ids = args.arxiv_id
    if len(target_ids) != len(set(target_ids)):
        parser.error("target list contains duplicate arXiv IDs")
    if args.limit is not None:
        target_ids = target_ids[:args.limit]

    store = Store(args.db)
    store.init_schema()
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
    try:
        for index, paper in enumerate(pending, 1):
            if index > 1:
                judge.wait_between_requests()
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
            print(
                f"relatorio {index}/{len(pending)} gerado: {destination}",
                flush=True,
            )
    finally:
        selector.close()
        judge.close()

    publish_site(
        store, args.site_dir, datetime.now(timezone.utc).date(),
        reports_root=args.reports_dir,
    )
    print(f"site republicado: {args.site_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
