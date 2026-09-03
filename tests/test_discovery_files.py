from radar.config import PublicConfig
from radar.discovery_files import render_robots, render_sitemap


CONFIG = PublicConfig(
    repository="reader/research-radar",
    base_path="/research-radar",
    site_url="https://reader.github.io/research-radar",
)


def test_sitemap_contains_canonical_public_pages_once():
    sitemap = render_sitemap(
        CONFIG,
        paper_ids=["2608.22222", "2608.11111", "2608.11111"],
        report_ids=["2608.11111"],
        edition_days=["2026-09-02", "2026-09-01"],
    )

    assert sitemap.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert sitemap.count(
        "https://reader.github.io/research-radar/papers/2608.11111/"
    ) == 1
    assert "https://reader.github.io/research-radar/reports/2608.11111/" in sitemap
    assert "https://reader.github.io/research-radar/edicoes/2026-09-02/" in sitemap
    assert "https://reader.github.io/research-radar/about.html" in sitemap


def test_robots_points_to_the_forks_sitemap():
    assert render_robots(CONFIG) == (
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: https://reader.github.io/research-radar/sitemap.xml\n"
    )
