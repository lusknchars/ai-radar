import pytest
from pydantic import ValidationError

from radar.formulas import (MAX_SELECTOR_CANDIDATE_CHARS, FormulaCandidate, FormulaSelection,
                            FormulaSelectionItem, FormulaVariable,
                            FormulaWalkthrough, TechnicalCore, WorkedExample,
                            extract_formula_candidates, locate_candidate_excerpt,
                            rank_formula_candidates,
                            technical_core_from_selection,
                            verify_formula_selection, ground_technical_core)


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


def test_equation_candidates_preserve_exact_tex_and_nearby_context():
    tex = r"""
\section{Method}
We normalize attention before applying softmax.
\begin{equation}
S = \frac{QK^T}{\sqrt{d}}
\end{equation}
This keeps the logits in a useful range.
"""
    candidates = extract_formula_candidates({"main.tex": tex})
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.latex == r"S = \frac{QK^T}{\sqrt{d}}"
    assert candidate.environment == "equation"
    assert "normalize attention" in candidate.context_before
    assert "useful range" in candidate.context_after
    assert candidate.candidate_id.startswith("eq-")


def test_equation_candidate_ids_are_stable_for_the_same_source():
    files = {"main.tex": r"\[x^2 + y^2 = z^2\]"}
    first = extract_formula_candidates(files)
    second = extract_formula_candidates(files)
    assert [item.candidate_id for item in first] == [
        item.candidate_id for item in second]


def test_commented_equations_do_not_become_candidates():
    tex = "% \\begin{equation}invented = 1\\end{equation}\nPlain text."
    assert extract_formula_candidates({"main.tex": tex}) == []


def test_tex_without_display_equations_returns_no_candidates():
    assert extract_formula_candidates({"main.tex": "Only prose and $x$ inline."}) == []


def _candidate(**overrides):
    values = {
        "candidate_id": "eq-0123456789abcdef",
        "path": "main.tex",
        "environment": "equation",
        "latex": r"L = \\sum_i e_i",
        "context_before": "We minimize the following objective over all tokens.",
        "context_after": "This objective penalizes reconstruction error.",
    }
    return FormulaCandidate(**{**values, **overrides})


def test_selection_contract_contains_ids_and_roles_but_no_latex_field():
    schema = FormulaSelection.model_json_schema()
    item = schema["$defs"]["FormulaSelectionItem"]
    assert set(item["properties"]) == {"candidate_id", "role"}
    assert item["additionalProperties"] is False


def test_selection_rejects_duplicate_candidate_ids():
    item = FormulaSelectionItem(
        candidate_id="eq-0123456789abcdef", role="loss")
    with pytest.raises(ValidationError, match="repetir"):
        FormulaSelection(kind="formula", selected=[item, item])


def test_selection_verifier_rejects_an_id_the_model_never_received():
    selection = FormulaSelection(
        kind="formula",
        selected=[FormulaSelectionItem(
            candidate_id="eq-fedcba9876543210", role="loss")],
    )
    with pytest.raises(ValueError, match="desconhecido"):
        verify_formula_selection(selection, [_candidate()])


def test_candidate_ranking_prefers_contribution_context_and_limits_tokens():
    appendix = _candidate(
        candidate_id="eq-1111111111111111",
        context_before="Appendix proof of the lemma.")
    method = _candidate(
        candidate_id="eq-2222222222222222",
        context_before="We propose our method and objective.")
    assert rank_formula_candidates([appendix, method], limit=1) == [method]


def test_candidate_ranking_has_a_total_character_budget():
    candidates = [
        _candidate(
            candidate_id=f"eq-{index:016x}",
            latex="x" * 5_000,
            context_before="we propose an objective",
        )
        for index in range(10)
    ]
    selected = rank_formula_candidates(candidates)
    used = sum(
        len(item.latex + item.context_before + item.context_after + item.path)
        for item in selected
    )
    assert used <= MAX_SELECTOR_CANDIDATE_CHARS
    assert len(selected) < len(candidates)


def test_candidate_is_located_by_neighboring_prose_not_damaged_notation():
    candidate = _candidate()
    pages = {
        1: "Introduction and related work.",
        2: (
            "We minimize the following objective over all tokens. "
            "L equals unreadable PDF glyphs."
        ),
    }
    page, excerpt = locate_candidate_excerpt(candidate, pages)
    assert page == 2
    assert "following objective" in excerpt


def test_technical_core_copies_exact_candidate_latex_after_page_grounding():
    candidate = _candidate()
    selection = FormulaSelection(
        kind="formula",
        selected=[FormulaSelectionItem(
            candidate_id=candidate.candidate_id, role="loss")],
    )
    core = technical_core_from_selection(
        selection, [candidate],
        {3: "We minimize the following objective over all tokens in the batch."},
    )
    item = core.walkthroughs[0]
    assert item.status == "exact"
    assert item.latex == candidate.latex
    assert item.source_page == 3


def test_technical_core_downgrades_selected_formula_without_pdf_context():
    candidate = _candidate()
    selection = FormulaSelection(
        kind="formula",
        selected=[FormulaSelectionItem(
            candidate_id=candidate.candidate_id, role="loss")],
    )
    item = technical_core_from_selection(
        selection, [candidate], {1: "Unrelated page."}).walkthroughs[0]
    assert item.status == "extraction_failed"
    assert item.latex == ""


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
