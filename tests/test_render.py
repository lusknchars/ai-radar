import pytest

from radar.models import Judgment, Paper, Signal
from radar.render import RadarItem, render_markdown, render_telegram

P = Paper(arxiv_id="2508.11111", title="Fused INT4 Kernels", abstract="A",
          authors=["A B"], categories=["cs.LG"], published="2026-08-20")
J = Judgment(technique="Kernel INT4 fundido",
             summary="Satura banda de memoria em batch unitario.",
             runs_on_3090="sim", rationale="INT4 roda nativo em Ampere.")


def item(score=0.53, delta=None, judgment=J, paper=P):
    return RadarItem(paper=paper, judgment=judgment,
                     signal=Signal(4, 4, 3, 60), score=score, delta=delta)


def test_telegram_output_has_no_emoji():
    text = render_telegram([item()])
    assert all(ord(c) < 0x2190 for c in text), "push do Telegram nao leva emoji"


def test_telegram_shows_technique_summary_numbers_and_verdict():
    text = render_telegram([item()])
    assert "Kernel INT4 fundido" in text
    assert "Satura banda" in text
    assert "4 impls independentes" in text
    assert "Roda na 3090: sim" in text
    assert "arxiv.org/abs/2508.11111" in text


def test_telegram_uses_delta_wording_for_a_revival():
    text = render_telegram([item(delta={"independent_from": 2, "independent_to": 9,
                                        "stars_from": 300, "stars_to": 340, "days": 21})])
    assert "2 -> 9 impls independentes em 21 dias" in text
    assert "4 impls independentes" not in text


def test_telegram_of_an_empty_list_is_empty():
    """Silencio e resultado valido. Nada de mandar item fraco por ter o que mandar."""
    assert render_telegram([]) == ""


def test_telegram_never_renders_more_than_three():
    with pytest.raises(ValueError, match="teto"):
        render_telegram([item() for _ in range(4)])


def test_markdown_lists_radar_items_first():
    md = render_markdown("2026-08-27", radar=[item()], feed=[], cuts={})
    assert md.index("## Radar") < md.index("## Feed")


def test_markdown_exposes_the_authorship_reason():
    md = render_markdown("2026-08-27", radar=[item()], feed=[],
                         cuts={}, repos={"2508.11111": [
                             {"full_name": "a/b", "is_author": 1,
                              "is_author_reason": "sobrenome", "stars": 10}]})
    assert "a/b" in md
    assert "sobrenome" in md


def test_markdown_reports_cuts_with_counts_and_reasons():
    md = render_markdown("2026-08-27", radar=[], feed=[],
                         cuts={"ja_estourou": 4, "abaixo_do_piso": 11, "ja_entregue": 2})
    assert "ja_estourou" in md and "4" in md
    assert "abaixo_do_piso" in md and "11" in md


def test_markdown_states_explicitly_when_nothing_was_cut():
    md = render_markdown("2026-08-27", radar=[item()], feed=[], cuts={})
    assert "Nenhum corte" in md


def test_markdown_never_omits_the_cuts_section():
    """Truncar em silencio faz o radar parecer que cobriu tudo."""
    md = render_markdown("2026-08-27", radar=[item()], feed=[], cuts={})
    assert "## Cortes" in md


def test_markdown_includes_the_full_feed_with_verdicts():
    """A linha inteira, nao um pedaco dela: `"sim" in md` casa com quase
    qualquer saida, inclusive com o veredito faltando e o resumo no lugar
    errado."""
    feed_item = item(paper=Paper(arxiv_id="2508.99999", title="Outro", abstract="A",
                                 authors=[], categories=["cs.LG"], published="2026-08-21"))
    md = render_markdown("2026-08-27", radar=[], feed=[feed_item], cuts={})
    assert ("- **Kernel INT4 fundido** — Satura banda de memoria em batch unitario. "
            "(3090: sim) arxiv.org/abs/2508.99999") in md


def test_markdown_feed_carries_the_verdict_of_each_item():
    """Contraprova: o veredito renderizado e o do item, nao um literal fixo."""
    nao_roda = Judgment(technique="Kernel FP8", summary="Depende de FP8.",
                        runs_on_3090="nao", rationale="Ampere nao tem FP8.")
    md = render_markdown("2026-08-27", radar=[], cuts={},
                         feed=[item(judgment=nao_roda)])
    assert "(3090: nao)" in md
    assert "(3090: sim)" not in md


def test_recheck_section_lists_only_what_moved():
    mexeu = item(delta={"independent_from": 2, "independent_to": 9,
                        "stars_from": 300, "stars_to": 340, "days": 21})
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={},
                         rechecked=[mexeu], rechecked_total=30)
    assert "30 papers re-consultados" in md
    assert "1 com movimento" in md
    assert "2 -> 9 impls independentes em 21 dias" in md


def test_recheck_section_is_explicit_when_nothing_moved():
    """Silencio ambiguo faz parecer que o trabalho nao foi feito."""
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={},
                         rechecked=[], rechecked_total=30)
    assert "30 papers re-consultados, nenhum com movimento" in md


def test_recheck_section_is_absent_when_no_recheck_ran():
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={})
    assert "## Re-consulta" not in md


def test_recheck_section_shows_the_current_score():
    mexeu = item(score=0.4032,
                 delta={"independent_from": 2, "independent_to": 9,
                        "stars_from": 300, "stars_to": 340, "days": 21})
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={},
                         rechecked=[mexeu], rechecked_total=5)
    assert "score 0.4032" in md
