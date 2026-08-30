"""Tipos compartilhados. Nenhum IO, nenhuma dependencia externa alem de stdlib."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Fechado por decisao de produto. O seed de 2026-08-29 produziu 1088 valores
# distintos de `technique` para 1088 papers: uma taxonomia com N categorias
# para N itens nao agrega nada, e agregacao e a razao de existir do acervo.
#
# Familia NAO e derivada de escopo. Um paper descoberto pelo escopo de agentes
# pode ser legitimamente `cache_kv`; `scope` diz por onde ele entrou, `familia`
# diz do que ele trata.
FAMILIAS = frozenset({
    # inferencia
    "quantizacao", "cache_kv", "decodificacao_especulativa",
    "esparsidade_e_poda", "kernels_e_atencao", "serving_e_batching",
    "arquitetura_eficiente", "destilacao", "treino_eficiente",
    # agentes
    "uso_de_ferramenta", "memoria_e_contexto", "planejamento_e_decomposicao",
    "orquestracao_multiagente", "avaliacao_de_agente", "recuperacao_de_falha",
    "agentes_de_codigo", "seguranca_e_guardrails", "recuperacao_e_rag",
    # Escape, e instrumento de medicao: sem ele o modelo e forcado a encaixar
    # mal e o erro fica invisivel. A frequencia de `outro` mede se a taxonomia
    # esta errada, e o gate da spec e 10%.
    "outro",
})

PRATICAS = frozenset({"adotar", "testar", "observar", "nao_aplica"})

# O que o leitor pode usar HOJE, com infra pequena. Traduz a regra "executavel
# primeiro" da spec original, que media hardware; agora mede aplicabilidade.
# `observar` exige escala que ele nao tem, `nao_aplica` esta fora do que faz --
# nenhum deve disputar uma das tres vagas do push com o acionavel.
ACIONAVEIS = frozenset({"adotar", "testar"})
GANHO_EIXOS = frozenset({"velocidade", "memoria", "custo", "qualidade", "nenhum"})
_VERSIONED = re.compile(r"v\d+$")


@dataclass(frozen=True)
class Paper:
    arxiv_id: str                 # chave canonica, SEM sufixo de versao
    title: str
    abstract: str
    authors: tuple[str, ...]
    categories: tuple[str, ...]
    published: str                # ISO date

    def __post_init__(self) -> None:
        if _VERSIONED.search(self.arxiv_id):
            raise ValueError(
                f"arxiv_id {self.arxiv_id!r} carrega versao; use a chave canonica "
                f"sem sufixo para que v1 e v2 nao virem entradas distintas"
            )
        # frozen=True protege reatribuicao de atributo, nao o conteudo de uma
        # lista. Sem coagir para tupla, Paper aceita mutacao interna E explode
        # em TypeError ao ser hasheado -- justamente o oposto do que arxiv_id
        # existe para fazer, que e servir de chave de deduplicacao.
        # Aceitar lista na construcao e devolver tupla mantem os chamadores
        # simples sem abrir mao da imutabilidade.
        object.__setattr__(self, "authors", tuple(self.authors))
        object.__setattr__(self, "categories", tuple(self.categories))


@dataclass(frozen=True)
class Discovery:
    """O resultado da descoberta do dia: o que entrou e o que foi descartado.

    A contagem viaja junto com os papers de proposito. Papers jogados fora
    dentro do cliente do arXiv -- por categoria fora do escopo, ou por um termo
    cuja consulta falhou -- desapareciam sem deixar rastro, e a restricao global
    do projeto e que TODO corte seja contado e chegue ao markdown do dia.
    """
    papers: list[Paper]
    cuts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Repo:
    full_name: str
    owner: str
    stars: int
    created_at: str        # ISO datetime


@dataclass(frozen=True)
class RepoClassification:
    repo: Repo
    is_author: bool
    reason: str | None     # qual regra disparou; auditavel no markdown


@dataclass(frozen=True)
class Signal:
    total_impls: int
    independent_impls: int
    velocity_14d: int
    stars_total: int
    # None = desconhecido, NUNCA zero. A distincao existe porque ~8% dos papers
    # nao resolvem no OpenAlex (arXiv so passou a cunhar DOI automatico por
    # volta de 2022), e gravar zero para esses recria o defeito que este campo
    # teve desde o dia um: 1088 linhas constantes em zero participando de uma
    # formula e de um portao.
    citations: int | None = None


@dataclass(frozen=True)
class ScoreResult:
    value: float | None    # None quando cortado no portao
    gated_by: str | None   # 'estrelas' | 'citacoes' | None

    @property
    def passed(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class Judgment:
    technique: str
    familia: str
    pratica: str
    ganho_eixo: str
    ganho_fator: float | None
    ganho_texto: str
    resumo: str
    porque: str

    def __post_init__(self) -> None:
        if self.familia not in FAMILIAS:
            raise ValueError(
                f"familia={self.familia!r} fora da taxonomia; "
                f"use um de {sorted(FAMILIAS)}"
            )
        if self.pratica not in PRATICAS:
            raise ValueError(
                f"pratica={self.pratica!r} invalida; use um de {sorted(PRATICAS)}"
            )
        if self.ganho_eixo not in GANHO_EIXOS:
            raise ValueError(
                f"ganho_eixo={self.ganho_eixo!r} invalido; "
                f"use um de {sorted(GANHO_EIXOS)}"
            )
        if self.ganho_eixo == "nenhum" and self.ganho_fator is not None:
            raise ValueError(
                f"ganho_fator={self.ganho_fator!r} com ganho_eixo='nenhum': "
                f"fator sem dimensao e numero solto"
            )
        if self.ganho_fator is not None and self.ganho_fator <= 0:
            raise ValueError(
                f"ganho_fator={self.ganho_fator!r} nao e razao de melhora; "
                f"precisa ser > 0"
            )
