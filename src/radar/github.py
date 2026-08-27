"""Adaptador do GitHub.

Verificado no spike: `q="<arxiv_id>" in:readme` na busca de repositorios devolve
104 resultados para o ID do GPTQ, com a distincao autor/independente visivel.

LIMITACAO ESTRUTURAL: `in:readme` so alcanca o README da branch padrao.
Implementacao que cita o paper apenas no codigo, num notebook ou no artigo e
invisivel. O sinal e um piso, nao uma contagem.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable
from urllib.parse import urlencode

from .authorship import classify_repos
from .models import Paper, Repo, RepoClassification, Signal

SEARCH_ENDPOINT = "https://api.github.com/search/repositories"
VELOCITY_WINDOW_DAYS = 14


def build_search_url(arxiv_id: str, per_page: int = 100) -> str:
    return f"{SEARCH_ENDPOINT}?{urlencode({'q': f'\"{arxiv_id}\" in:readme', 'per_page': per_page})}"


def parse_search(payload: dict) -> list[Repo]:
    return [
        Repo(
            full_name=item["full_name"],
            owner=item["owner"]["login"],
            stars=item["stargazers_count"],
            created_at=item["created_at"],
        )
        for item in payload.get("items", [])
    ]


class GitHubClient:
    def __init__(self, fetch: Callable[[str], dict]) -> None:
        self._fetch = fetch

    def signal_with_repos(
        self, paper: Paper, today: date, citations: int = 0
    ) -> tuple[Signal, list[RepoClassification]]:
        repos = parse_search(self._fetch(build_search_url(paper.arxiv_id)))
        classifications = classify_repos(repos, paper.authors, paper.abstract)

        cutoff = today - timedelta(days=VELOCITY_WINDOW_DAYS)
        velocity = sum(
            1 for r in repos
            if datetime.fromisoformat(r.created_at.replace("Z", "+00:00")).date() >= cutoff
        )

        signal = Signal(
            total_impls=len(repos),
            independent_impls=sum(1 for c in classifications if not c.is_author),
            velocity_14d=velocity,
            stars_total=sum(r.stars for r in repos),
            citations=citations,
        )
        return signal, classifications

    def signal_for(self, paper: Paper, today: date, citations: int = 0) -> Signal:
        return self.signal_with_repos(paper, today, citations)[0]
