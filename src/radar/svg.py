"""Desenho em SVG. Puro: sem IO, sem dependencia externa.

O grafico e gerado no servidor de proposito. A camada de render deste projeto
nao importa httpx, anthropic nem sqlite3, e por isso e a parte mais coberta
por teste do repositorio -- um teste afirma que o ponto do paper X esta na
coordenada Y, e a projecao e aritmetica. Biblioteca de grafico no cliente
jogaria isso fora e tornaria a posicao de cada ponto inauditavel.
"""
from __future__ import annotations

from html import escape
from math import ceil, floor, log10

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


def _formatar_tick(valor: float) -> str:
    return f"{valor:g}"


def _ticks_lineares(maximo: float, alvo: int = 4) -> tuple[float, list[float]]:
    """Devolve um teto arredondado e poucos ticks legiveis.

    O dado do radar costuma ocupar dominios muito diferentes (9 impls, 800
    estrelas, 120 dias). Fixar um passo serviria para apenas um deles; esta
    versao escolhe passos 1, 2, 2.5, 5 ou 10 em qualquer ordem de grandeza.
    """
    if maximo <= 0:
        return 1.0, [0.0, 1.0]
    bruto = maximo / alvo
    potencia = 10 ** floor(log10(bruto))
    fracao = bruto / potencia
    multiplo = next(n for n in (1, 2, 2.5, 5, 10) if fracao <= n)
    passo = multiplo * potencia
    teto = ceil(maximo / passo) * passo
    quantidade = int(round(teto / passo))
    return teto, [i * passo for i in range(quantidade + 1)]


def _rotulo_mes(mes: str) -> str:
    nomes = ("jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez")
    try:
        ano, numero = mes.split("-")
        return f"{nomes[int(numero) - 1]} {ano[2:]}"
    except (ValueError, IndexError):
        return mes


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
    max_x, ticks_x = _ticks_lineares(
        max((getattr(p, x_metrica) for p in pontos), default=0))
    max_y, ticks_y = _ticks_lineares(
        max((p.independent_impls for p in pontos), default=0))
    rotulo_x = METRICAS_X[x_metrica]
    plot_baixo = ALTURA - PAD
    plot_direita = LARGURA - PAD
    partes = [
        f'<svg class="scatter" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {LARGURA} {ALTURA}" '
        f'role="img" aria-label="implementações independentes contra '
        f'{escape(rotulo_x)}">'
        f'<desc>Cada ponto é um paper. Mais alto significa mais implementações '
        f'independentes; mais à direita significa mais {escape(rotulo_x)}.</desc>',
        '<g class="chart-grid" aria-hidden="true">',
    ]
    for tick in ticks_y:
        y = projetar(tick, max_y, ALTURA, PAD, inverter=True)
        partes.append(
            f'<line x1="{PAD}" x2="{plot_direita}" y1="{y:.1f}" '
            f'y2="{y:.1f}" stroke="#000" opacity="0.10"/>'
        )
    for tick in ticks_x:
        x = projetar(tick, max_x, LARGURA, PAD)
        partes.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{PAD}" '
            f'y2="{plot_baixo}" stroke="#000" opacity="0.07"/>'
        )
    partes.append('</g><g class="x-axis" aria-hidden="true">')
    partes.append(
        f'<line x1="{PAD}" x2="{plot_direita}" y1="{plot_baixo}" '
        f'y2="{plot_baixo}" stroke="#000" opacity="0.35"/>'
    )
    for tick in ticks_x:
        x = projetar(tick, max_x, LARGURA, PAD)
        partes.append(
            f'<text x="{x:.1f}" y="{plot_baixo + 18}" text-anchor="middle" '
            f'font-size="10" fill="#555">{_formatar_tick(tick)}</text>'
        )
    partes.append(
        f'<text x="{LARGURA / 2:.1f}" y="{ALTURA - 10}" text-anchor="middle" '
        f'font-size="11" fill="#333">{escape(rotulo_x)}</text></g>'
        '<g class="y-axis" aria-hidden="true">'
        f'<line x1="{PAD}" x2="{PAD}" y1="{PAD}" y2="{plot_baixo}" '
        f'stroke="#000" opacity="0.35"/>'
    )
    for tick in ticks_y:
        y = projetar(tick, max_y, ALTURA, PAD, inverter=True)
        partes.append(
            f'<text x="{PAD - 10}" y="{y + 3:.1f}" text-anchor="end" '
            f'font-size="10" fill="#555">{_formatar_tick(tick)}</text>'
        )
    partes.append(
        f'<text x="14" y="{ALTURA / 2:.1f}" text-anchor="middle" '
        f'transform="rotate(-90 14 {ALTURA / 2:.1f})" font-size="11" '
        f'fill="#333">implementações independentes</text></g>'
    )
    for p in pontos:
        valor_x = getattr(p, x_metrica)
        cx = projetar(valor_x, max_x, LARGURA, PAD)
        cy = projetar(p.independent_impls, max_y, ALTURA, PAD, inverter=True)
        partes.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" '
            f'fill="{cores.get(p.familia, "currentColor")}" opacity="0.86" '
            f'stroke="#eeeeee" stroke-width="2" vector-effect="non-scaling-stroke">'
            f'<title>{escape(p.titulo)} — {_formatar_tick(valor_x)} '
            f'{escape(rotulo_x)}; {p.independent_impls} implementações '
            f'independentes</title></circle>'
        )
    partes.append("</svg>")
    return "".join(partes)


