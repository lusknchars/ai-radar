"""Contrato de formulas verificaveis para relatorios profundos.

Este modulo descreve o que pode chegar ao artigo. Extracao de PDF/TeX,
selecao por modelo e calculo numerico ficam atras desta fronteira: o renderer
nao precisa adivinhar se uma formula existe ou se uma conta veio do paper.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FormulaStatus = Literal[
    "exact", "concept_only", "not_applicable", "extraction_failed",
]
FormulaRole = Literal[
    "baseline", "proposed_method", "loss", "metric", "complexity",
]
TechnicalCoreKind = Literal[
    "formula", "algorithm", "system", "evaluation_protocol", "concept", "none",
]

MIN_SOURCE_EXCERPT_CHARS = 24
MAX_FORMULA_CANDIDATES = 100
MAX_CANDIDATE_LATEX_CHARS = 6000
CONTEXT_CHARS = 900

_TEX_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
_EQUATION_ENV = re.compile(
    r"\\begin\{(?P<environment>equation\*?|align\*?|gather\*?|"
    r"multline\*?|eqnarray\*?|displaymath)\}"
    r"(?P<body>.*?)"
    r"\\end\{(?P=environment)\}",
    re.DOTALL,
)
_DISPLAY_PATTERNS = (
    ("display_brackets", re.compile(r"\\\[(?P<body>.*?)\\\]", re.DOTALL)),
    ("display_dollars", re.compile(r"\$\$(?P<body>.*?)\$\$", re.DOTALL)),
)


class FormulaVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=80)
    meaning: str = Field(min_length=1, max_length=320)
    unit: str = Field(default="", max_length=80)


class FormulaCandidate(BaseModel):
    """Trecho TeX exato que o seletor pode escolher apenas pelo ID."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^eq-[0-9a-f]{16}$")
    path: str = Field(min_length=1, max_length=500)
    environment: str = Field(min_length=1, max_length=40)
    latex: str = Field(min_length=1, max_length=MAX_CANDIDATE_LATEX_CHARS)
    context_before: str = Field(default="", max_length=CONTEXT_CHARS)
    context_after: str = Field(default="", max_length=CONTEXT_CHARS)


class WorkedExample(BaseModel):
    """Conta ilustrativa do AI Radar, nunca um resultado atribuido ao paper."""

    model_config = ConfigDict(extra="forbid")

    provenance: Literal["ai_radar_calculation"] = "ai_radar_calculation"
    inputs: dict[str, float] = Field(default_factory=dict)
    expression: str = Field(min_length=1, max_length=320)
    result: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=640)


