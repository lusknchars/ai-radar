"""Escopo e limiares.

O escopo estreito e o que mantem o digest legivel. Alargar aqui e a forma mais
facil de matar o projeto -- ver spec secao 1, nao-objetivos.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

PUSH_CAP = 3   # rigido por decisao de produto; nao configuravel


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
    push_cap: int = PUSH_CAP


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def load_thresholds() -> Thresholds:
    # push_cap deliberadamente NAO lido do ambiente: ver spec secao 9.
    return Thresholds(
        broke_out_stars=_env_int("RADAR_BROKE_OUT_STARS", 1000),
        broke_out_citations=_env_int("RADAR_BROKE_OUT_CITATIONS", 200),
        score_floor=_env_float("RADAR_SCORE_FLOOR", 0.0),
    )


def load_model() -> str:
    return os.environ.get("RADAR_MODEL") or "claude-opus-5"