# Pequenos multiplos: grade de paineis de mesma escala, um por familia.
PAINEL_L, PAINEL_A, PAINEL_PAD = 270, 150, 32
COLUNAS = 3


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
    colunas = min(max(len(familias), 1), COLUNAS)
    linhas = (len(familias) + colunas - 1) // colunas
    largura = colunas * PAINEL_L
    altura = max(linhas, 1) * PAINEL_A

    # Maximo GLOBAL, calculado sobre todas as series antes de desenhar
    # qualquer uma. Move esta linha para dentro do laco e a escala vira
    # por painel.
    maximo = max((v for meses in series.values() for v in meses.values()),
                 default=0)
    # Um unico calendario para todos os paineis. Sem isso, o primeiro mes
    # presente em cada familia virava a primeira barra, e colunas iguais
    # podiam representar meses diferentes.
    meses_globais = sorted({mes for meses in series.values() for mes in meses})

    partes = [f'<svg class="multiplos" xmlns="http://www.w3.org/2000/svg" '
              f'viewBox="0 0 {largura} {altura}" '
              f'role="img" aria-label="volume por família ao longo do tempo">']

    for i, familia in enumerate(familias):
        ox = (i % colunas) * PAINEL_L
        oy = (i // colunas) * PAINEL_A
        cor = cores.get(familia, "currentColor")
        partes.append(f'<g class="painel" transform="translate({ox},{oy})">')
        partes.append(
            f'<text x="{PAINEL_PAD}" y="18" font-size="11" fill="#222">'
            f'{escape(rotulos.get(familia, familia))}</text>'
            f'<text x="{PAINEL_L - 12}" y="18" text-anchor="end" '
            f'font-size="9" fill="#777">máx. {maximo}</text>')

        meses = series.get(familia, {})
        topo = 30
        base = PAINEL_A - 28
        util_a = base - topo
        inicio_x = PAINEL_PAD
        fim_x = PAINEL_L - 12
        partes.append(
            f'<line x1="{inicio_x}" x2="{fim_x}" y1="{base}" y2="{base}" '
            f'stroke="#000" opacity="0.22"/>'
        )
        if meses_globais:
            passo = (fim_x - inicio_x) / len(meses_globais)
            larg_barra = max(passo - 4, 1)
            for k, mes in enumerate(meses_globais):
                n = meses.get(mes, 0)
                h = 0.0 if maximo <= 0 else util_a * (n / maximo)
                x = inicio_x + k * passo + (passo - larg_barra) / 2
                partes.append(
                    f'<rect class="bar" data-month="{escape(mes)}" '
                    f'data-value="{n}" x="{x:.1f}" y="{base - h:.1f}" '
                    f'width="{larg_barra:.1f}" height="{h:.1f}" fill="{cor}" '
                    f'opacity="{0.82 if n else 0.12}"><title>'
                    f'{escape(_rotulo_mes(mes))}: {n} papers</title></rect>'
                )
            primeiro = escape(_rotulo_mes(meses_globais[0]))
            ultimo = escape(_rotulo_mes(meses_globais[-1]))
            partes.append(
                f'<text x="{inicio_x}" y="{PAINEL_A - 8}" font-size="9" '
                f'fill="#777">{primeiro}</text>'
                f'<text x="{fim_x}" y="{PAINEL_A - 8}" text-anchor="end" '
                f'font-size="9" fill="#777">{ultimo}</text>'
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
    com_fator = [p for p in pontos if p.ganho_fator is not None]
    for p in com_fator:
        if p.ganho_fator <= 0:
            # Explodir alto em vez de gerar coordenada NaN: um SVG com NaN
            # desenha errado em silencio, que e pior que nao desenhar.
            raise ValueError(
                f"ganho_fator={p.ganho_fator!r} em {p.arxiv_id}: a escala log "
                f"exige fator > 0"
            )

    partes = [f'<svg class="avanco" xmlns="http://www.w3.org/2000/svg" '
              f'viewBox="0 0 {AVANCO_L} {AVANCO_A}" '
              f'role="img" aria-label="ganho alegado ao longo do tempo, escala log">'
              '<desc>Fatores declarados pelos autores, não verificados. '
              'O eixo vertical usa escala logarítmica e a linha de base é 1x.</desc>']
    if com_fator:
        meses = sorted({p.publicado[:7] for p in com_fator})
        idx = {m: i for i, m in enumerate(meses)}
        logs = [log10(p.ganho_fator) for p in com_fator]
        min_log = min(0.0, min(logs))
        max_log = max(0.0, max(logs))
        if min_log == max_log:
            max_log = min_log + 1.0

        def projetar_log(fator: float) -> float:
            frac = (log10(fator) - min_log) / (max_log - min_log)
            return PAD + (AVANCO_A - 2 * PAD) * (1 - frac)

        def coord(p):
            x = projetar(idx[p.publicado[:7]], max(len(meses) - 1, 1),
                         AVANCO_L, PAD)
            y = projetar_log(p.ganho_fator)
            return x, y

        tick_fatores: list[float] = []
        for expoente in range(floor(min_log) - 1, ceil(max_log) + 1):
            for multiplo in (1, 2, 5):
                fator = multiplo * (10 ** expoente)
                valor_log = log10(fator)
                if min_log - 1e-9 <= valor_log <= max_log + 1e-9:
                    tick_fatores.append(fator)

        partes.append('<g class="chart-grid" aria-hidden="true">')
        for fator in tick_fatores:
            y = projetar_log(fator)
            partes.append(
                f'<line x1="{PAD}" x2="{AVANCO_L - PAD}" y1="{y:.1f}" '
                f'y2="{y:.1f}" stroke="#000" opacity="0.10"/>'
                f'<text x="{PAD - 10}" y="{y + 3:.1f}" text-anchor="end" '
                f'font-size="10" fill="#555">{_formatar_tick(fator)}x</text>'
            )
        for mes in meses:
            x = projetar(idx[mes], max(len(meses) - 1, 1), AVANCO_L, PAD)
            partes.append(
                f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{PAD}" '
                f'y2="{AVANCO_A - PAD}" stroke="#000" opacity="0.06"/>'
                f'<text x="{x:.1f}" y="{AVANCO_A - PAD + 18}" '
                f'text-anchor="middle" font-size="10" fill="#555">'
                f'{escape(_rotulo_mes(mes))}</text>'
            )
        partes.append('</g>')

        base_y = projetar_log(1.0)
        partes.append(
            f'<line class="baseline" x1="{PAD}" x2="{AVANCO_L - PAD}" '
            f'y1="{base_y:.1f}" y2="{base_y:.1f}" stroke="#000" '
            f'stroke-width="1.5" opacity="0.55"/>'
            f'<text x="14" y="{AVANCO_A / 2:.1f}" text-anchor="middle" '
            f'transform="rotate(-90 14 {AVANCO_A / 2:.1f})" font-size="11" '
            f'fill="#333">fator alegado · escala log</text>'
        )

        for p in com_fator:
            x, y = coord(p)
            partes.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" '
                f'fill="{cores.get(p.familia, "currentColor")}" opacity="0.86" '
                f'stroke="#eeeeee" stroke-width="2" vector-effect="non-scaling-stroke">'
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
