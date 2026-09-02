import pytest
from pydantic import ValidationError

from radar.formulas import (FormulaVariable, FormulaWalkthrough, TechnicalCore,
                            WorkedExample, ground_technical_core)


def exact_formula(**overrides):
    values = {
        "status": "exact",
        "role": "proposed_method",
        "latex": r"S = QK^T / \sqrt{d}",
        "source_page": 4,
        "source_excerpt": (
            "We compute scaled attention scores by dividing QK transpose "
            "by the square root of d."
        ),
        "plain_language": "Normaliza o produto entre consultas e chaves.",
        "variables": [
            FormulaVariable(symbol="d", meaning="dimensao da cabeca"),
        ],
        "derivation_steps": ["Calcule QK^T.", "Divida por sqrt(d)."],
        "worked_example": None,
        "assumptions": ["Q e K usam a mesma dimensao interna."],
    }
    return FormulaWalkthrough(**{**values, **overrides})


def test_exact_formula_requires_a_source_location():
    with pytest.raises(ValidationError, match="source_page"):
        exact_formula(source_page=None)


def test_exact_formula_requires_a_meaningful_source_excerpt():
    with pytest.raises(ValidationError, match="source_excerpt"):
        exact_formula(source_excerpt="too short")


@pytest.mark.parametrize(
    "status", ["concept_only", "not_applicable", "extraction_failed"])
def test_non_exact_states_cannot_carry_source_mathematics(status):
    with pytest.raises(ValidationError, match="nao pode carregar"):
        FormulaWalkthrough(
            status=status,
            role=None,
            latex="x = 1",
            source_page=2,
            source_excerpt="A source excerpt long enough to look grounded.",
            plain_language="A formula exata nao esta disponivel.",
        )


def test_worked_example_is_explicitly_an_ai_radar_calculation():
    example = WorkedExample(
        inputs={"d": 64},
        expression="sqrt(64)",
        result="8",
        explanation="A escala usada no exemplo seria oito.",
    )
    formula = exact_formula(worked_example=example)
    assert formula.worked_example is not None
    assert formula.worked_example.provenance == "ai_radar_calculation"


def test_non_exact_state_cannot_claim_a_worked_example():
    with pytest.raises(ValidationError, match="worked_example"):
        FormulaWalkthrough(
            status="concept_only",
            role="metric",
            latex="",
            source_page=None,
            source_excerpt="",
            plain_language="O PDF nomeia a metrica, mas perdeu a notacao.",
            worked_example=WorkedExample(
                inputs={"n": 2},
                expression="2 + 2",
                result="4",
                explanation="Exemplo ilustrativo.",
            ),
        )


def test_non_exact_state_cannot_claim_derived_formula_details():
    with pytest.raises(ValidationError, match="detalhes derivados"):
        FormulaWalkthrough(
            status="extraction_failed",
            plain_language="A notação não foi recuperada.",
            derivation_steps=["Divida por oito."],
        )


def test_grounding_downgrades_formula_absent_from_its_claimed_page():
    core = TechnicalCore(
        kind="formula", summary="Escala o produto.",
        walkthroughs=[exact_formula()],
    )
    grounded = ground_technical_core(
        core, {4: "This page discusses another equation entirely."})
    item = grounded.walkthroughs[0]
    assert item.status == "extraction_failed"
    assert item.latex == ""
    assert item.source_page is None
    assert item.worked_example is None


def test_grounding_keeps_formula_when_excerpt_exists_on_the_page():
    formula = exact_formula()
    core = TechnicalCore(
        kind="formula", summary="Escala o produto.", walkthroughs=[formula])
    grounded = ground_technical_core(
        core, {4: f"Context before. {formula.source_excerpt} Context after."})
    assert grounded.walkthroughs == [formula]


def test_formula_technical_core_requires_a_walkthrough():
    with pytest.raises(ValidationError, match="walkthrough"):
        TechnicalCore(
            kind="formula",
            summary="A mudanca central e uma nova funcao de perda.",
            walkthroughs=[],
        )


def test_non_formula_technical_core_makes_absence_explicit():
    core = TechnicalCore(
        kind="system",
        summary="O ganho vem do escalonador e nao de uma nova equacao.",
        walkthroughs=[],
    )
    assert core.kind == "system"
    assert core.walkthroughs == []


def test_non_formula_technical_core_rejects_exact_formulae():
    with pytest.raises(ValidationError, match="kind='formula'"):
        TechnicalCore(
            kind="algorithm",
            summary="Uma sequencia de passos discretos.",
            walkthroughs=[exact_formula()],
        )
