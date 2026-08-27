"""Adaptador do arXiv.

PEGADINHA VERIFICADA: a API so responde em HTTPS e com User-Agent explicito.
Em HTTP ela retorna corpo vazio com status 200 -- falha silenciosa, o pior tipo.
O endpoint abaixo esta travado por teste.

Uma query por termo, unidas em codigo, em vez de uma query booleana gigante:
a API trata mal query longa com aspas aninhadas, e a uniao em codigo e trivial
de depurar.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Callable
from urllib.parse import urlencode

from .config import ScopeConfig
from .models import Paper

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
USER_AGENT = "ai-radar/0.1 (personal research digest)"
ETIQUETTE_SLEEP_SECONDS = 3

_ATOM = {"a": "http://www.w3.org/2005/Atom"}


def build_query(term: str, scope: ScopeConfig) -> str:
    cats = " OR ".join(f"cat:{c}" for c in scope.categories)
    return f'({cats}) AND abs:"{term}"'


def build_url(term: str, scope: ScopeConfig, max_results: int = 100) -> str:
    params = {
        "search_query": build_query(term, scope),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    return f"{ARXIV_ENDPOINT}?{urlencode(params)}"


def _text(node, path: str) -> str:
    found = node.find(path, _ATOM)
    return " ".join(found.text.split()) if found is not None and found.text else ""


def parse_feed(xml_text: str) -> list[Paper]:
    """Parseia sem filtrar. Filtro de escopo e do cliente, nao do parser."""
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall("a:entry", _ATOM):
        raw_id = _text(entry, "a:id").rsplit("/", 1)[-1]
        canonical = raw_id.split("v")[0] if "v" in raw_id else raw_id
        papers.append(Paper(
            arxiv_id=canonical,
            title=_text(entry, "a:title"),
            abstract=_text(entry, "a:summary"),
            authors=[" ".join(n.text.split())
                     for n in entry.findall("a:author/a:name", _ATOM) if n.text],
            categories=[c.get("term") for c in entry.findall("a:category", _ATOM)],
            published=_text(entry, "a:published")[:10],
        ))
    return papers


class ArxivClient:
    def __init__(
        self,
        fetch: Callable[[str], str],
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._fetch = fetch
        self._sleep = sleep

    def recent(self, scope: ScopeConfig, max_results: int = 100) -> list[Paper]:
        allowed = set(scope.categories)
        seen: dict[str, Paper] = {}
        for index, term in enumerate(scope.terms):
            if index:
                self._sleep(ETIQUETTE_SLEEP_SECONDS)
            # build_url fica FORA do try: se a construcao da query tiver bug
            # nosso, queremos que exploda, nao que seja engolida como falha
            # do arXiv.
            url = build_url(term, scope, max_results)
            try:
                parsed = parse_feed(self._fetch(url))
            except Exception:
                # Um termo que falha nao derruba a coleta inteira. O parse
                # precisa estar DENTRO do try: corpo vazio -- que e o que a API
                # devolve em HTTP simples -- faz ET.fromstring levantar
                # ParseError, e sem essa cobertura um unico termo ruim mata a
                # coleta de todos os outros.
                continue
            for paper in parsed:
                if paper.arxiv_id in seen:
                    continue
                if allowed.intersection(paper.categories):
                    seen[paper.arxiv_id] = paper
        return list(seen.values())
