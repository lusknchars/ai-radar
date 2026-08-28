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
    categories: tuple[str, ...]
    terms: tuple[str, ...]


DEFAULT_SCOPE = ScopeConfig(
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
