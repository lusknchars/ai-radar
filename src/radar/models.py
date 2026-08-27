"""Tipos compartilhados. Nenhum IO, nenhuma dependencia externa alem de stdlib."""
from __future__ import annotations

import re
from dataclasses import dataclass

VALID_VERDICTS = frozenset({"sim", "sim_com_ressalva", "nao"})
_VERSIONED = re.compile(r"v\d+$")


@dataclass(frozen=True)
class Paper:
    arxiv_id: str                 # chave canonica, SEM sufixo de versao
    title: str
    abstract: str
    authors: tuple[str, ...]
    categories: tuple[str, ...]
    published: str                # ISO date

    def __post_init__(self) -> None:
        if _VERSIONED.search(self.arxiv_id):
            raise ValueError(
                f"arxiv_id {self.arxiv_id!r} carrega versao; use a chave canonica "
                f"sem sufixo para que v1 e v2 nao virem entradas distintas"
            )
        # frozen=True protege reatribuicao de atributo, nao o conteudo de uma
        # lista. Sem coagir para tupla, Paper aceita mutacao interna E explode
        # em TypeError ao ser hasheado -- justamente o oposto do que arxiv_id
        # existe para fazer, que e servir de chave de deduplicacao.
        # Aceitar lista na construcao e devolver tupla mantem os chamadores
        # simples sem abrir mao da imutabilidade.
        object.__setattr__(self, "authors", tuple(self.authors))
        object.__setattr__(self, "categories", tuple(self.categories))


@dataclass(frozen=True)
class Repo:
    full_name: str
    owner: str
    stars: int
    created_at: str        # ISO datetime


@dataclass(frozen=True)
class RepoClassification:
    repo: Repo
    is_author: bool
    reason: str | None     # qual regra disparou; auditavel no markdown


@dataclass(frozen=True)
class Signal:
    total_impls: int
    independent_impls: int
    velocity_14d: int
    stars_total: int
    citations: int = 0


@dataclass(frozen=True)
class ScoreResult:
    value: float | None    # None quando cortado no portao
    gated_by: str | None   # 'estrelas' | 'citacoes' | None

    @property
    def passed(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class Judgment:
    technique: str
    summary: str
    runs_on_3090: str
    rationale: str

    def __post_init__(self) -> None:
        if self.runs_on_3090 not in VALID_VERDICTS:
            raise ValueError(
                f"runs_on_3090={self.runs_on_3090!r} invalido; "
                f"use um de {sorted(VALID_VERDICTS)}"
            )
