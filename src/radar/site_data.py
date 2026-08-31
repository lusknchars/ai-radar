"""O dado que a pagina desenha.

Sem IO e sem dependencia externa: o jornal recebe `SiteData` pronto e nunca
toca o `Store`. Um dataclass e nao `list[dict]` porque o desenho precisa saber
os nomes dos campos -- um erro de digitacao em `p["familia"]` so aparece em
producao, e em `p.familia` aparece no import.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ponto:
    arxiv_id: str
    titulo: str
    familia: str
    pratica: str
    independent_impls: int
    total_impls: int
    stars_total: int
    citations: int | None       # None = desconhecido; a pagina renderiza "—"
    idade_dias: int
    ganho_eixo: str
    ganho_fator: float | None
    ganho_texto: str
    resumo: str
    publicado: str              # ISO date
    score: float
    scope: str


@dataclass(frozen=True)
class SiteData:
    pontos: list[Ponto]
    dia: str
    # None significa "nao registrado". Dicionario vazio significa que a
    # contabilidade rodou e nenhum corte aconteceu. Misturar os dois faria uma
    # edicao historica afirmar "nenhum corte" sem ter o dado para provar.
    cortes: dict[str, int] | None
    rechecked_total: int
    # Historico de coleta. Existem para a frase de movimento do bloco de
    # leitura, e default 0 mantem todo construtor existente valido -- quem os
    # preenche e o `store`, explicitamente.
    dias_de_coleta: int = 0
    papers_que_moveram: int = 0
    repos_do_destaque: list[dict] = field(default_factory=list)

    @property
    def cobertura_de_ganho(self) -> float:
        """Fracao dos papers com fator de ganho extraido.

        Calculada aqui e nao recebida pronta: e ela que decide se a secao de
        avanco existe, e quem monta o SiteData nao pode ter voz nisso.
        """
        if not self.pontos:
            return 0.0
        com = sum(1 for p in self.pontos if p.ganho_fator is not None)
        return com / len(self.pontos)

    @property
    def familias_presentes(self) -> list[str]:
        return sorted({p.familia for p in self.pontos})

    @property
    def destaque(self) -> Ponto | None:
        return max(self.pontos, key=lambda p: p.score, default=None)
