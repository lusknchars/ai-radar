"""Heuristica para separar o repo dos autores das reimplementacoes de terceiros.

Esta e a maior fonte de erro do score, e o erro e assimetrico e conhecido:
laboratorio publicando sob nome de organizacao nao casa por sobrenome, e uma
reimplementacao de terceiro que por acaso seja a mais antiga e a mais estrelada
e marcada como autor por engano.

Nao ha correcao automatica. A mitigacao e registrar QUAL regra disparou, para
que toda decisao seja auditavel no markdown do dia.
"""
from __future__ import annotations

import unicodedata
from typing import Sequence

from .models import Repo, RepoClassification

MIN_SURNAME_FOR_SUBSTRING = 4


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


def _surnames(authors: Sequence[str]) -> list[str]:
    out = []
    for author in authors:
        parts = author.split()
        if parts:
            out.append(normalize(parts[-1]))
    return [s for s in out if s]


def _matches_surname(owner: str, surnames: list[str]) -> bool:
    norm_owner = normalize(owner)
    for surname in surnames:
        if len(surname) >= MIN_SURNAME_FOR_SUBSTRING:
            if surname in norm_owner:
                return True
        elif surname == norm_owner:
            return True
    return False


def classify_repos(
    repos: list[Repo], authors: Sequence[str], abstract: str
) -> list[RepoClassification]:
    if not repos:
        return []

    surnames = _surnames(authors)
    norm_abstract = abstract.lower()

    oldest = min(repos, key=lambda r: r.created_at)
    most_starred = max(repos, key=lambda r: r.stars)
    presumed_official = oldest.full_name if oldest.full_name == most_starred.full_name else None

    out: list[RepoClassification] = []
    for repo in repos:
        reason: str | None = None
        if _matches_surname(repo.owner, surnames):
            reason = "sobrenome"
        elif repo.full_name.lower() in norm_abstract:
            reason = "citado_no_abstract"
        elif repo.full_name == presumed_official:
            reason = "mais_antigo_e_mais_estrelado"
        out.append(RepoClassification(repo=repo, is_author=reason is not None, reason=reason))
    return out
