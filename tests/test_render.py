import pytest

from radar.models import Judgment, Paper, Signal
from radar.render import RadarItem, render_markdown, render_telegram

P = Paper(arxiv_id="2508.11111", title="Fused INT4 Kernels", abstract="A",
          authors=["A B"], categories=["cs.LG"], published="2026-08-20")
J = Judgment(technique="Kernel INT4 fundido", familia="quantizacao",
             pratica="testar", ganho_eixo="velocidade", ganho_fator=2.3,
             ganho_texto="2.3x sobre o kernel FP16",
             resumo="Satura banda de memoria em batch unitario.",
             porque="Roda em infra pequena; o ganho depende do modelo.")


def item(score=0.53, delta=None, judgment=J, paper=P):
    return RadarItem(paper=paper, judgment=judgment,
                     signal=Signal(4, 4, 3, 60), score=score, delta=delta)


def test_telegram_output_has_no_emoji():
    text = render_telegram([item()])
    assert all(ord(c) < 0x2190 for c in text), "push do Telegram nao leva emoji"


def test_telegram_shows_technique_resumo_numbers_and_pratica():
    text = render_telegram([item()])
    assert "Kernel INT4 fundido" in text
    assert "Satura banda" in text
    assert "4 impls independentes" in text
    assert "Pratica: testar" in text
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
            "(quantizacao · testar) arxiv.org/abs/2508.99999") in md


def test_markdown_feed_carries_the_verdict_of_each_item():
    """Contraprova: o veredito renderizado e o do item, nao um literal fixo."""
    fora = Judgment(technique="Kernel FP8", familia="kernels_e_atencao",
                    pratica="nao_aplica", ganho_eixo="nenhum", ganho_fator=None,
                    ganho_texto="", resumo="Depende de FP8.",
                    porque="Fora do que o leitor faz.")
    md = render_markdown("2026-08-27", radar=[], cuts={},
                         feed=[item(judgment=fora)])
    assert "nao_aplica" in md
    assert "· testar)" not in md


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


# --- Tarefa 7 do plano do segundo escopo ---

def test_o_item_mostra_a_pratica_e_nao_o_hardware():
    saida = render_markdown("2026-08-29", [item()], [], {})
    assert "testar" in saida
    assert "3090" not in saida


def test_o_ganho_alegado_aparece_rotulado_como_alegado():
    """O rotulo e inegociavel: numero de abstract apresentado como medicao e
    exatamente o hype de que este projeto existe para fugir."""
    saida = render_markdown("2026-08-29", [item()], [], {})
    assert "2.3" in saida
    assert "alegado" in saida.lower()


def test_sem_ganho_nao_ha_rotulo_de_alegacao():
    j = Judgment(technique="T", familia="outro", pratica="observar",
                 ganho_eixo="nenhum", ganho_fator=None, ganho_texto="",
                 resumo="R", porque="P")
    saida = render_markdown("2026-08-29", [item(judgment=j)], [], {})
    assert "alegado" not in saida.lower()


def test_julgamento_sem_familia_e_recusado_na_construcao():
    """Os defaults temporarios das tarefas 4 a 6 caem aqui.

    Enquanto existiam, `Judgment(technique="t")` produzia um julgamento com
    familia 'outro' e pratica 'observar' sem ninguem ter decidido isso. A
    auto-revisao do plano marcou esta como a divida mais provavel de
    sobreviver; este teste e o que a mata.
    """
    with pytest.raises(TypeError):
        Judgment(technique="so o rotulo")


# --- Tarefa 9 do plano do segundo escopo ---

def _dia(radar=(), feed=(), cuts=None):
    from radar.pipeline import DayResult
    cuts = cuts or {}
    return DayResult(radar=list(radar), feed=list(feed), cuts=cuts,
                     markdown=render_markdown("2026-08-29", list(radar),
                                              list(feed), cuts),
                     push="")


def test_a_composicao_traz_as_duas_secoes_na_ordem():
    from radar.render import compose_day
    saida = compose_day("2026-08-29", {"inferencia": _dia(radar=[item()]),
                                       "agentes": _dia(radar=[item()])})
    assert saida.index("Inferência") < saida.index("Agentes")


def test_escopo_com_radar_vazio_ainda_aparece():
    """Um escopo silencioso e informacao: sumir com a secao faria parecer que
    o escopo nao rodou."""
    from radar.render import compose_day
    saida = compose_day("2026-08-29", {"inferencia": _dia(radar=[item()]),
                                       "agentes": _dia()})
    assert "Agentes" in saida
    assert "Nenhum item passou o piso hoje." in saida


def test_a_composicao_nao_perde_corte_de_nenhum_escopo():
    from radar.render import compose_day
    saida = compose_day("2026-08-29", {
        "inferencia": _dia(cuts={"abaixo_do_piso": 7}),
        "agentes": _dia(cuts={"ja_conhecido": 3}),
    })
    assert "abaixo_do_piso" in saida
    assert "ja_conhecido" in saida


def test_o_cabecalho_do_dia_aparece_uma_vez_so():
    from radar.render import compose_day
    saida = compose_day("2026-08-29", {"inferencia": _dia(), "agentes": _dia()})
    assert saida.count("# Radar — 2026-08-29") == 1


def test_os_titulos_internos_descem_um_nivel():
    """O rotulo de escopo entra como h2; sem rebaixar os de dentro, `## Radar`
    viraria irmao de `## Inferência` quando na verdade e filho."""
    from radar.render import compose_day
    saida = compose_day("2026-08-29", {"inferencia": _dia(radar=[item()])})
    assert "## Inferência" in saida
    assert "### Radar" in saida
    assert "\n## Radar" not in saida
    assert "#### 1. Kernel INT4 fundido" in saida


def test_escopo_ausente_do_dicionario_nao_gera_secao():
    from radar.render import compose_day
    saida = compose_day("2026-08-29", {"inferencia": _dia()})
    assert "Agentes" not in saida
