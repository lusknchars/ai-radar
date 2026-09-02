"""Contrato de formulas verificaveis para relatorios profundos.

Este modulo descreve o que pode chegar ao artigo. Extracao de PDF/TeX,
selecao por modelo e calculo numerico ficam atras desta fronteira: o renderer
nao precisa adivinhar se uma formula existe ou se uma conta veio do paper.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Literal, Protocol

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
MAX_SELECTOR_CANDIDATE_CHARS = 24_000
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


class FormulaSelectionItem(BaseModel):
    """A decisao barata do seletor; nenhuma notacao pode ser reescrita aqui."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^eq-[0-9a-f]{16}$")
    role: FormulaRole


class FormulaSelection(BaseModel):
    """Saida fechada do K2.6: tipo do nucleo e IDs, sem prosa ou LaTeX."""

    model_config = ConfigDict(extra="forbid")

    kind: TechnicalCoreKind
    selected: list[FormulaSelectionItem] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_selection_shape(self) -> "FormulaSelection":
        ids = [item.candidate_id for item in self.selected]
        if len(ids) != len(set(ids)):
            raise ValueError("o seletor nao pode repetir candidate_id")
        if self.kind == "formula" and not self.selected:
            raise ValueError("kind='formula' exige ao menos um candidate_id")
        if self.kind != "formula" and self.selected:
            raise ValueError("candidate_id so e permitido para kind='formula'")
        return self


class FormulaSelector(Protocol):
    def select(
        self, paper, candidates: list[FormulaCandidate],
    ) -> FormulaSelection: ...


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


_CONTRIBUTION_TERMS = (
    "we propose", "our method", "objective", "loss", "complexity",
    "algorithm", "latency", "throughput", "memory", "metric",
)
_AUXILIARY_TERMS = ("appendix", "proof", "lemma", "theorem")


def rank_formula_candidates(
    candidates: list[FormulaCandidate], *, limit: int = 30,
) -> list[FormulaCandidate]:
    """Reduz custo sem deixar o modelo alterar ou fabricar candidatos.

    O teto por quantidade sozinho nao basta: trinta ambientes ``align`` no
    limite de tamanho excederiam com folga a janela de custo planejada.
    """
    if limit < 1:
        raise ValueError("limit precisa ser >= 1")

    def score(item: FormulaCandidate) -> int:
        context = (
            f"{item.context_before} {item.context_after} {item.latex}"
        ).casefold()
        return (
            sum(3 for term in _CONTRIBUTION_TERMS if term in context)
            - sum(2 for term in _AUXILIARY_TERMS if term in context)
        )

    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda pair: (-score(pair[1]), pair[0]))
    selected: list[FormulaCandidate] = []
    used_chars = 0
    for _, item in indexed:
        item_chars = len(
            item.latex + item.context_before + item.context_after + item.path
        )
        if used_chars + item_chars > MAX_SELECTOR_CANDIDATE_CHARS:
            continue
        selected.append(item)
        used_chars += item_chars
        if len(selected) == limit:
            break
    return selected


def verify_formula_selection(
    selection: FormulaSelection,
    candidates: list[FormulaCandidate],
) -> list[tuple[FormulaSelectionItem, FormulaCandidate]]:
    """Resolve apenas IDs presentes no conjunto exato enviado ao modelo."""
    available = {item.candidate_id: item for item in candidates}
    resolved: list[tuple[FormulaSelectionItem, FormulaCandidate]] = []
    for item in selection.selected:
        candidate = available.get(item.candidate_id)
        if candidate is None:
            raise ValueError(
                f"seletor devolveu candidate_id desconhecido: {item.candidate_id}"
            )
        resolved.append((item, candidate))
    return resolved


