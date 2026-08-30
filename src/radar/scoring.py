"""Portao de atencao, depois razao. A ordem importa.

A primeira versao usava so a razao. Um teste com os numeros reais do GPTQ
(103 impls, 3000 estrelas, 2500 citacoes) colocou o paper de quantizacao mais
famoso que existe em terceiro lugar: log1p comprime demais no topo, e um
numerador enorme quase compensa um denominador enorme.

Um paper que ja estourou nao e material de radar por definicao. Ele nao recebe
score baixo -- ele nao e pontuado. Com o portao, a razao so precisa ordenar
dentro do conjunto "ainda nao estourou", que e um trabalho muito mais facil.
"""
from __future__ import annotations

from math import log1p

from .config import Thresholds
from .models import ScoreResult, Signal


def evaluate(signal: Signal, thresholds: Thresholds) -> ScoreResult:
    for name, value in (
        ("total_impls", signal.total_impls),
        ("independent_impls", signal.independent_impls),
        ("velocity_14d", signal.velocity_14d),
        ("stars_total", signal.stars_total),
        ("citations", signal.citations),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} negativo: {value}")

    # Etapa 1: portao. Estrelas antes de citacoes -- o motivo reportado e o
    # primeiro que dispara, e estrelas sao o sinal mais imediato de que estourou.
    if signal.stars_total > thresholds.broke_out_stars:
        return ScoreResult(value=None, gated_by="estrelas")
    # `None` e desconhecido: nao ha numero para comparar com o limiar, e
    # inventar zero so para poder comparar seria fabricar dado. O paper passa.
    if signal.citations is not None and signal.citations > thresholds.broke_out_citations:
        return ScoreResult(value=None, gated_by="citacoes")

    # Etapa 2: razao entre os que passaram.
    strength = log1p(signal.independent_impls) * (1 + 0.5 * log1p(signal.velocity_14d))
    attention = log1p(signal.stars_total) + log1p(signal.citations or 0)
    return ScoreResult(value=strength / (1 + attention), gated_by=None)
