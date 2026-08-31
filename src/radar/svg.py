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
                              cores: dict[str, str],
                              rotulos: dict[str, str] | None = None) -> str:
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
    rotulos = rotulos or {}
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
            f'<text x="4" y="12" font-size="10">'
            f'{escape(rotulos.get(familia, familia))}</text>')

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


# O avanco alegado. Escala log no y porque fatores de ganho variam por ordens
# de grandeza: 1.2x e 40x no mesmo eixo linear achatam tudo perto de zero.
AVANCO_L, AVANCO_A = 860, 400
MIN_PARA_MEDIANA = 5


def _trimestre(publicado: str) -> str:
    ano, mes = publicado[:4], int(publicado[5:7])
    return f"{ano}-T{(mes - 1) // 3 + 1}"


def render_avanco(pontos: list[Ponto], cores: dict[str, str]) -> str:
    """Ganho alegado ao longo do tempo, por familia.

    ATENCAO, e a regra mais importante da pagina: `ganho_fator` e ALEGACAO
    extraida do resumo, nunca medicao -- nada aqui foi reproduzido. Quem chama
    esta funcao e obrigado a exibir o rotulo de nao-verificado junto. Se nao
    couber o rotulo, corta-se o grafico, nao o rotulo.
    """
    from math import log10

    com_fator = [p for p in pontos if p.ganho_fator is not None]
    for p in com_fator:
        if p.ganho_fator <= 0:
            # Explodir alto em vez de gerar coordenada NaN: um SVG com NaN
            # desenha errado em silencio, que e pior que nao desenhar.
            raise ValueError(
                f"ganho_fator={p.ganho_fator!r} em {p.arxiv_id}: a escala log "
                f"exige fator > 0"
            )

    partes = [f'<svg class="avanco" viewBox="0 0 {AVANCO_L} {AVANCO_A}" '
              f'role="img" aria-label="ganho alegado ao longo do tempo">']
    if com_fator:
        meses = sorted({p.publicado[:7] for p in com_fator})
        idx = {m: i for i, m in enumerate(meses)}
        max_log = max(log10(p.ganho_fator) for p in com_fator) or 1.0

        def coord(p):
            x = projetar(idx[p.publicado[:7]], max(len(meses) - 1, 1),
                         AVANCO_L, PAD)
            y = projetar(max(log10(p.ganho_fator), 0.0), max_log,
                         AVANCO_A, PAD, inverter=True)
            return x, y

        for p in com_fator:
            x, y = coord(p)
            partes.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" '
                f'fill="{cores.get(p.familia, "currentColor")}" opacity="0.75">'
                f"<title>{escape(p.titulo)}: {p.ganho_fator:g}x em "
                f"{escape(p.ganho_eixo)} (alegado)</title></circle>"
            )

        # Mediana por familia por trimestre, e SO onde houver massa: abaixo de
        # cinco papers a mediana e ruido com aparencia de tendencia, e uma
        # linha num grafico le como afirmacao.
        grupos: dict[tuple[str, str], list] = {}
        for p in com_fator:
            grupos.setdefault((p.familia, _trimestre(p.publicado)), []).append(p)
        for (familia, _tri), grupo in sorted(grupos.items()):
            if len(grupo) < MIN_PARA_MEDIANA:
                continue
            xs = sorted(coord(p)[0] for p in grupo)
            ys = sorted(coord(p)[1] for p in grupo)
            partes.append(
                f'<line class="mediana" x1="{xs[0]:.1f}" x2="{xs[-1]:.1f}" '
                f'y1="{ys[len(ys) // 2]:.1f}" y2="{ys[len(ys) // 2]:.1f}" '
                f'stroke="{cores.get(familia, "currentColor")}" '
                f'stroke-width="2" opacity="0.6"/>'
            )
    partes.append("</svg>")
    return "".join(partes)