_SOURCE_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def locate_candidate_excerpt(
    candidate: FormulaCandidate, pages: Mapping[int, str],
) -> tuple[int, str] | None:
    """Localiza uma frase vizinha do TeX no PDF sem comparar a formula.

    A extracao de PDF costuma destruir a notacao, mas preserva a prosa ao
    redor. Casar uma sequencia de palavras dessa prosa fornece pagina e trecho
    auditavel sem alegar que o texto extraido do PDF preservou a equacao.
    """
    context_words = [
        match.group(0).casefold()
        for match in _SOURCE_WORD.finditer(
            f"{candidate.context_before} {candidate.context_after}"
        )
    ]
    if len(context_words) < 6:
        return None
    page_tokens: dict[int, tuple[list[str], list[tuple[int, int]]]] = {}
    for number, text in pages.items():
        matches = list(_SOURCE_WORD.finditer(text))
        page_tokens[number] = (
            [match.group(0).casefold() for match in matches],
            [match.span() for match in matches],
        )

    for window in range(min(14, len(context_words)), 5, -1):
        for start in range(len(context_words) - window + 1):
            needle = context_words[start:start + window]
            for page_number, text in pages.items():
                words, spans = page_tokens[page_number]
                for offset in range(len(words) - window + 1):
                    if words[offset:offset + window] != needle:
                        continue
                    excerpt_start = spans[offset][0]
                    excerpt_end = spans[offset + window - 1][1]
                    excerpt = " ".join(text[excerpt_start:excerpt_end].split())
                    if len(excerpt) >= MIN_SOURCE_EXCERPT_CHARS:
                        return page_number, excerpt[:640]
    return None


_ROLE_EXPLANATIONS: dict[FormulaRole, str] = {
    "baseline": "Esta equacao formaliza o baseline usado na comparacao.",
    "proposed_method": "Esta equacao formaliza o mecanismo proposto pelo paper.",
    "loss": "Esta equacao define a funcao de perda otimizada pelo metodo.",
    "metric": "Esta equacao define a metrica usada para avaliar o resultado.",
    "complexity": "Esta equacao explicita o custo ou a complexidade do metodo.",
}


def technical_core_from_selection(
    selection: FormulaSelection,
    candidates: list[FormulaCandidate],
    pages: Mapping[int, str],
) -> TechnicalCore:
    """Constroi o nucleo usando somente LaTeX preservado pelo extrator."""
    if selection.kind != "formula":
        labels = {
            "algorithm": "O nucleo tecnico e uma sequencia de passos, nao uma nova formula.",
            "system": "O nucleo tecnico esta na composicao do sistema, nao numa nova formula.",
            "evaluation_protocol": (
                "O nucleo tecnico e o protocolo de avaliacao, nao uma nova formula."
            ),
            "concept": "O paper contribui um conceito sem notacao central verificavel.",
            "none": "O nucleo tecnico nao foi classificado com seguranca.",
        }
        return TechnicalCore(kind=selection.kind, summary=labels[selection.kind])

    walkthroughs: list[FormulaWalkthrough] = []
    for selected, candidate in verify_formula_selection(selection, candidates):
        location = locate_candidate_excerpt(candidate, pages)
        if location is None:
            walkthroughs.append(FormulaWalkthrough(
                status="extraction_failed",
                role=selected.role,
                plain_language=(
                    "A equacao foi selecionada na fonte TeX, mas sua prosa "
                    "vizinha nao foi localizada com seguranca no PDF."
                ),
            ))
            continue
        page, excerpt = location
        walkthroughs.append(FormulaWalkthrough(
            status="exact",
            role=selected.role,
            latex=candidate.latex,
            source_page=page,
            source_excerpt=excerpt,
            plain_language=_ROLE_EXPLANATIONS[selected.role],
        ))
    return TechnicalCore(
        kind="formula",
        summary=(
            "Equacoes centrais escolhidas por identificador e copiadas sem "
            "alteracao da fonte TeX oficial."
        ),
        walkthroughs=walkthroughs,
    )


def extract_technical_core(source, paper, selector: FormulaSelector) -> TechnicalCore:
    """Orquestra extracao, selecao barata e verificacao deterministica."""
    candidates = rank_formula_candidates(extract_formula_candidates(source.tex))
    selection = selector.select(paper, candidates)
    return technical_core_from_selection(selection, candidates, source.pages)


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
