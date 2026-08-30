"""O bloco de leitura: o que o acervo mostra, em frases calculadas.

ARITMETICA, NUNCA GERACAO. Um LLM escrevendo estas frases inventaria
correlacao com fluencia perfeita, e seria indistinguivel de calculo correto
para quem le. Esta e a decisao que organiza o modulo inteiro.

Cada afirmacao tem uma guarda, e guarda que nao passa OMITE a frase em vez de
enfraquece-la com hedge. Um bloco com duas frases solidas vale mais que um com
seis cheias de "pode indicar que" -- hedge e o que se escreve quando nao se
quer decidir se a afirmacao se sustenta; a guarda decide.

Sem IO: recebe `SiteData` pronto.
"""
from __future__ import annotations

from dataclasses import dataclass

from .site_data import SiteData


@dataclass(frozen=True)
class Afirmacao:
    texto: str
    filtro: dict | None = None      # o filtro que reproduz a frase na tabela


def afirmacoes(dados: SiteData) -> list[Afirmacao]:
    """Ordem ARGUMENTATIVA, nao estetica.

    Escassez vem primeiro porque e o denominador de tudo: quem le "10 na
    fronteira" sem ter lido "936 com zero" superestima a densidade do sinal
    por mais de uma ordem de grandeza.
    """
    if not dados.pontos:
        return []
    candidatas = (
        _escassez(dados),
        _fronteira(dados),
        _concentracao(dados),
        _cobertura(dados),
        _taxonomia(dados),
        _movimento(dados),
    )
    return [a for a in candidatas if a is not None]


def _escassez(d: SiteData) -> Afirmacao | None:
    return None


def _fronteira(d: SiteData) -> Afirmacao | None:
    return None


def _concentracao(d: SiteData) -> Afirmacao | None:
    return None


def _cobertura(d: SiteData) -> Afirmacao | None:
    return None


def _taxonomia(d: SiteData) -> Afirmacao | None:
    return None


def _movimento(d: SiteData) -> Afirmacao | None:
    return None
