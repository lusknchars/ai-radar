"""Desenho em SVG. Puro: sem IO, sem dependencia externa.

O grafico e gerado no servidor de proposito. A camada de render deste projeto
nao importa httpx, anthropic nem sqlite3, e por isso e a parte mais coberta
por teste do repositorio -- um teste afirma que o ponto do paper X esta na
coordenada Y, e a projecao e aritmetica. Biblioteca de grafico no cliente
jogaria isso fora e tornaria a posicao de cada ponto inauditavel.
"""
from __future__ import annotations

from html import escape

from .site_data import Ponto

LARGURA, ALTURA, PAD = 860, 480, 52

# Citacao esta fora de proposito, e a decisao e travada por teste: o acervo e
# jovem demais para o eixo discriminar -- dos 25 papers mais antigos, 8 tem
# citacao e o resto tem zero legitimo. Um eixo em que tudo empilha no zero nao
# separa nada. Ver spec do jornal, secao 3.3.
METRICAS_X = {
    "stars_total": "estrelas no GitHub",
    "idade_dias": "dias desde a publicação",
    "total_impls": "implementações totais",
}


def projetar(valor: float, maximo: float, tamanho: int, pad: int,
             inverter: bool = False) -> float:
    """Projeta um valor no eixo.

    `maximo <= 0` colapsa na origem em vez de dividir por zero: acervo em que
    ninguem tem estrela e caso real no primeiro dia.

    `inverter` existe porque em SVG o y cresce para baixo -- sem ele a
    fronteira apareceria de cabeca para baixo, o que e o tipo de erro que
    passa despercebido porque o grafico continua "bonito".
    """
    frac = 0.0 if maximo <= 0 else valor / maximo
    util = tamanho - 2 * pad
    return pad + util * (1 - frac) if inverter else pad + util * frac


def render_scatter(pontos: list[Ponto], x_metrica: str,
                   cores: dict[str, str]) -> str:
    if x_metrica not in METRICAS_X:
        raise ValueError(
            f"metrica {x_metrica!r} nao e eixo valido; "
            f"use um de {sorted(METRICAS_X)}"
        )
    partes = [
        f'<svg class="scatter" viewBox="0 0 {LARGURA} {ALTURA}" '
        f'role="img" aria-label="implementações independentes contra '
        f'{METRICAS_X[x_metrica]}">'
    ]
    if pontos:
        max_x = max(getattr(p, x_metrica) for p in pontos)
        max_y = max(p.independent_impls for p in pontos)
        for p in pontos:
            cx = projetar(getattr(p, x_metrica), max_x, LARGURA, PAD)
            cy = projetar(p.independent_impls, max_y, ALTURA, PAD, inverter=True)
            partes.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" '
                f'fill="{cores.get(p.familia, "currentColor")}" opacity="0.8">'
                f'<title>{escape(p.titulo)}</title></circle>'
            )
    partes.append("</svg>")
    return "".join(partes)
