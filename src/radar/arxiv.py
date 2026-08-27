"""Adaptador do arXiv.

PEGADINHA VERIFICADA E MEDIDA: a API so responde em HTTPS e com User-Agent
explicito. Em HTTP ela retorna 301 com corpo vazio -- falha silenciosa, o pior
tipo, porque raise_for_status() nao levanta em 3xx e o httpx nao segue redirect
por padrao: o chamador recebe zero byte e nenhum erro. O endpoint abaixo esta
travado por teste.

Uma query por termo, unidas em codigo, em vez de uma query booleana gigante:
a API trata mal query longa com aspas aninhadas, e a uniao em codigo e trivial
de depurar.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from typing import Callable
from urllib.parse import urlencode

from .config import ScopeConfig
from .models import Discovery, Paper

_log = logging.getLogger(__name__)

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

    def recent(self, scope: ScopeConfig, max_results: int = 100) -> Discovery:
        """Devolve os papers do escopo E a contagem do que ficou pelo caminho.

        As duas contagens existem porque o que o cliente descarta some do
        digest se ninguem contar: "fora de escopo" e o primeiro motivo de corte
        que a spec (secao 7) nomeia, e um termo que falha leva junto ate um doze
        avos da descoberta do dia.
        """
        allowed = set(scope.categories)
        seen: dict[str, Paper] = {}
        fora_de_escopo: set[str] = set()      # por id: um paper repetido em dois
        termos_falhos = 0                     # termos nao conta duas vezes
        for index, term in enumerate(scope.terms):
            if index:
                self._sleep(ETIQUETTE_SLEEP_SECONDS)
            # build_url fica FORA do try: se a construcao da query tiver bug
            # nosso, queremos que exploda, nao que seja engolida como falha
            # do arXiv.
            url = build_url(term, scope, max_results)
            try:
                parsed = parse_feed(self._fetch(url))
            except Exception as exc:
                # Um termo que falha nao derruba a coleta inteira. O parse
                # precisa estar DENTRO do try: corpo vazio -- que e o que a API
                # devolve em HTTP simples -- faz ET.fromstring levantar
                # ParseError, e sem essa cobertura um unico termo ruim mata a
                # coleta de todos os outros. Contado E logado: engolir calado
                # e o truncamento silencioso que o projeto proibe.
                termos_falhos += 1
                _log.warning("termo %r nao produziu resultados: %s", term, exc)
                continue
            for paper in parsed:
                if paper.arxiv_id in seen:
                    continue
                if allowed.intersection(paper.categories):
                    seen[paper.arxiv_id] = paper
                else:
                    fora_de_escopo.add(paper.arxiv_id)

        cuts: dict[str, int] = {}
        if fora_de_escopo:
            cuts["fora_de_escopo"] = len(fora_de_escopo)
        if termos_falhos:
            cuts["termo_falhou"] = termos_falhos
        return Discovery(papers=list(seen.values()), cuts=cuts)
