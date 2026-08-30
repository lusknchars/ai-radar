"""Renderizacao. Puro: nao importa httpx, anthropic nem sqlite3.

Regras de produto codificadas aqui:
- push sem emoji
- teto de 3 e rigido; passar 4 e erro, nao truncamento
- a secao de cortes e obrigatoria, mesmo vazia
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import PUSH_CAP
from .models import Judgment, Paper, Signal


@dataclass(frozen=True)
class RadarItem:
    paper: Paper
    judgment: Judgment
    signal: Signal
    score: float
    delta: dict | None = None


def _linha_de_ganho(j: Judgment) -> str | None:
    """O rotulo NAO e opcional.

    `ganho_fator` e alegacao de abstract, nunca medicao -- nada aqui foi
    reproduzido. Um numero desses apresentado como resultado seria exatamente
    o hype de que este projeto existe para fugir. Se um dia nao couber o
    rotulo, corta-se a linha, nao o rotulo.
    """
    if j.ganho_fator is None:
        return None
    return (f"ganho {j.ganho_fator:g}x em {j.ganho_eixo} "
            f"— alegado pelos autores, nao verificado")


def _numbers_line(item: RadarItem) -> str:
    if item.delta:
        d = item.delta
        return (f"{d['independent_from']} -> {d['independent_to']} impls independentes "
                f"em {d['days']} dias · {d['stars_to']} estrelas")
    return (f"{item.signal.independent_impls} impls independentes · "
            f"{item.signal.stars_total} estrelas · +{item.signal.velocity_14d} em 14 dias")


def render_telegram(items: list[RadarItem]) -> str:
    if len(items) > PUSH_CAP:
        raise ValueError(f"teto de {PUSH_CAP} itens excedido: {len(items)}")
    if not items:
        return ""      # silencio e resultado valido
    blocks = []
    for item in items:
        blocks.append(
            f"[TECNICA] {item.judgment.technique}\n"
            f"{item.judgment.resumo}\n"
            f"{_numbers_line(item)}\n"
            f"Pratica: {item.judgment.pratica.replace('_', ' ')}\n"
            + (f"{ganho}\n" if (ganho := _linha_de_ganho(item.judgment)) else "")
            + f"arxiv.org/abs/{item.paper.arxiv_id}"
        )
    return "\n\n".join(blocks)


def render_markdown(
    day: str,
    radar: list[RadarItem],
    feed: list[RadarItem],
    cuts: dict[str, int],
    repos: dict[str, list[dict]] | None = None,
    rechecked: list[RadarItem] | None = None,
    rechecked_total: int = 0,
) -> str:
    repos = repos or {}
    out = [f"# Radar — {day}", ""]

    out.append("## Radar")
    out.append("")
    if radar:
        for rank, item in enumerate(radar, start=1):
            out.append(f"### {rank}. {item.judgment.technique}")
            out.append("")
            out.append(item.judgment.resumo)
            out.append("")
            out.append(f"- score: {item.score:.4f}")
            out.append(f"- {_numbers_line(item)}")
            out.append(f"- familia: {item.judgment.familia}")
            out.append(f"- pratica: {item.judgment.pratica} "
                       f"({item.judgment.porque})")
            if (ganho := _linha_de_ganho(item.judgment)):
                out.append(f"- {ganho}")
            out.append(f"- arxiv.org/abs/{item.paper.arxiv_id}")
            for repo in repos.get(item.paper.arxiv_id, []):
                marca = f"autor ({repo['is_author_reason']})" if repo["is_author"] else "independente"
                out.append(f"  - {repo['full_name']} — {repo['stars']} estrelas — {marca}")
            out.append("")
    else:
        out.append("Nenhum item passou o piso hoje.")
        out.append("")

    out.append("## Feed")
    out.append("")
    if feed:
        for item in feed:
            out.append(f"- **{item.judgment.technique}** — {item.judgment.resumo} "
                       f"({item.judgment.familia} · {item.judgment.pratica}) "
                       f"arxiv.org/abs/{item.paper.arxiv_id}")
    else:
        out.append("Nada novo no escopo hoje.")
    out.append("")

    # Seccao presente apenas quando houve re-consulta. Lista so quem se moveu:
    # trinta linhas de "nada mudou" e ruido, e o teto de legibilidade e a
    # restricao de produto mais forte deste projeto. Mas quando nada se moveu,
    # diz isso -- silencio ambiguo faz parecer que o trabalho nao foi feito.
    if rechecked_total:
        out.append("## Re-consulta")
        out.append("")
        if rechecked:
            out.append(f"{rechecked_total} papers re-consultados. "
                       f"{len(rechecked)} com movimento:")
            out.append("")
            for it in rechecked:
                d = it.delta or {}
                out.append(
                    f"- {it.paper.arxiv_id} — "
                    f"{d.get('independent_from')} -> {d.get('independent_to')} "
                    f"impls independentes em {d.get('days')} dias — "
                    f"score {it.score:.4f}"
                )
        else:
            out.append(f"{rechecked_total} papers re-consultados, nenhum com movimento.")
        out.append("")

    # Secao obrigatoria: truncar em silencio faz o radar parecer que cobriu tudo.
    out.append("## Cortes")
    out.append("")
    if cuts:
        for reason, count in sorted(cuts.items()):
            out.append(f"- {reason}: {count}")
    else:
        out.append("Nenhum corte hoje.")
    out.append("")
    return "\n".join(out)


# Rotulo legivel por escopo, e a ordem em que aparecem no arquivo do dia.
# `inferencia` primeiro por decisao travada: e o primeiro escopo a descobrir,
# e o que fica com o paper quando os dois o encontram.
ROTULO_ESCOPO = {"inferencia": "Inferência", "agentes": "Agentes"}
ORDEM_ESCOPO = ("inferencia", "agentes")


def _rebaixa_titulos(linha: str) -> str:
    """Desce um nivel os titulos vindos de `render_markdown`.

    O rotulo de escopo entra como h2. Sem rebaixar, `## Radar` viraria irmao
    de `## Inferência` quando na verdade e filho dele, e o documento passaria
    a mentir sobre a propria estrutura.

    Nao ha bloco de codigo no markdown do radar, entao nao existe `#` de
    conteudo para proteger aqui.
    """
    return "#" + linha if linha.startswith("#") else linha


def compose_day(day: str, por_escopo: dict) -> str:
    """Costura o markdown de cada escopo num arquivo unico do dia.

    NAO reabre `render_markdown`: cada DayResult ja traz o seu markdown pronto
    e testado -- e ela e a funcao mais coberta do projeto. Aqui so se remove o
    cabecalho duplicado, se rebaixa o resto, e se rotula a secao.
    """
    out = [f"# Radar — {day}", ""]
    for nome in ORDEM_ESCOPO:
        r = por_escopo.get(nome)
        if r is None:
            continue
        out.append(f"## {ROTULO_ESCOPO[nome]}")
        # Sem `out.append("")` aqui: o corpo ja comeca com a linha em branco
        # que vinha logo depois do cabecalho removido.
        corpo = r.markdown.split("\n")
        # A primeira linha de cada markdown e o cabecalho `# Radar — <dia>`;
        # ele vira uma vez so, no topo do arquivo composto.
        if corpo and corpo[0].startswith("# Radar"):
            corpo = corpo[1:]
        out.extend(_rebaixa_titulos(l) for l in corpo)
        out.append("")
    return "\n".join(out)
