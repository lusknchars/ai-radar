"""Escopo e limiares.

O escopo estreito e o que mantem o digest legivel. Alargar aqui e a forma mais
facil de matar o projeto -- ver spec secao 1, nao-objetivos.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

# Local commands and scripts share one configuration file. Environment
# variables still win, which keeps GitHub Actions and explicit shell exports
# predictable.
load_dotenv(override=False)

# Rigido por decisao de produto, e por isso mora AQUI e em lugar nenhum mais:
# nao e campo de Thresholds, nao sai do ambiente, nao entra por argumento. O
# pipeline fatia por ele e o render guarda por ele -- a mesma constante nos dois
# lados, para que nao exista jeito de expressar um teto diferente.
PUSH_CAP = 3

# Configuravel, ao contrario de PUSH_CAP: aquele e decisao de produto sobre
# legibilidade do digest; este e orcamento operacional, que muda com o tamanho
# do banco e com a presenca de GH_TOKEN.
RECHECK_LIMIT = 30

DEFAULT_REPOSITORY = "lusknchars/ai-radar"
_GITHUB_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class PublicConfig:
    """Public links used by the static archive.

    Keeping these values together prevents a fork from publishing links that
    still point to the original repository.
    """

    repository: str
    base_path: str
    site_url: str

    def __post_init__(self) -> None:
        parts = self.repository.split("/")
        if len(parts) != 2 or not all(_GITHUB_NAME.fullmatch(part) for part in parts):
            raise ValueError(
                "RADAR_REPOSITORY must use the GitHub owner/repository format"
            )
        if self.base_path and (
            not self.base_path.startswith("/") or self.base_path.endswith("/")
        ):
            raise ValueError(
                "RADAR_SITE_BASE_PATH must be empty or look like /repository"
            )
        parsed = urlsplit(self.site_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("RADAR_SITE_URL must be an absolute HTTP(S) URL")

    def path(self, resource: str = "") -> str:
        """Return a root-relative URL below the configured Pages base path."""
        resource = resource.lstrip("/")
        if not resource:
            return f"{self.base_path}/" if self.base_path else "/"
        prefix = self.base_path or ""
        return f"{prefix}/{resource}"


DEFAULT_PUBLIC_CONFIG = PublicConfig(
    repository=DEFAULT_REPOSITORY,
    base_path="/ai-radar",
    site_url="https://lusknchars.github.io/ai-radar",
)


def _normalise_base_path(value: str) -> str:
    value = value.strip()
    if value in {"", "/"}:
        return ""
    return "/" + value.strip("/")


def load_public_config() -> PublicConfig:
    """Load URLs for this fork, deriving conventional GitHub Pages defaults."""
    repository = (
        os.environ.get("RADAR_REPOSITORY")
        or os.environ.get("GITHUB_REPOSITORY")
        or DEFAULT_REPOSITORY
    ).strip()
    parts = repository.split("/")
    if len(parts) != 2 or not all(_GITHUB_NAME.fullmatch(part) for part in parts):
        raise ValueError(
            "RADAR_REPOSITORY must use the GitHub owner/repository format"
        )
    owner, name = parts
    default_base = "" if name.lower() == f"{owner.lower()}.github.io" else f"/{name}"
    configured_base = os.environ.get("RADAR_SITE_BASE_PATH")
    base_path = _normalise_base_path(
        default_base if configured_base is None else configured_base
    )
    site_url = (
        os.environ.get("RADAR_SITE_URL")
        or f"https://{owner}.github.io{base_path}"
    ).strip().rstrip("/")
    return PublicConfig(
        repository=repository,
        base_path=base_path,
        site_url=site_url,
    )


def load_database_path() -> Path:
    """Database selected for local commands; Actions keeps the legacy default."""
    return Path(os.environ.get("RADAR_DB") or "data/radar.db")


@dataclass(frozen=True)
class ScopeConfig:
    # `name` vem primeiro e nao tem default: e o que impede escopo anonimo de
    # chegar ao banco. A coluna `papers.scope` existe para fatiar o acervo, e
    # um default aqui deixaria um chamador novo gravar linha sem escopo calado.
    name: str                      # 'observatorio' | 'inferencia' | 'agentes'
    categories: tuple[str, ...]
    terms: tuple[str, ...]
    # Cada grupo e um OR; todos os grupos precisam casar no titulo ou abstract.
    # O arXiv continua responsavel pelo recall. Este filtro local impede que um
    # termo amplo, como "latency", admita um paper sem relacao com LLMs.
    required_term_groups: tuple[tuple[str, ...], ...] = ()


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


# Escopo padrao do produto. A pergunta nao e "este paper melhora inferencia?",
# que ainda admite treino, hardware custom e compressao de outros dominios. A
# pergunta e "este paper muda algo que uma sonda externa consegue medir em um
# endpoint publico de LLM?". Os termos de consulta favorecem recall; os dois
# grupos obrigatorios recuperam precisao antes de qualquer chamada paga.
OBSERVATORY_SCOPE = ScopeConfig(
    name="observatorio",
    categories=("cs.LG", "cs.CL", "cs.DC", "cs.PF", "cs.AI"),
    terms=(
        "time to first token",
        "inter-token latency",
        "inference latency",
        "tail latency",
        "streaming inference",
        "model serving",
        "continuous batching",
        "KV cache",
        "prefix caching",
        "speculative decoding",
        "model routing",
        "API reliability",
        "behavioral drift",
        "model drift",
        "output stability",
    ),
    required_term_groups=(
        (
            "large language model",
            "language model",
            "llm",
            "foundation model",
            "generative model",
            "model api",
            "inference server",
            "model serving",
            "chatbot",
        ),
        (
            "time to first token",
            "ttft",
            "inter token latency",
            "decode latency",
            "inference latency",
            "tail latency",
            "tokens per second",
            "streaming inference",
            "streaming response",
            "streaming api",
            "availability",
            "api reliability",
            "service level objective",
            "model routing",
            "inference routing",
            "behavioral drift",
            "model drift",
            "version drift",
            "silent model update",
            "output stability",
            "prompt sensitivity",
            "cross linguistic",
            "multilingual consistency",
            "speculative decoding",
            "kv cache",
            "prefix cache",
            "continuous batching",
            "inference cost",
            "api cost",
        ),
    ),
)


_SCOPES = {
    OBSERVATORY_SCOPE.name: OBSERVATORY_SCOPE,
    DEFAULT_SCOPE.name: DEFAULT_SCOPE,
    AGENT_SCOPE.name: AGENT_SCOPE,
}


def load_scopes() -> tuple[ScopeConfig, ...]:
    """Select daily lanes. Production defaults to the Observatory lane only."""
    configured = os.environ.get("RADAR_SCOPES") or OBSERVATORY_SCOPE.name
    names = [name.strip().lower() for name in configured.split(",") if name.strip()]
    if not names:
        raise ValueError("RADAR_SCOPES must name at least one scope")
    unknown = [name for name in names if name not in _SCOPES]
    if unknown:
        raise ValueError(
            f"RADAR_SCOPES contains unknown scopes: {', '.join(unknown)}; "
            f"use one or more of {', '.join(_SCOPES)}"
        )
    # A primeira ocorrencia decide a ordem e, portanto, qual escopo recebe um
    # paper que duas consultas encontram.
    return tuple(_SCOPES[name] for name in dict.fromkeys(names))


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
    provider = load_llm_provider()
    default = "kimi-k3" if provider == "kimi" else "claude-opus-5"
    return os.environ.get("RADAR_MODEL") or default


def load_formula_model() -> str:
    """Modelo estreito para selecionar candidatos, sem rebaixar o relatorio."""
    return os.environ.get("RADAR_FORMULA_MODEL") or "kimi-k2.6"


def load_formula_thinking() -> str:
    """Modo de raciocinio aceito pelo request nativo do K2.6."""
    mode = (os.environ.get("RADAR_FORMULA_THINKING") or "disabled").strip().lower()
    if mode not in {"enabled", "disabled"}:
        raise ValueError(
            f"RADAR_FORMULA_THINKING={mode!r} invalido; "
            "use 'enabled' ou 'disabled'"
        )
    return mode


def load_pdf_extractor() -> str:
    """Parser do relatorio profundo; o radar diario nunca baixa o PDF."""
    name = (os.environ.get("RADAR_PDF_EXTRACTOR") or "pypdf").strip().lower()
    if name not in {"pypdf", "docling"}:
        raise ValueError(
            f"RADAR_PDF_EXTRACTOR={name!r} invalido; use 'pypdf' ou 'docling'"
        )
    return name


def load_llm_provider() -> str:
    """Escolhe o adaptador sem confundir nome de modelo com protocolo.

    A variavel explicita vence. Sem ela, uma instalacao que tenha apenas a
    chave da Kimi usa Kimi; todos os demais casos preservam Anthropic como o
    comportamento historico.
    """
    configured = os.environ.get("RADAR_LLM_PROVIDER")
    if configured:
        provider = configured.strip().lower()
    elif os.environ.get("KIMI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        provider = "kimi"
    else:
        provider = "anthropic"
    if provider not in {"anthropic", "kimi"}:
        raise ValueError(
            f"RADAR_LLM_PROVIDER={provider!r} invalido; use 'anthropic' ou 'kimi'"
        )
    return provider


def load_kimi_request_interval() -> float:
    """Intervalo conservador para contas Kimi no tier inicial de 3 RPM."""
    return _env_float("RADAR_KIMI_REQUEST_INTERVAL", 20.0)


def load_kimi_base_url() -> str:
    """Endpoint da mesma regiao onde a chave e os creditos foram criados."""
    return (os.environ.get("RADAR_KIMI_BASE_URL")
            or "https://api.moonshot.ai/v1").rstrip("/")


def load_recheck_limit() -> int:
    return _env_int("RADAR_RECHECK_LIMIT", RECHECK_LIMIT)
