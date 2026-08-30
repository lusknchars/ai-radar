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


# Pequenos multiplos: grade de paineis de mesma escala, um por familia.
PAINEL_L, PAINEL_A, PAINEL_PAD = 200, 110, 22
COLUNAS = 4


def render_pequenos_multiplos(series: dict[str, dict[str, int]],
                              familias: list[str],
                              cores: dict[str, str]) -> str:
    """Volume por familia por mes, em paineis de ESCALA COMPARTILHADA.

    Pequenos multiplos e nao area empilhada: a pergunta e "esta familia esta
    crescendo?", nao "que fatia do total ela e". Empilhar faz cada serie
    depender das vizinhas e destroi a leitura individual.

    A escala e compartilhada porque a comparacao entre familias e a unica
    pergunta que a secao responde. Escala por painel faria 3 papers e 300
    desenharem a mesma altura -- o grafico continuaria bonito e passaria a
    mentir.

    Uma familia sem dado ainda ganha painel: ausencia e informacao, e some-la
    faria parecer que a familia nao existe.
    """
    linhas = (len(familias) + COLUNAS - 1) // COLUNAS
    largura = COLUNAS * PAINEL_L
    altura = max(linhas, 1) * PAINEL_A

    # Maximo GLOBAL, calculado sobre todas as series antes de desenhar
    # qualquer uma. Move esta linha para dentro do laco e a escala vira
    # por painel.
    maximo = max((v for meses in series.values() for v in meses.values()),
                 default=0)

    partes = [f'<svg class="multiplos" viewBox="0 0 {largura} {altura}" '
              f'role="img" aria-label="volume por família ao longo do tempo">']

    for i, familia in enumerate(familias):
        ox = (i % COLUNAS) * PAINEL_L
        oy = (i // COLUNAS) * PAINEL_A
        cor = cores.get(familia, "currentColor")
        partes.append(f'<g class="painel" transform="translate({ox},{oy})">')
        partes.append(
            f'<text x="4" y="12" font-size="10">{escape(familia)}</text>')

        meses = series.get(familia, {})
        util_a = PAINEL_A - PAINEL_PAD - 14
        if meses:
            # Ordem cronologica: `sorted` sobre chaves ISO `YYYY-MM` ja da a
            # ordem certa sem parsear data.
            ordenados = sorted(meses.items())
            larg_barra = max((PAINEL_L - 8) / len(ordenados) - 2, 1)
            for k, (_mes, n) in enumerate(ordenados):
                h = 0.0 if maximo <= 0 else util_a * (n / maximo)
                x = 4 + k * (larg_barra + 2)
                partes.append(
                    f'<rect x="{x:.1f}" y="{14 + util_a - h:.1f}" '
                    f'width="{larg_barra:.1f}" height="{h:.1f}" fill="{cor}"/>'
                )
        partes.append("</g>")

    partes.append("</svg>")
    return "".join(partes)
