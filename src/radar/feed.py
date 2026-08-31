"""Feed RSS: como se acompanha o radar sem voltar ao site.

O item e UM PAPER que chegou ao radar, nao o digest do dia. Quem assina quer
saber de tecnicas; um item por dia dizendo "saiu o digest" obrigaria a abrir a
pagina para descobrir se valeu a pena.

Puro: sem IO, sem dependencia externa. XML montado a mao porque a saida e
pequena, fixa, e assim ela fica dentro da fronteira testada do projeto.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape

TITULO = "ai-radar"
DESCRICAO = (
    "Papers de inferência eficiente e de harness de agentes, ordenados por "
    "implementações independentes no GitHub em vez de citação ou estrela. "
    "Papers que já estouraram em atenção são cortados de propósito."
)

# O arquivo de edicoes preserva o historico inteiro. O RSS e a janela de
# acompanhamento: milhares de itens num primeiro carregamento travam leitores
# sem acrescentar nada a quem acabou de assinar.
MAX_ITEMS = 100

_DIAS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class ItemFeed:
    arxiv_id: str
    titulo: str
    resumo: str
    familia: str
    pratica: str
    independent_impls: int
    stars_total: int
    entregue_em: str        # ISO date


def rfc822(iso: str) -> str:
    """RSS exige RFC 822.

    Data em ISO passa despercebida em alguns leitores e SOME em outros -- e
    some sem erro, que e o pior modo de falhar: o feed parece vazio e ninguem
    descobre por que.
    """
    d = date.fromisoformat(iso[:10])
    return (f"{_DIAS[d.weekday()]}, {d.day:02d} {_MESES[d.month - 1]} "
            f"{d.year} 00:00:00 +0000")


def _item(i: ItemFeed) -> str:
    corpo = (f"{i.resumo} — {i.independent_impls} implementações "
             f"independentes, {i.stars_total} estrelas. "
             f"Família: {i.familia}. O que fazer: {i.pratica.replace('_', ' ')}.")
    return (
        "<item>"
        f"<title>{escape(i.titulo)}</title>"
        f"<link>https://arxiv.org/abs/{escape(i.arxiv_id)}</link>"
        f"<description>{escape(corpo)}</description>"
        # guid permanente e nao-URL: o leitor deduplica por ele, e um guid que
        # muda faria o mesmo paper reaparecer como novo a cada execucao.
        f'<guid isPermaLink="false">arxiv:{escape(i.arxiv_id)}</guid>'
        f"<pubDate>{rfc822(i.entregue_em)}</pubDate>"
        f"<category>{escape(i.familia)}</category>"
        "</item>"
    )


def render_rss(itens: list[ItemFeed], dia: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        f"<title>{escape(TITULO)}</title>"
        "<link>https://lusknchars.github.io/ai-radar/</link>"
        f"<description>{escape(DESCRICAO)}</description>"
        "<language>pt-BR</language>"
        f"<lastBuildDate>{rfc822(dia)}</lastBuildDate>"
        + "".join(_item(i) for i in itens)
        + "</channel></rss>"
    )
