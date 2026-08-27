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
            f"{item.judgment.summary}\n"
            f"{_numbers_line(item)}\n"
            f"Roda na 3090: {item.judgment.runs_on_3090.replace('_', ' ')}\n"
            f"arxiv.org/abs/{item.paper.arxiv_id}"
        )
    return "\n\n".join(blocks)


def render_markdown(
    day: str,
    radar: list[RadarItem],
    feed: list[RadarItem],
    cuts: dict[str, int],
    repos: dict[str, list[dict]] | None = None,
) -> str:
    repos = repos or {}
    out = [f"# Radar — {day}", ""]

    out.append("## Radar")
    out.append("")
    if radar:
        for rank, item in enumerate(radar, start=1):
            out.append(f"### {rank}. {item.judgment.technique}")
            out.append("")
            out.append(item.judgment.summary)
            out.append("")
            out.append(f"- score: {item.score:.4f}")
            out.append(f"- {_numbers_line(item)}")
            out.append(f"- roda na 3090: {item.judgment.runs_on_3090} "
                       f"({item.judgment.rationale})")
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
            out.append(f"- **{item.judgment.technique}** — {item.judgment.summary} "
                       f"(3090: {item.judgment.runs_on_3090}) "
                       f"arxiv.org/abs/{item.paper.arxiv_id}")
    else:
        out.append("Nada novo no escopo hoje.")
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
