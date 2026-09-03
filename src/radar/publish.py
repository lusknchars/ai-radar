"""Publicacao atomica do acervo e dos relatorios estaticos."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from shutil import copyfile

from .config import PublicConfig, load_public_config
from .discovery_files import render_robots, render_sitemap
from .feed import MAX_ITEMS as RSS_MAX_ITEMS, render_rss
from .public_research import build_research_page
from .report import load_report
from .site import (render_about, render_editions, render_report,
                   render_research_page, render_site)
from .site_assets import BACKGROUND_SCRIPT, STYLES
from .store import Store

VENDOR_ASSETS = tuple(
    Path(__file__).resolve().parents[2] / "assets" / "vendor" / name
    for name in ("d3-7.9.0.min.js", "observable-plot-0.6.17.min.js")
)


def publish_site(
    store: Store,
    root: Path,
    today: date,
    *,
    cuts: dict[str, int] | None = None,
    reports_root: Path | None = None,
    public_config: PublicConfig | None = None,
) -> None:
    """Escreve todos os artefatos servidos pelo GitHub Pages.

    Nao coleta, julga nem chama rede. Assim um relatorio pode republicar o
    acervo existente sem acionar o pipeline diario ou gastar outro lote.
    """
    public_config = public_config or load_public_config()
    root.mkdir(parents=True, exist_ok=True)
    assets_root = root / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    for asset in VENDOR_ASSETS:
        copyfile(asset, assets_root / asset.name)
    (assets_root / "site.css").write_text(STYLES, encoding="utf-8")
    (assets_root / "background.js").write_text(
        BACKGROUND_SCRIPT, encoding="utf-8")
    reports_root = reports_root or root.parent / "reports"
    reports = [load_report(path) for path in sorted(reports_root.glob("*.json"))]
    available_reports = {document.arxiv_id for document in reports}
    reports_by_id = {document.arxiv_id: document for document in reports}

    data = store.site_data(today)
    if cuts is not None:
        data = replace(data, cortes=cuts)
    days = store.delivery_days()

    (root / "index.html").write_text(
        render_site(
            data, report_ids=available_reports, public_config=public_config,
        ), encoding="utf-8")
    (root / "feed.xml").write_text(
        render_rss(
            store.feed_items(limit=RSS_MAX_ITEMS), dia=today.isoformat(),
            site_url=public_config.site_url,
        ),
        encoding="utf-8")
    (root / "about.html").write_text(
        render_about(
            today.isoformat(), papers=len(data.pontos), edicoes=len(days),
            public_config=public_config,
        ),
        encoding="utf-8")

    editions_root = root / "edicoes"
    editions_root.mkdir(parents=True, exist_ok=True)
    (editions_root / "index.html").write_text(
        render_editions(days, today.isoformat(), public_config), encoding="utf-8")
    for day in days:
        destination = editions_root / day
        destination.mkdir(parents=True, exist_ok=True)
        edition_data = store.site_data(date.fromisoformat(day), delivered_on=day)
        (destination / "index.html").write_text(
            render_site(
                edition_data, edicao=True, report_ids=available_reports,
                public_config=public_config,
            ),
            encoding="utf-8")

    papers_root = root / "papers"
    for point in data.pontos:
        page = build_research_page(
            point, as_of=today.isoformat(),
            report=reports_by_id.get(point.arxiv_id),
        )
        destination = papers_root / point.arxiv_id
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "index.html").write_text(
            render_research_page(page, public_config), encoding="utf-8")
        (destination / "index.json").write_text(
            page.model_dump_json(indent=2), encoding="utf-8")

    for document in reports:
        destination = root / "reports" / document.arxiv_id
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "index.html").write_text(
            render_report(document, public_config), encoding="utf-8")

    (root / "sitemap.xml").write_text(
        render_sitemap(
            public_config,
            paper_ids=(point.arxiv_id for point in data.pontos),
            report_ids=available_reports,
            edition_days=days,
        ),
        encoding="utf-8",
    )
    (root / "robots.txt").write_text(
        render_robots(public_config), encoding="utf-8",
    )
    (root / ".nojekyll").write_text("", encoding="utf-8")
