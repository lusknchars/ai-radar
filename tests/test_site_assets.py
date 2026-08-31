from radar.site_assets import SCRIPT, STYLES


def test_assets_preservam_o_frontend_sem_build():
    assert ":root" in STYLES
    assert ".sheen-button" in STYLES
    assert "prefers-reduced-motion" in STYLES
    assert "@media (max-width:640px)" in STYLES


def test_script_so_aprimora_o_html_ja_renderizado():
    assert "data-mostrar-todos" in SCRIPT
    assert "data-ordenar" in SCRIPT
    assert "fetch(" not in SCRIPT
    assert "XMLHttpRequest" not in SCRIPT
