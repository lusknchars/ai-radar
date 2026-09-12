from datetime import date
from pathlib import Path
import shutil

import pytest

from scripts import build_vercel


@pytest.mark.parametrize("explicit,production,preview,expected", [
    ("https://radar.example/", "project.vercel.app", "preview.vercel.app", "https://radar.example"),
    ("", "project.vercel.app", "preview.vercel.app", "https://project.vercel.app"),
    ("", "", "preview.vercel.app", "https://preview.vercel.app"),
])
def test_uses_preferred_production_domain(monkeypatch, explicit, production, preview, expected):
    monkeypatch.setenv("RADAR_SITE_URL", explicit)
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", production)
    monkeypatch.setenv("VERCEL_URL", preview)
    assert build_vercel.production_url() == expected


@pytest.mark.parametrize("url", ["", "https://radar.example/ai-radar", "https://a:b@radar.example", "https://radar.example?x=1"])
def test_rejects_missing_or_non_root_domain(monkeypatch, url):
    monkeypatch.setenv("RADAR_SITE_URL", url)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)
    with pytest.raises(ValueError, match="root URL"):
        build_vercel.production_url()


@pytest.mark.parametrize("environment", ["production", "preview"])
def test_builds_root_domain_archive_without_changing_source(tmp_path, monkeypatch, environment):
    source = Path(__file__).resolve().parents[1] / "data" / "radar-state.db"
    database = tmp_path / "publication.db"
    shutil.copyfile(source, database)
    original = database.read_bytes()
    monkeypatch.setattr(build_vercel, "ROOT", tmp_path)
    monkeypatch.setenv("RADAR_SITE_URL", "https://radar.example")
    monkeypatch.setenv("VERCEL_ENV", environment)
    output = tmp_path / "dist"
    output.mkdir()
    (output / "obsolete.html").write_text("old build")

    build_vercel.build(database=database, output=output, reports=tmp_path / "reports", as_of=date(2026, 9, 11))

    assert database.read_bytes() == original
    assert not (output / "obsolete.html").exists()
    assert not list(output.rglob("*.db"))
    home = (output / "index.html").read_text()
    assert 'src="/assets/d3-7.9.0.min.js"' in home
    assert (output / "assets" / "site.css").is_file()
    assert 'href="https://radar.example/"' in home
    assert 'href="/papers/' in home
    assert '/ai-radar/' not in home
    assert (output / "assets" / "social-card.png").is_file()
    assert 'https://radar.example/papers/' in (output / "sitemap.xml").read_text()
    assert 'https://radar.example/' in (output / "feed.xml").read_text()
    assert ('Disallow: /' in (output / "robots.txt").read_text()) == (environment == "preview")
    for page in output.rglob("*.html"):
        assert ('name="robots" content="noindex, nofollow"' in page.read_text()) == (environment == "preview")


def test_missing_database_fails_without_replacing_existing_build(tmp_path, monkeypatch):
    monkeypatch.setattr(build_vercel, "ROOT", tmp_path)
    monkeypatch.setenv("RADAR_SITE_URL", "https://radar.example")
    output = tmp_path / "dist"
    output.mkdir()
    (output / "index.html").write_text("existing build")
    with pytest.raises(FileNotFoundError, match="Publication database"):
        build_vercel.build(database=tmp_path / "missing.db", output=output,
                           reports=tmp_path / "reports", as_of=date(2026, 9, 11))
    assert (output / "index.html").read_text() == "existing build"
