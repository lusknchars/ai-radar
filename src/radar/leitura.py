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

from .public_labels import FAMILY_LABELS, public_label
from .site_data import SiteData

# Todos escolhidos por inspecao, NAO derivados de analise. Estao nomeados aqui
# para serem discutiveis; fingir que ha estudo por tras seria pior que admitir.
IMPLS_FRONTEIRA = 3
ESTRELAS_FRONTEIRA = 10
MIN_PAPERS_CONCENTRACAO = 100
MIN_IMPLS_CONCENTRACAO = 50
MIN_DIAS_PARA_MOVIMENTO = 30


@dataclass(frozen=True)
class Afirmacao:
    texto: str
    filtro: dict | None = None      # o filtro que reproduz a frase na tabela


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


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
    """Sem guarda, de proposito: esta frase sai sempre.

    E o denominador de todas as outras. Medido em 2026-08-29: 936 de 1088
    papers do acervo, 86%. Um leitor que ve "10 na fronteira" sem ter visto
    esse numero superestima a densidade do sinal por mais de uma ordem de
    grandeza.
    """
    zerados = sum(1 for p in d.pontos if p.independent_impls == 0)
    total = len(d.pontos)
    # `{n} de {total}` e nao `Dos {total}, {n}`: a guarda de denominador
    # procura " de " ou " das ", e a segunda forma nao casa. A verificacao do
    # plano pegou isso antes de virar codigo.
    papers = _plural(total, "paper")
    verb = "has" if zerados == 1 else "have"
    return Afirmacao(
        texto=f"{zerados} of {total} {papers} in the index "
              f"({zerados / total:.0%}) {verb} no independent implementations.",
    )


def _fronteira(d: SiteData) -> Afirmacao | None:
    """A tese do projeto virada em numero.

    Se ficar perto de zero de forma persistente, a hipotese -- que
    reimplementacao antecede atencao -- esta errada, e a pagina passa a dizer
    isso. Medido em 2026-08-29: 10 papers de 1088.
    """
    n = sum(1 for p in d.pontos
            if p.independent_impls >= IMPLS_FRONTEIRA
            and p.stars_total < ESTRELAS_FRONTEIRA)
    if n == 0:
        return None
    subject = _plural(n, "paper")
    verb = "sits" if n == 1 else "sit"
    return Afirmacao(
        texto=f"{n} {subject} {verb} on the research frontier: at least "
              f"{IMPLS_FRONTEIRA} independent implementations and fewer than "
              f"{ESTRELAS_FRONTEIRA} combined stars.",
        filtro={"ordenar": "impls"},
    )


def _concentracao(d: SiteData) -> Afirmacao | None:
    por_familia: dict[str, int] = {}
    for p in d.pontos:
        por_familia[p.familia] = por_familia.get(p.familia, 0) + p.independent_impls
    total = sum(por_familia.values())

    # Guardas CONJUNTIVAS: um acervo grande com pouco sinal, ou muito sinal
    # concentrado em poucos papers, produz concentracao que e ruido de amostra.
    if len(d.pontos) < MIN_PAPERS_CONCENTRACAO or total < MIN_IMPLS_CONCENTRACAO:
        return None

    acumulado, escolhidas = 0, []
    for familia, n in sorted(por_familia.items(), key=lambda kv: (-kv[1], kv[0])):
        acumulado += n
        escolhidas.append(familia)
        if acumulado > total / 2:
            break

    family_count = len(escolhidas)
    family_label = _plural(family_count, "research area")
    implementation_label = _plural(total, "implementation")
    return Afirmacao(
        texto=f"{family_count} {family_label} account for "
              f"{acumulado / total:.0%} of the index's {total} independent "
              f"{implementation_label}: "
              f"{', '.join(public_label(FAMILY_LABELS, item) for item in escolhidas)}.",
        filtro={"familia": escolhidas[0]},
    )


def _cobertura(d: SiteData) -> Afirmacao | None:
    """Sem guarda. Publica o numero que decide se a secao de avanco existe,
    tornando essa decisao auditavel em vez de invisivel."""
    com = sum(1 for p in d.pontos if p.ganho_fator is not None)
    papers = _plural(len(d.pontos), "paper")
    verb = "reports" if com == 1 else "report"
    return Afirmacao(
        texto=f"{com} of {len(d.pontos)} {papers} ({d.cobertura_de_ganho:.0%}) "
              f"{verb} a quantified gain in the abstract. All such gains are "
              f"author-reported and not independently verified.",
        filtro={"ordenar": "ganho"},
    )


def _taxonomia(d: SiteData) -> Afirmacao | None:
    """A taxa de `outro` e instrumento de medicao da propria taxonomia.

    Esconde-la apresentaria a classificacao como mais ajustada do que ela e.
    O denominador aqui e explicito de proposito: a redacao do plano passava na
    guarda por ACIDENTE, pelo " das " de "nenhuma das dezoito familias".
    """
    n = sum(1 for p in d.pontos if p.familia == "outro")
    papers = _plural(len(d.pontos), "paper")
    verb = "remains" if n == 1 else "remain"
    return Afirmacao(
        texto=f"{n} of {len(d.pontos)} {papers} ({n / len(d.pontos):.0%}) "
              f"{verb} classified as 'other' because none of the eighteen "
              f"defined research areas fit.",
        filtro={"familia": "outro"} if n else None,
    )


def _movimento(d: SiteData) -> Afirmacao | None:
    """A guarda mais restritiva do modulo.

    O seed de 2026-08-29 rodou SEM PISO DE DATA: ele trouxe o que o arXiv
    devolvia por termo, nao o que foi publicado em cada mes. Qualquer
    afirmacao temporal sobre esse recorte mede o ranking de busca do arXiv,
    nao a literatura. Ate a rotina diaria acumular historico proprio, esta
    frase nao existe.
    """
    if d.dias_de_coleta < MIN_DIAS_PARA_MOVIMENTO:
        return None
    if d.papers_que_moveram == 0:
        return None
    papers = _plural(d.papers_que_moveram, "paper")
    return Afirmacao(
        texto=f"{d.papers_que_moveram} {papers} gained an independent "
              f"implementation since the previous observation.",
        filtro={"ordenar": "impls"},
    )
