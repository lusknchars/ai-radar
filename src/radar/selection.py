"""Shared editorial selections for the website and weekly newsletter."""
from __future__ import annotations

from datetime import date, timedelta

from .site_data import Ponto


def recent_papers(points: list[Ponto], today: date, *, days: int = 7) -> list[Ponto]:
    start = (today - timedelta(days=days - 1)).isoformat()
    return sorted(
        (p for p in points if start <= p.publicado <= today.isoformat()
         and p.pratica != "nao_aplica" and p.scope in {"inferencia", "agentes"}),
        key=lambda p: (p.publicado, p.score, p.arxiv_id), reverse=True,
    )


def implementation_papers(points: list[Ponto]) -> list[Ponto]:
    return sorted(
        (p for p in points if p.independent_impls > 0 and p.score > 0
         and p.pratica != "nao_aplica" and p.scope in {"inferencia", "agentes"}),
        key=lambda p: (p.score, p.publicado, p.arxiv_id), reverse=True,
    )
