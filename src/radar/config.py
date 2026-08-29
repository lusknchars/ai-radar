"""Escopo e limiares.

O escopo estreito e o que mantem o digest legivel. Alargar aqui e a forma mais
facil de matar o projeto -- ver spec secao 1, nao-objetivos.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Rigido por decisao de produto, e por isso mora AQUI e em lugar nenhum mais:
# nao e campo de Thresholds, nao sai do ambiente, nao entra por argumento. O
# pipeline fatia por ele e o render guarda por ele -- a mesma constante nos dois
# lados, para que nao exista jeito de expressar um teto diferente.
PUSH_CAP = 3

# Configuravel, ao contrario de PUSH_CAP: aquele e decisao de produto sobre
# legibilidade do digest; este e orcamento operacional, que muda com o tamanho
# do banco e com a presenca de GH_TOKEN.
RECHECK_LIMIT = 30


@dataclass(frozen=True)
class ScopeConfig:
    # `name` vem primeiro e nao tem default: e o que impede escopo anonimo de
    # chegar ao banco. A coluna `papers.scope` existe para fatiar o acervo, e
    # um default aqui deixaria um chamador novo gravar linha sem escopo calado.
    name: str                      # 'inferencia' | 'agentes'
    categories: tuple[str, ...]
    terms: tuple[str, ...]


DEFAULT_SCOPE = ScopeConfig(
    name="inferencia",
    categories=("cs.LG", "cs.CL", "cs.DC", "cs.AR", "cs.PF"),
    terms=(
        "quantization",
        "speculative decoding",
        "KV cache",
        "inference latency",
        "inference throughput",
        "sparsity",
        "pruning",
        "low-rank",
        "attention kernel",
        "memory bandwidth",
        "model serving",
        "efficient inference",
    ),
)

# Medido em 2026-08-29 pela mesma consulta que o pipeline usa: ~25 papers/dia.
# A lista ingenua tinha 20 termos sobre cs.AI/cs.CL/cs.LG/cs.SE/cs.MA e dava
# ~75/dia, com `agentic`, `trajectory` e `planning` saturando o teto de 200 por
# semana -- os tres capturam trajetoria de robo e planejamento classico, nao
# harness. Tirar cs.LG e os tres cortou dois tercos do volume sem perder nada
# especifico de harness. `tool retrieval` ficou de fora por medicao: zero
# papers ineditos, tudo que ele acha ja vem por `tool use` ou `tool calling`.
AGENT_SCOPE = ScopeConfig(
    name="agentes",
    categories=("cs.AI", "cs.CL", "cs.SE", "cs.MA"),
    terms=(
        "agent harness",
        "LLM agent",
        "agent trajectory",
        "tool use",
        "tool calling",
        "function calling",
        "agent memory",
        "context management",
        "context engineering",
        "prompt caching",
        "agent evaluation",
        "agent benchmark",
        "computer use",
        "code agent",
        "self-correction",
        "guardrail",
        "agent orchestration",
    ),
)


@dataclass(frozen=True)
class Thresholds:
    broke_out_stars: int
    broke_out_citations: int
    score_floor: float


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def load_thresholds() -> Thresholds:
    # Os tres limiares abaixo sao calibraveis por ambiente; o teto do push nao
    # e um deles. Ele nao aparece aqui porque nao existe como campo: ver
    # PUSH_CAP acima.
    return Thresholds(
        broke_out_stars=_env_int("RADAR_BROKE_OUT_STARS", 1000),
        broke_out_citations=_env_int("RADAR_BROKE_OUT_CITATIONS", 200),
        score_floor=_env_float("RADAR_SCORE_FLOOR", 0.0),
    )


def load_model() -> str:
    return os.environ.get("RADAR_MODEL") or "claude-opus-5"


def load_recheck_limit() -> int:
    return _env_int("RADAR_RECHECK_LIMIT", RECHECK_LIMIT)