class FormulaWalkthrough(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FormulaStatus
    role: FormulaRole | None = None
    latex: str = ""
    source_page: int | None = Field(default=None, ge=1)
    source_excerpt: str = Field(default="", max_length=640)
    plain_language: str = Field(min_length=1, max_length=1200)
    variables: list[FormulaVariable] = Field(default_factory=list)
    derivation_steps: list[str] = Field(default_factory=list)
    worked_example: WorkedExample | None = None
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_state(self) -> "FormulaWalkthrough":
        if not self.plain_language.strip():
            raise ValueError("plain_language precisa explicar o estado da formula")

        if self.status == "exact":
            if self.role is None:
                raise ValueError("role e obrigatorio para formula exact")
            if not self.latex.strip():
                raise ValueError("latex e obrigatorio para formula exact")
            if self.source_page is None:
                raise ValueError("source_page e obrigatorio para formula exact")
            if len(" ".join(self.source_excerpt.split())) < MIN_SOURCE_EXCERPT_CHARS:
                raise ValueError(
                    "source_excerpt precisa conter um trecho verificavel da pagina"
                )
            return self

        if self.latex.strip() or self.source_page is not None or self.source_excerpt.strip():
            raise ValueError(
                f"status={self.status!r} nao pode carregar latex, source_page "
                "ou source_excerpt"
            )
        if self.worked_example is not None:
            raise ValueError("worked_example exige uma formula exact")
        if self.variables or self.derivation_steps or self.assumptions:
            raise ValueError(
                f"status={self.status!r} nao pode carregar detalhes derivados "
                "de uma formula nao verificada"
            )
        return self


class TechnicalCore(BaseModel):
    """Mecanismo central do paper, inclusive quando ele nao e uma formula."""

    model_config = ConfigDict(extra="forbid")

    kind: TechnicalCoreKind
    summary: str = Field(min_length=1, max_length=1600)
    walkthroughs: list[FormulaWalkthrough] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_kind(self) -> "TechnicalCore":
        if not self.summary.strip():
            raise ValueError("summary precisa descrever o nucleo tecnico")
        if self.kind == "formula" and not self.walkthroughs:
            raise ValueError("kind='formula' exige ao menos um walkthrough")
        if self.kind != "formula" and any(
            item.status == "exact" for item in self.walkthroughs
        ):
            raise ValueError("formula exact exige TechnicalCore kind='formula'")
        return self


def _normalized_source(text: str) -> str:
    return " ".join(text.split()).casefold()


def _mask_tex_comments(text: str) -> str:
    return _TEX_COMMENT.sub(lambda match: " " * len(match.group(0)), text)


def _candidate_context(text: str, start: int, end: int) -> tuple[str, str]:
    before = " ".join(text[max(0, start - CONTEXT_CHARS):start].split())
    after = " ".join(text[end:end + CONTEXT_CHARS].split())
    return before[-CONTEXT_CHARS:], after[:CONTEXT_CHARS]


def extract_formula_candidates(
    tex_files: Mapping[str, str],
) -> list[FormulaCandidate]:
    """Extrai displays TeX sem corrigir, compilar ou interpretar a notacao."""
    candidates: list[FormulaCandidate] = []
    for path, text in sorted(tex_files.items()):
        masked = _mask_tex_comments(text)
        matches: list[tuple[int, int, str, str]] = []
        for match in _EQUATION_ENV.finditer(masked):
            body_start, body_end = match.span("body")
            matches.append((
                match.start(), match.end(), match.group("environment"),
                text[body_start:body_end].strip(),
            ))
        for environment, pattern in _DISPLAY_PATTERNS:
            for match in pattern.finditer(masked):
                body_start, body_end = match.span("body")
                matches.append((
                    match.start(), match.end(), environment,
                    text[body_start:body_end].strip(),
                ))

        previous_end = -1
        occurrence = 0
        for start, end, environment, latex in sorted(matches):
            if start < previous_end:
                continue
            previous_end = end
            if not latex or len(latex) > MAX_CANDIDATE_LATEX_CHARS:
                continue
            occurrence += 1
            digest = hashlib.sha256(
                f"{path}\0{occurrence}\0{environment}\0{latex}".encode("utf-8")
            ).hexdigest()[:16]
            before, after = _candidate_context(text, start, end)
            candidates.append(FormulaCandidate(
                candidate_id=f"eq-{digest}",
                path=path,
                environment=environment,
                latex=latex,
                context_before=before,
                context_after=after,
            ))
            if len(candidates) >= MAX_FORMULA_CANDIDATES:
                return candidates
    return candidates


def ground_technical_core(
    core: TechnicalCore, pages: Mapping[int, str],
) -> TechnicalCore:
    """Remove detalhes exatos cuja citacao nao existe na pagina indicada.

    O modulo de extracao ainda precisa provar a notacao contra a fonte TeX.
    Esta segunda trava impede que uma citacao de pagina incorreta chegue ao
    artigo mesmo quando um adaptador anterior falha.
    """
    grounded: list[FormulaWalkthrough] = []
    for item in core.walkthroughs:
        if item.status != "exact":
            grounded.append(item)
            continue
        excerpt = _normalized_source(item.source_excerpt)
        page = _normalized_source(pages.get(item.source_page, ""))
        if excerpt and excerpt in page:
            grounded.append(item)
            continue
        grounded.append(FormulaWalkthrough(
            status="extraction_failed",
            role=item.role,
            plain_language=(
                "A fórmula candidata não passou na verificação da página do "
                "PDF e foi removida antes da publicação."
            ),
        ))
    return core.model_copy(update={"walkthroughs": grounded})
