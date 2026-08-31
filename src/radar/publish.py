"""Publicacao atomica do acervo e dos relatorios estaticos."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from .feed import MAX_ITEMS as RSS_MAX_ITEMS, render_rss
from .report import load_report
from .site import render_about, render_editions, render_report, render_site
from .store import Store


def publish_site(
    store: Store,
    root: Path,
    today: date,
    *,
    cuts: dict[str, int] | None = None,
    reports_root: Path | None = None,
) -> None:
    """Escreve todos os artefatos servidos pelo GitHub Pages.

    Nao coleta, julga nem chama rede. Assim um relatorio pode republicar o
    acervo existente sem acionar o pipeline diario ou gastar outro lote.
    """
    root.mkdir(parents=True, exist_ok=True)
    reports_root = reports_root or root.parent / "reports"
    reports = [load_report(path) for path in sorted(reports_root.glob("*.json"))]
    available_reports = {document.arxiv_id for document in reports}

    data = store.site_data(today)
    if cuts is not None:
        data = replace(data, cortes=cuts)
    days = store.delivery_days()

    (root / "index.html").write_text(
        render_site(data, report_ids=available_reports), encoding="utf-8")
    (root / "feed.xml").write_text(
        render_rss(store.feed_items(limit=RSS_MAX_ITEMS), dia=today.isoformat()),
        encoding="utf-8")
    (root / "about.html").write_text(
        render_about(today.isoformat(), papers=len(data.pontos), edicoes=len(days)),
        encoding="utf-8")

    editions_root = root / "edicoes"
    editions_root.mkdir(parents=True, exist_ok=True)
    (editions_root / "index.html").write_text(
        render_editions(days, today.isoformat()), encoding="utf-8")
    for day in days:
        destination = editions_root / day
        destination.mkdir(parents=True, exist_ok=True)
        edition_data = store.site_data(date.fromisoformat(day), delivered_on=day)
        (destination / "index.html").write_text(
            render_site(edition_data, edicao=True, report_ids=available_reports),
            encoding="utf-8")

    for document in reports:
        destination = root / "reports" / document.arxiv_id
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "index.html").write_text(
            render_report(document), encoding="utf-8")
