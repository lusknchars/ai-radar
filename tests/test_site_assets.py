import base64

from radar.font_assets import (BE_VIETNAM_PRO_LIGHT_WOFF2_BASE64,
                               BE_VIETNAM_PRO_MEDIUM_WOFF2_BASE64)
from radar.site_assets import BACKGROUND_SCRIPT, REPORT_SCRIPT, SCRIPT, STYLES


def test_assets_preservam_o_frontend_sem_build():
    assert ":root" in STYLES
    assert ".sheen-button" in STYLES
    assert "prefers-reduced-motion" in STYLES
    assert "@media (max-width:640px)" in STYLES


def test_be_vietnam_pro_light_e_medium_sao_woff2_embutidos_sem_requisicao_remota():
    for b64 in (BE_VIETNAM_PRO_LIGHT_WOFF2_BASE64, BE_VIETNAM_PRO_MEDIUM_WOFF2_BASE64):
        assert base64.b64decode(b64)[:4] == b"wOF2"
    assert STYLES.count("@font-face{font-family:'Be Vietnam Pro'") == 2
    assert "font-weight:300;font-display:swap" in STYLES
    assert "font-weight:500;font-display:swap" in STYLES
    assert "format('woff2')" in STYLES
    assert '--display:"Be Vietnam Pro"' in STYLES
    assert '--sans:"Be Vietnam Pro"' in STYLES
    assert "fonts.gstatic.com" not in STYLES
    assert "Electrolize" not in STYLES


def test_o_corpo_e_light_e_a_enfase_e_medium_sem_peso_sintetizado():
    """So dois pesos existem: tudo em sans/display resolve para 300 ou 500."""
    assert "font-size:15px;font-weight:300;" in STYLES
    assert "strong,b{font-weight:500}" in STYLES
    for proibido in ("font-weight:520", "font-weight:550", "font-weight:600;font-variant",
                     "font:600 12px", "font-weight:400;line-height:.94"):
        assert proibido not in STYLES


def test_subtitulos_usam_a_fonte_display_selecionada():
    assert ".hero-deck,.article-deck,.sub,.chart-card-head h3+p" in STYLES
    assert "font-family:var(--display)" in STYLES


def test_barra_do_relatorio_afasta_conteudo_das_bordas():
    """Texto e botoes nao podem encostar nas regras da barra sticky."""
    assert ".report-bar{" in STYLES
    assert "margin:0 0 24px;padding:11px 16px;" in STYLES


def test_script_so_aprimora_o_html_ja_renderizado():
    assert "data-mostrar-todos" in SCRIPT
    assert "data-ordenar" in SCRIPT
    assert "fetch(" not in SCRIPT
    assert "XMLHttpRequest" not in SCRIPT


def test_fundo_dither_e_local_e_respeita_preferencias_do_leitor():
    assert "getContext('2d'" in BACKGROUND_SCRIPT
    assert "0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5" in BACKGROUND_SCRIPT
    assert "[[185,45,93], [255,140,130], [255,226,214]]" in BACKGROUND_SCRIPT
    assert "var speed = 2.3" in BACKGROUND_SCRIPT
    assert "var intensity = .95" in BACKGROUND_SCRIPT
    assert "var waveScale = 6" in BACKGROUND_SCRIPT
    assert "prefers-reduced-motion" in BACKGROUND_SCRIPT
    assert "visibilitychange" in BACKGROUND_SCRIPT
    assert "fetch(" not in BACKGROUND_SCRIPT
    assert "XMLHttpRequest" not in BACKGROUND_SCRIPT


def test_relatorio_marca_progresso_sem_buscar_codigo_externo():
    assert "data-report-progress" in REPORT_SCRIPT
    assert "IntersectionObserver" in REPORT_SCRIPT
    assert "aria-current" in REPORT_SCRIPT
    assert "fetch(" not in REPORT_SCRIPT
    assert "XMLHttpRequest" not in REPORT_SCRIPT


def test_formula_longa_rola_no_mobile_sem_quebrar_o_artigo():
    assert ".formula-latex" in STYLES
    assert "overflow-x:auto" in STYLES
    assert ".technical-core-summary{grid-template-columns:1fr" in STYLES
