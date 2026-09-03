"""Small public discovery files generated with the static publication."""
from __future__ import annotations

from collections.abc import Iterable
from xml.sax.saxutils import escape

from .config import PublicConfig


def _public_url(config: PublicConfig, resource: str = "") -> str:
    resource = resource.lstrip("/")
    return f"{config.site_url}/{resource}" if resource else f"{config.site_url}/"


def render_sitemap(
    config: PublicConfig,
    *,
    paper_ids: Iterable[str],
    report_ids: Iterable[str],
    edition_days: Iterable[str],
) -> str:
    """Return one canonical URL per public HTML page."""
    urls = [
        _public_url(config),
        _public_url(config, "about.html"),
        _public_url(config, "edicoes/"),
    ]
    urls.extend(
        _public_url(config, f"edicoes/{day}/")
        for day in sorted(set(edition_days), reverse=True)
    )
    urls.extend(
        _public_url(config, f"papers/{arxiv_id}/")
        for arxiv_id in sorted(set(paper_ids))
    )
    urls.extend(
        _public_url(config, f"reports/{arxiv_id}/")
        for arxiv_id in sorted(set(report_ids))
    )
    body = "\n".join(
        f"  <url><loc>{escape(url)}</loc></url>" for url in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def render_robots(config: PublicConfig) -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {_public_url(config, 'sitemap.xml')}\n"
    )
