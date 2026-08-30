"""Adaptador de citacoes.

O Semantic Scholar foi medido primeiro e reprovado: sem chave devolve 429 na
primeira chamada, e com esperas crescentes de ate 52s acertou 2 de 6
tentativas. Uma fonte que falha dois tercos das vezes gravaria zeros
silenciosos -- exatamente o defeito que este modulo existe para consertar.

O OpenAlex resolve 50 papers numa requisicao em 0,38s sem chave nenhuma; basta
um `mailto:` no User-Agent para cair no pool "polite". Medido em 2026-08-29:
LoRA 2527 citacoes, FlashAttention 461, GPTQ 136.

Sem IO: o transporte entra por injecao, como em `arxiv` e `github`.
"""
from __future__ import annotations

import logging
from typing import Callable
from urllib.parse import urlencode

_log = logging.getLogger(__name__)

BASE = "https://api.openalex.org/works"
MAX_POR_LOTE = 50          # teto de `per-page` da API
USER_AGENT = "ai-radar/0.1 (mailto:luskoliveira@protonmail.com)"

_PREFIXO = "https://doi.org/10.48550/arXiv."
_MARCA = "10.48550/arxiv."


def build_url(arxiv_ids: list[str]) -> str:
    if len(arxiv_ids) > MAX_POR_LOTE:
        raise ValueError(
            f"{len(arxiv_ids)} ids num lote; o teto da API e {MAX_POR_LOTE}"
        )
    filtro = "|".join(f"{_PREFIXO}{i}" for i in arxiv_ids)
    return f"{BASE}?" + urlencode({
        "filter": f"doi:{filtro}",
        "select": "doi,cited_by_count",
        "per-page": str(MAX_POR_LOTE),
    })


def _id_do_doi(doi: str) -> str:
    """Extrai o arXiv ID de um DOI do OpenAlex.

    A API responde `arxiv.` mesmo tendo sido consultada com `arXiv.`. Casar
    sensivel a caixa faz TODA linha se perder, e o sintoma seria citacoes
    sempre nulas -- indistinguivel do bug que estamos consertando.
    """
    baixa = doi.lower()
    if _MARCA not in baixa:
        return ""
    return doi[baixa.index(_MARCA) + len(_MARCA):]


class OpenAlexClient:
    def __init__(self, fetch: Callable[[str], dict]) -> None:
        self._fetch = fetch

    def citations_for(self, arxiv_ids: list[str]) -> dict[str, int | None]:
        """Devolve citacoes por id. Ausente e `None`, jamais `0`.

        Fatia em lotes de `MAX_POR_LOTE`: o teto e da API, nao do chamador, e
        o acervo tem mais de mil papers.
        """
        if not arxiv_ids:
            return {}

        # Comeca tudo desconhecido. So um resultado explicito vira numero, e e
        # isso que separa "ninguem citou" de "nao perguntamos".
        fora: dict[str, int | None] = {i: None for i in arxiv_ids}

        for inicio in range(0, len(arxiv_ids), MAX_POR_LOTE):
            fatia = arxiv_ids[inicio:inicio + MAX_POR_LOTE]
            try:
                payload = self._fetch(build_url(fatia))
            except Exception:
                # Degrada para desconhecido, nunca para zero. Uma falha de rede
                # que virasse zero entraria na formula de atencao como fato.
                _log.warning("openalex falhou para %d ids; ficam desconhecidos",
                             len(fatia))
                continue
            for obra in payload.get("results", []):
                ident = _id_do_doi(obra.get("doi") or "")
                if ident in fora:
                    fora[ident] = obra.get("cited_by_count")
        return fora
