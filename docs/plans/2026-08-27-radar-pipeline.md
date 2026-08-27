# Radar de Técnicas — Plano de Implementação

> **Para executores agênticos:** SUB-SKILL OBRIGATÓRIA: usar `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans` para implementar tarefa a tarefa. Os passos usam checkbox (`- [ ]`) para rastreio.

**Objetivo:** um pipeline diário que descobre papers de inferência e eficiência no arXiv, pontua cada um pelo sinal de implementação independente no GitHub, julga com LLM, e entrega três itens no Telegram mais o feed completo em markdown versionado.

**Arquitetura:** núcleo puro, borda fina de IO. Parsing, heurística de autoria, pontuação e renderização são funções puras testáveis sem rede. Cada serviço externo — arXiv, GitHub, Anthropic, Telegram — fica atrás de um adaptador estreito que recebe o cliente HTTP por injeção. Isso torna toda a lógica testável num Mac offline, e deixa só quatro pontos onde a rede importa.

**Stack:** Python 3.12, `anthropic`, `httpx`, `pydantic`, `pytest`, sqlite3 (stdlib).

**Spec:** `docs/2026-08-27-radar-spec.md`

---

## Restrições globais

**Git exige aprovação por ação.** Nenhum `git init`, `git add`, `git commit`, `git push` ou criação de repositório sem aprovação explícita do Lucas para aquela ação específica. Os passos de commit deste plano são **propostas**: mostrar o comando e esperar o sim. O commit feito pelo workflow em execução é outra coisa — é o robô operando dentro de um repositório já autorizado.

**Sem trailer de co-autoria** em nenhuma mensagem de commit.

**Modelo:** `claude-opus-5`, lido de `RADAR_MODEL` com esse default. Nunca trocar por modelo mais barato sem o usuário pedir.

**Comparação sempre por bpw... não — por score com portão.** Nenhum caminho no código ordena por estrelas, citações ou data. A ordenação do radar é sempre `ScoreResult.value`, e itens com `gated_by` preenchido nunca entram no push.

**Ordem do push é (executável, score), nunca score puro.** Itens com `runs_on_3090 == "nao"` vêm depois de todos os executáveis, e só entram se sobrar vaga.

**Teto de 3 é rígido.** Nenhum caminho no código ultrapassa. Se menos de 3 passarem o piso, manda menos. Se zero passarem, não manda nada.

**Nada de truncamento silencioso.** Todo corte é contado com motivo e sai no markdown do dia.

**Sem emoji** no push do Telegram nem no markdown.

**Testes rodam sem rede.** Toda tarefa tem testes que passam offline. Adaptadores recebem o cliente HTTP por injeção; testes passam duplos.

**arXiv exige HTTPS e User-Agent.** Em HTTP a API devolve 301 com corpo vazio — e como `raise_for_status()` não levanta em 3xx e o httpx não segue redirect por padrão, o chamador recebe zero byte sem erro. Está codificado no adaptador e travado por teste.

---

## Estrutura de arquivos

```
ai-radar/
  pyproject.toml
  src/radar/
    __init__.py
    models.py       Paper, Repo, RepoClassification, Signal, ScoreResult, Judgment
    config.py       categorias, termos de escopo, limiares, leitura de env
    scoring.py      portao de atencao + razao (puro)
    authorship.py   heuristica is_author (pura)
    arxiv.py        adaptador arXiv: monta query, parseia Atom
    github.py       adaptador GitHub: busca por arXiv ID, parseia resposta
    store.py        SQLite: schema, upsert, delta, deliveries
    judge.py        LLM: schema pydantic, prompt, chamada normal e batch
    render.py       markdown do dia + formato do push (puro)
    telegram.py     adaptador de envio
    pipeline.py     orquestracao
    cli.py          ponto de entrada
  tests/
    fixtures/arxiv_response.xml
    fixtures/github_search.json
    test_*.py
  .github/workflows/radar.yml
```

Regra de fronteira: `scoring.py`, `authorship.py` e `render.py` não importam `httpx`, `anthropic` nem `sqlite3`. Se algum dia importarem, a fronteira foi violada.

---

## Tarefa 1: Scaffold, modelos e configuração de escopo

**Arquivos:**
- Criar: `pyproject.toml`, `src/radar/__init__.py`, `src/radar/models.py`, `src/radar/config.py`
- Teste: `tests/test_config.py`

**Interfaces:**
- Consome: nada.
- Produz: as dataclasses `Paper`, `Repo`, `RepoClassification`, `Signal`, `ScoreResult`, `Judgment`, e `ScopeConfig` / `Thresholds`. Todas as tarefas seguintes dependem destes tipos.

- [ ] **Passo 1: Criar o scaffold**

`pyproject.toml`:

```toml
[project]
name = "radar"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27", "anthropic>=0.40", "pydantic>=2.7"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Criar `src/radar/__init__.py` e `tests/__init__.py` vazios.

- [ ] **Passo 2: Escrever o teste que falha**

`tests/test_config.py`:

```python
import pytest

from radar.config import DEFAULT_SCOPE, load_thresholds
from radar.models import Judgment, Paper, Signal


def test_scope_covers_the_five_arxiv_categories():
    assert set(DEFAULT_SCOPE.categories) == {"cs.LG", "cs.CL", "cs.DC", "cs.AR", "cs.PF"}


def test_scope_terms_are_non_empty_and_unique():
    terms = DEFAULT_SCOPE.terms
    assert len(terms) >= 10
    assert len(terms) == len(set(terms))


def test_scope_excludes_out_of_scope_domains():
    """O escopo estreito e deliberado: visao, audio e agentes ficam de fora."""
    joined = " ".join(DEFAULT_SCOPE.terms).lower()
    for banned in ("vision", "speech", "robot", "agent", "retrieval"):
        assert banned not in joined


def test_paper_is_frozen_and_keyed_by_arxiv_id():
    p = Paper(arxiv_id="2508.12345", title="T", abstract="A",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-01")
    assert p.arxiv_id == "2508.12345"
    with pytest.raises(Exception):
        p.arxiv_id = "outro"


def test_paper_rejects_versioned_arxiv_id():
    """A chave canonica nao carrega versao: v1 e v2 sao o mesmo paper."""
    with pytest.raises(ValueError, match="versao"):
        Paper(arxiv_id="2508.12345v2", title="T", abstract="A",
              authors=[], categories=["cs.LG"], published="2026-08-01")


def test_paper_is_hashable_so_it_can_serve_as_a_dedup_key():
    """arxiv_id canonico existe para deduplicar. Um Paper nao-hashavel
    explodiria no primeiro `set(papers)` do pipeline."""
    p = Paper(arxiv_id="2508.12345", title="T", abstract="A",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-01")
    assert len({p, p}) == 1


def test_paper_coerces_sequences_so_contents_cannot_be_mutated():
    """frozen=True sozinho protege a reatribuicao, nao o conteudo da lista."""
    p = Paper(arxiv_id="2508.12345", title="T", abstract="A",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-01")
    assert p.authors == ("Elias Frantar",)
    assert p.categories == ("cs.LG",)
    with pytest.raises(AttributeError):
        p.authors.append("intruso")


def test_signal_defaults_citations_to_zero():
    s = Signal(total_impls=4, independent_impls=3, velocity_14d=1, stars_total=60)
    assert s.citations == 0


def test_judgment_rejects_unknown_verdict():
    with pytest.raises(ValueError, match="runs_on_3090"):
        Judgment(technique="T", summary="S", runs_on_3090="talvez", rationale="R")


def test_judgment_accepts_the_three_valid_verdicts():
    for verdict in ("sim", "sim_com_ressalva", "nao"):
        j = Judgment(technique="T", summary="S", runs_on_3090=verdict, rationale="R")
        assert j.runs_on_3090 == verdict


def test_thresholds_come_from_env_with_documented_defaults(monkeypatch):
    monkeypatch.delenv("RADAR_BROKE_OUT_STARS", raising=False)
    monkeypatch.delenv("RADAR_BROKE_OUT_CITATIONS", raising=False)
    monkeypatch.delenv("RADAR_SCORE_FLOOR", raising=False)
    t = load_thresholds()
    assert t.broke_out_stars == 1000
    assert t.broke_out_citations == 200
    assert t.score_floor == 0.0        # nao calibrado; ver spec secao 10
    assert t.push_cap == 3


def test_push_cap_cannot_be_raised_by_env(monkeypatch):
    """O teto de 3 e rigido por decisao de produto, nao configuracao."""
    monkeypatch.setenv("RADAR_PUSH_CAP", "10")
    assert load_thresholds().push_cap == 3


def test_model_defaults_to_opus_5(monkeypatch):
    monkeypatch.delenv("RADAR_MODEL", raising=False)
    from radar.config import load_model
    assert load_model() == "claude-opus-5"
```

- [ ] **Passo 3: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_config.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.config'`

- [ ] **Passo 4: Implementar os modelos**

`src/radar/models.py`:

```python
"""Tipos compartilhados. Nenhum IO, nenhuma dependencia externa alem de stdlib."""
from __future__ import annotations

import re
from dataclasses import dataclass

VALID_VERDICTS = frozenset({"sim", "sim_com_ressalva", "nao"})
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
    citations: int = 0


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
    summary: str
    runs_on_3090: str
    rationale: str

    def __post_init__(self) -> None:
        if self.runs_on_3090 not in VALID_VERDICTS:
            raise ValueError(
                f"runs_on_3090={self.runs_on_3090!r} invalido; "
                f"use um de {sorted(VALID_VERDICTS)}"
            )
```

- [ ] **Passo 5: Implementar a configuração**

`src/radar/config.py`:

```python
"""Escopo e limiares.

O escopo estreito e o que mantem o digest legivel. Alargar aqui e a forma mais
facil de matar o projeto -- ver spec secao 1, nao-objetivos.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

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
    # push_cap passado explicitamente a partir da constante, NUNCA do ambiente
    # (spec secao 9). Explicito aqui para que a invariante fique visivel no
    # ponto de chamada, e nao escondida num default de dataclass.
    return Thresholds(
        broke_out_stars=_env_int("RADAR_BROKE_OUT_STARS", 1000),
        broke_out_citations=_env_int("RADAR_BROKE_OUT_CITATIONS", 200),
        score_floor=_env_float("RADAR_SCORE_FLOOR", 0.0),
        push_cap=PUSH_CAP,
    )


def load_model() -> str:
    return os.environ.get("RADAR_MODEL") or "claude-opus-5"
```

- [ ] **Passo 6: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_config.py -v`
Esperado: 13 passed

- [ ] **Passo 7: Propor commit (aguardar aprovação)**

```bash
git add pyproject.toml src/radar/ tests/
git commit -m "feat: modelos, escopo e limiares com teto de push rigido"
```

---

## Tarefa 2: Pontuação — portão de atenção e razão

**Arquivos:**
- Criar: `src/radar/scoring.py`
- Teste: `tests/test_scoring.py`

**Interfaces:**
- Consome: `Signal`, `ScoreResult`, `Thresholds` da Tarefa 1.
- Produz: `evaluate(signal, thresholds) -> ScoreResult`. Usada pelo pipeline da Tarefa 10.

**Nota:** os casos de teste abaixo vêm da verificação numérica que derrubou a primeira versão da fórmula. São regressão, não exemplo.

- [ ] **Passo 1: Escrever o teste que falha**

`tests/test_scoring.py`:

```python
import pytest

from radar.config import Thresholds
from radar.models import Signal
from radar.scoring import evaluate

T = Thresholds(broke_out_stars=1000, broke_out_citations=200, score_floor=0.0)


def sig(indep, vel, stars, cites, total=None):
    return Signal(total_impls=total if total is not None else indep,
                  independent_impls=indep, velocity_14d=vel,
                  stars_total=stars, citations=cites)


def test_famous_paper_is_gated_out_by_stars():
    """GPTQ real: 103 impls, 3000 estrelas, 2500 citacoes. Ja estourou."""
    r = evaluate(sig(103, 2, 3000, 2500), T)
    assert r.value is None
    assert r.gated_by == "estrelas"


def test_paper_is_gated_out_by_citations_alone():
    r = evaluate(sig(5, 1, 50, 500), T)
    assert r.value is None
    assert r.gated_by == "citacoes"


def test_hidden_gem_outranks_everything_that_passes():
    gem = evaluate(sig(4, 3, 60, 0), T).value
    novo = evaluate(sig(2, 2, 15, 0), T).value
    revival = evaluate(sig(9, 7, 340, 120), T).value
    assert gem > novo > revival


def test_hidden_gem_score_matches_the_verified_value():
    """Regressao numerica: valor conferido na revisao da spec."""
    assert evaluate(sig(4, 3, 60, 0), T).value == pytest.approx(0.5332, abs=1e-4)


def test_no_independent_implementation_scores_zero():
    """So os autores publicaram. Nenhum sinal, mas passa o portao."""
    r = evaluate(sig(0, 0, 800, 30, total=3), T)
    assert r.value == pytest.approx(0.0)
    assert r.gated_by is None


def test_velocity_increases_the_score_at_equal_implementations():
    parado = evaluate(sig(5, 0, 100, 0), T).value
    acelerando = evaluate(sig(5, 5, 100, 0), T).value
    assert acelerando > parado


def test_attention_decreases_the_score_at_equal_implementations():
    obscuro = evaluate(sig(5, 2, 10, 0), T).value
    conhecido = evaluate(sig(5, 2, 900, 0), T).value
    assert obscuro > conhecido


def test_gate_is_exclusive_not_inclusive_at_the_boundary():
    exatamente = evaluate(sig(3, 1, 1000, 0), T)
    um_acima = evaluate(sig(3, 1, 1001, 0), T)
    assert exatamente.passed is True
    assert um_acima.passed is False


def test_stars_gate_is_reported_when_both_gates_would_fire():
    r = evaluate(sig(3, 1, 5000, 5000), T)
    assert r.gated_by == "estrelas"


def test_thresholds_are_respected_not_hardcoded():
    frouxo = Thresholds(broke_out_stars=100000, broke_out_citations=100000, score_floor=0.0)
    assert evaluate(sig(103, 2, 3000, 2500), frouxo).passed is True


def test_negative_input_is_rejected():
    with pytest.raises(ValueError, match="negativ"):
        evaluate(sig(-1, 0, 0, 0), T)
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_scoring.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.scoring'`

- [ ] **Passo 3: Implementar**

`src/radar/scoring.py`:

```python
"""Portao de atencao, depois razao. A ordem importa.

A primeira versao usava so a razao. Um teste com os numeros reais do GPTQ
(103 impls, 3000 estrelas, 2500 citacoes) colocou o paper de quantizacao mais
famoso que existe em terceiro lugar: log1p comprime demais no topo, e um
numerador enorme quase compensa um denominador enorme.

Um paper que ja estourou nao e material de radar por definicao. Ele nao recebe
score baixo -- ele nao e pontuado. Com o portao, a razao so precisa ordenar
dentro do conjunto "ainda nao estourou", que e um trabalho muito mais facil.
"""
from __future__ import annotations

from math import log1p

from .config import Thresholds
from .models import ScoreResult, Signal


def evaluate(signal: Signal, thresholds: Thresholds) -> ScoreResult:
    for name, value in (
        ("total_impls", signal.total_impls),
        ("independent_impls", signal.independent_impls),
        ("velocity_14d", signal.velocity_14d),
        ("stars_total", signal.stars_total),
        ("citations", signal.citations),
    ):
        if value < 0:
            raise ValueError(f"{name} negativo: {value}")

    # Etapa 1: portao. Estrelas antes de citacoes -- o motivo reportado e o
    # primeiro que dispara, e estrelas sao o sinal mais imediato de que estourou.
    if signal.stars_total > thresholds.broke_out_stars:
        return ScoreResult(value=None, gated_by="estrelas")
    if signal.citations > thresholds.broke_out_citations:
        return ScoreResult(value=None, gated_by="citacoes")

    # Etapa 2: razao entre os que passaram.
    strength = log1p(signal.independent_impls) * (1 + 0.5 * log1p(signal.velocity_14d))
    attention = log1p(signal.stars_total) + log1p(signal.citations)
    return ScoreResult(value=strength / (1 + attention), gated_by=None)
```

- [ ] **Passo 4: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_scoring.py -v`
Esperado: 11 passed

- [ ] **Passo 5: Propor commit (aguardar aprovação)**

```bash
git add src/radar/scoring.py tests/test_scoring.py
git commit -m "feat: pontuacao com portao de atencao antes da razao"
```

---

## Tarefa 3: Heurística de autoria

**Arquivos:**
- Criar: `src/radar/authorship.py`
- Teste: `tests/test_authorship.py`

**Interfaces:**
- Consome: `Repo`, `RepoClassification` da Tarefa 1.
- Produz: `classify_repos(repos, authors, abstract) -> list[RepoClassification]`. Usada pela Tarefa 5 ao montar o `Signal`.

**Nota de desenho:** o casamento por sobrenome só usa substring quando o sobrenome tem 4 caracteres ou mais. Sobrenomes curtos como "Lin", "Xu" ou "He" casariam com metade do GitHub (`linux-foundation`, `linkedin`) e envenenariam o sinal.

- [ ] **Passo 1: Escrever o teste que falha**

`tests/test_authorship.py`:

```python
from radar.authorship import classify_repos, normalize
from radar.models import Repo


def repo(full_name, stars, created_at):
    return Repo(full_name=full_name, owner=full_name.split("/")[0],
                stars=stars, created_at=created_at)


def test_normalize_strips_accents_case_and_punctuation():
    assert normalize("Frantar") == "frantar"
    assert normalize("Elías-Gonçalves") == "eliasgoncalves"


def test_owner_matching_author_surname_is_flagged():
    repos = [repo("efrantar/gptq-fast", 30, "2024-01-01T00:00:00Z"),
             repo("someone/other", 20, "2024-02-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Elias Frantar"], "")}
    assert out["efrantar/gptq-fast"].is_author is True
    assert out["efrantar/gptq-fast"].reason == "sobrenome"
    assert out["someone/other"].is_author is False


def test_short_surname_does_not_match_by_substring():
    """'Lin' casaria com linux-foundation, linkedin, linear-ai...

    O segundo repo existe para ISOLAR a regra sob teste: com um repo so,
    'mais antigo E mais estrelado' dispara sozinha e o teste passaria (ou
    falharia) sem nunca exercitar o casamento por sobrenome.
    """
    repos = [repo("linux-foundation/serving", 40, "2024-01-01T00:00:00Z"),
             repo("outro/mais-estrelado", 500, "2024-02-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Ji Lin"], "")}
    assert out["linux-foundation/serving"].is_author is False


def test_short_surname_still_matches_exactly():
    repos = [repo("lin/impl", 40, "2024-01-01T00:00:00Z"),
             repo("outro/mais-estrelado", 500, "2024-02-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Ji Lin"], "")}
    assert out["lin/impl"].is_author is True
    # Conferir a RAZAO, nao so o booleano: sem isso o teste passa pelo
    # motivo errado quando outra regra dispara.
    assert out["lin/impl"].reason == "sobrenome"


def test_repo_named_in_the_abstract_is_flagged():
    repos = [repo("acme/official-impl", 5, "2024-03-01T00:00:00Z")]
    abstract = "Code is available at https://github.com/acme/official-impl"
    out = classify_repos(repos, ["Someone Else"], abstract)
    assert out[0].is_author is True
    assert out[0].reason == "citado_no_abstract"


def test_oldest_and_most_starred_is_presumed_official():
    """Cobre o laboratorio que publica sob nome de organizacao, como
    IST-DASLab/gptq, que nenhum sobrenome alcanca."""
    repos = [repo("IST-DASLab/gptq", 2360, "2022-10-19T00:00:00Z"),
             repo("fpgaminer/GPTQ-triton", 322, "2023-03-28T00:00:00Z"),
             repo("davisyoshida/jax-gptq", 10, "2023-05-05T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Elias Frantar"], "")}
    assert out["IST-DASLab/gptq"].is_author is True
    assert out["IST-DASLab/gptq"].reason == "mais_antigo_e_mais_estrelado"
    assert out["fpgaminer/GPTQ-triton"].is_author is False
    assert out["davisyoshida/jax-gptq"].is_author is False


def test_oldest_but_not_most_starred_is_not_presumed_official():
    repos = [repo("a/first", 5, "2022-01-01T00:00:00Z"),
             repo("b/popular", 900, "2023-01-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, [], "")}
    assert out["a/first"].is_author is False
    assert out["b/popular"].is_author is False


def test_single_repo_is_presumed_official():
    out = classify_repos([repo("solo/only", 5, "2024-01-01T00:00:00Z")], [], "")
    assert out[0].is_author is True


def test_every_classification_carries_an_auditable_reason():
    repos = [repo("efrantar/x", 10, "2024-01-01T00:00:00Z"),
             repo("outro/y", 5, "2024-02-01T00:00:00Z")]
    for c in classify_repos(repos, ["Elias Frantar"], ""):
        if c.is_author:
            assert c.reason, "toda flag de autoria precisa registrar qual regra disparou"
        else:
            assert c.reason is None


def test_empty_repo_list_returns_empty():
    assert classify_repos([], ["A B"], "") == []
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_authorship.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.authorship'`

- [ ] **Passo 3: Implementar**

`src/radar/authorship.py`:

```python
"""Heuristica para separar o repo dos autores das reimplementacoes de terceiros.

Esta e a maior fonte de erro do score, e o erro e assimetrico e conhecido:
laboratorio publicando sob nome de organizacao nao casa por sobrenome, e uma
reimplementacao de terceiro que por acaso seja a mais antiga e a mais estrelada
e marcada como autor por engano.

Nao ha correcao automatica. A mitigacao e registrar QUAL regra disparou, para
que toda decisao seja auditavel no markdown do dia.
"""
from __future__ import annotations

import unicodedata
from typing import Sequence

from .models import Repo, RepoClassification

MIN_SURNAME_FOR_SUBSTRING = 4


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


def _surnames(authors: Sequence[str]) -> list[str]:
    out = []
    for author in authors:
        parts = author.split()
        if parts:
            out.append(normalize(parts[-1]))
    return [s for s in out if s]


def _matches_surname(owner: str, surnames: list[str]) -> bool:
    norm_owner = normalize(owner)
    for surname in surnames:
        if len(surname) >= MIN_SURNAME_FOR_SUBSTRING:
            if surname in norm_owner:
                return True
        elif surname == norm_owner:
            return True
    return False


def classify_repos(
    repos: list[Repo], authors: Sequence[str], abstract: str
) -> list[RepoClassification]:
    if not repos:
        return []

    surnames = _surnames(authors)
    norm_abstract = abstract.lower()

    oldest = min(repos, key=lambda r: r.created_at)
    most_starred = max(repos, key=lambda r: r.stars)
    presumed_official = oldest.full_name if oldest.full_name == most_starred.full_name else None

    out: list[RepoClassification] = []
    for repo in repos:
        reason: str | None = None
        if _matches_surname(repo.owner, surnames):
            reason = "sobrenome"
        elif repo.full_name.lower() in norm_abstract:
            reason = "citado_no_abstract"
        elif repo.full_name == presumed_official:
            reason = "mais_antigo_e_mais_estrelado"
        out.append(RepoClassification(repo=repo, is_author=reason is not None, reason=reason))
    return out
```

- [ ] **Passo 4: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_authorship.py -v`
Esperado: 10 passed

- [ ] **Passo 5: Propor commit (aguardar aprovação)**

```bash
git add src/radar/authorship.py tests/test_authorship.py
git commit -m "feat: heuristica de autoria com guarda para sobrenome curto"
```

---

## Tarefa 4: Adaptador arXiv

**Arquivos:**
- Criar: `src/radar/arxiv.py`, `tests/fixtures/arxiv_response.xml`
- Teste: `tests/test_arxiv.py`

**Interfaces:**
- Consome: `Paper`, `ScopeConfig` das Tarefas 1.
- Produz: `build_query(term, scope) -> str`, `parse_feed(xml_text) -> list[Paper]`, `ArxivClient(fetch).recent(scope) -> list[Paper]`. `fetch` é injetado: recebe uma URL e devolve texto.

- [ ] **Passo 1: Criar a fixture**

`tests/fixtures/arxiv_response.xml`:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2608.11111v2</id>
    <published>2026-08-20T10:00:00Z</published>
    <title>Fused INT4 Kernels for Ampere Inference</title>
    <summary>  We present a fused INT4 by FP16 kernel that saturates
  memory bandwidth at batch size one.  </summary>
    <author><name>Elias Frantar</name></author>
    <author><name>Ji Lin</name></author>
    <arxiv:primary_category term="cs.LG"/>
    <category term="cs.LG"/>
    <category term="cs.AR"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2608.22222v1</id>
    <published>2026-08-19T08:30:00Z</published>
    <title>A Survey of Speech Recognition Models</title>
    <summary>Unrelated to the scope.</summary>
    <author><name>Someone Else</name></author>
    <arxiv:primary_category term="eess.AS"/>
    <category term="eess.AS"/>
  </entry>
</feed>
```

- [ ] **Passo 2: Escrever o teste que falha**

`tests/test_arxiv.py`:

```python
from pathlib import Path

from radar.arxiv import ARXIV_ENDPOINT, ArxivClient, build_query, parse_feed
from radar.config import ScopeConfig

FIXTURE = (Path(__file__).parent / "fixtures" / "arxiv_response.xml").read_text()


def test_endpoint_is_https():
    """Em HTTP a API devolve 301 com corpo vazio; raise_for_status() nao
    levanta em 3xx e httpx nao segue redirect por padrao -- falha silenciosa."""
    assert ARXIV_ENDPOINT.startswith("https://")


def test_query_combines_categories_with_or_and_ands_the_term():
    q = build_query("quantization", ScopeConfig(categories=("cs.LG", "cs.AR"), terms=()))
    assert "cat:cs.LG OR cat:cs.AR" in q
    assert 'abs:"quantization"' in q
    assert " AND " in q


def test_parse_strips_version_from_the_arxiv_id():
    papers = parse_feed(FIXTURE)
    assert papers[0].arxiv_id == "2608.11111"


def test_parse_collapses_whitespace_in_title_and_abstract():
    p = parse_feed(FIXTURE)[0]
    assert p.title == "Fused INT4 Kernels for Ampere Inference"
    assert "  " not in p.abstract
    assert p.abstract.startswith("We present")


def test_parse_extracts_authors_in_order():
    assert parse_feed(FIXTURE)[0].authors == ("Elias Frantar", "Ji Lin")


def test_parse_extracts_all_categories():
    assert parse_feed(FIXTURE)[0].categories == ("cs.LG", "cs.AR")


def test_parse_keeps_published_as_iso_date():
    assert parse_feed(FIXTURE)[0].published == "2026-08-20"


def test_parse_returns_every_entry_without_filtering():
    """O parser nao filtra. Filtro de escopo e responsabilidade do cliente."""
    assert len(parse_feed(FIXTURE)) == 2


def test_empty_feed_returns_empty_list():
    empty = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert parse_feed(empty) == []


def test_client_excludes_papers_with_no_category_in_scope():
    seen = []

    def fake_fetch(url):
        seen.append(url)
        return FIXTURE

    scope = ScopeConfig(categories=("cs.LG", "cs.AR"), terms=("quantization",))
    papers = ArxivClient(fetch=fake_fetch, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]   # a entrada eess.AS cai fora
    assert len(seen) == 1


CROSS_LISTED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2608.33333v1</id>
    <published>2026-08-18T00:00:00Z</published>
    <title>Cross-listed Efficiency Work</title>
    <summary>Categoria primaria fora do escopo, secundaria dentro.</summary>
    <author><name>A B</name></author>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
  </entry>
</feed>"""


def test_client_admits_a_paper_whose_only_in_scope_category_is_secondary():
    """Cross-listing e comum: trabalho de eficiencia costuma ter primaria
    cs.AI e secundaria cs.LG. A descoberta favorece recall de proposito --
    cinco filtros a jusante (termo, sinal do GitHub, portao, piso, teto de 3)
    cuidam da precisao. Este teste distingue interseccao de primary-only;
    o teste acima nao distinguia, porque a entrada descartada da fixture nao
    tem NENHUMA categoria no escopo."""
    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization",))
    papers = ArxivClient(fetch=lambda url: CROSS_LISTED, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.33333"]


def test_client_unions_terms_and_deduplicates_by_id():
    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=lambda url: FIXTURE, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]


def test_client_sleeps_between_calls_for_arxiv_etiquette():
    naps = []
    scope = ScopeConfig(categories=("cs.LG",), terms=("a", "b", "c"))
    ArxivClient(fetch=lambda url: FIXTURE, sleep=naps.append).recent(scope)
    assert len(naps) == 2          # dorme entre chamadas, nao depois da ultima
    assert all(n >= 3 for n in naps)


def test_client_survives_a_term_whose_response_is_empty():
    """Corpo vazio e exatamente o que a API devolve em HTTP simples, e
    ET.fromstring("") levanta ParseError. Sem o parse dentro do try, um unico
    termo ruim derruba a coleta de todos os outros."""
    def fetch(url):
        return "" if "sparsity" in url else FIXTURE

    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=fetch, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]


def test_client_survives_a_term_whose_response_is_malformed():
    def fetch(url):
        return "<feed><entry>truncad" if "sparsity" in url else FIXTURE

    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=fetch, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]


def test_client_survives_one_failing_term():
    def flaky(url):
        if "sparsity" in url:
            raise RuntimeError("502")
        return FIXTURE

    scope = ScopeConfig(categories=("cs.LG",), terms=("quantization", "sparsity"))
    papers = ArxivClient(fetch=flaky, sleep=lambda s: None).recent(scope)
    assert [p.arxiv_id for p in papers] == ["2608.11111"]
```

- [ ] **Passo 3: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_arxiv.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.arxiv'`

- [ ] **Passo 4: Implementar**

`src/radar/arxiv.py`:

```python
"""Adaptador do arXiv.

PEGADINHA VERIFICADA: a API so responde em HTTPS e com User-Agent explicito.
Em HTTP ela devolve 301 com corpo vazio. A falha e silenciosa porque
raise_for_status() nao levanta em 3xx e o httpx nao segue redirect por padrao:
o chamador recebe zero byte e nenhum erro. Endpoint travado por teste.

Uma query por termo, unidas em codigo, em vez de uma query booleana gigante:
a API trata mal query longa com aspas aninhadas, e a uniao em codigo e trivial
de depurar.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Callable
from urllib.parse import urlencode

from .config import ScopeConfig
from .models import Paper

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
USER_AGENT = "ai-radar/0.1 (personal research digest)"
ETIQUETTE_SLEEP_SECONDS = 3

_ATOM = {"a": "http://www.w3.org/2005/Atom"}


def build_query(term: str, scope: ScopeConfig) -> str:
    cats = " OR ".join(f"cat:{c}" for c in scope.categories)
    return f'({cats}) AND abs:"{term}"'


def build_url(term: str, scope: ScopeConfig, max_results: int = 100) -> str:
    params = {
        "search_query": build_query(term, scope),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    return f"{ARXIV_ENDPOINT}?{urlencode(params)}"


def _text(node, path: str) -> str:
    found = node.find(path, _ATOM)
    return " ".join(found.text.split()) if found is not None and found.text else ""


def parse_feed(xml_text: str) -> list[Paper]:
    """Parseia sem filtrar. Filtro de escopo e do cliente, nao do parser."""
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall("a:entry", _ATOM):
        raw_id = _text(entry, "a:id").rsplit("/", 1)[-1]
        canonical = raw_id.split("v")[0] if "v" in raw_id else raw_id
        papers.append(Paper(
            arxiv_id=canonical,
            title=_text(entry, "a:title"),
            abstract=_text(entry, "a:summary"),
            authors=[" ".join(n.text.split())
                     for n in entry.findall("a:author/a:name", _ATOM) if n.text],
            categories=[c.get("term") for c in entry.findall("a:category", _ATOM)],
            published=_text(entry, "a:published")[:10],
        ))
    return papers


class ArxivClient:
    def __init__(
        self,
        fetch: Callable[[str], str],
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._fetch = fetch
        self._sleep = sleep

    def recent(self, scope: ScopeConfig, max_results: int = 100) -> list[Paper]:
        allowed = set(scope.categories)
        seen: dict[str, Paper] = {}
        for index, term in enumerate(scope.terms):
            if index:
                self._sleep(ETIQUETTE_SLEEP_SECONDS)
            # build_url fica FORA do try: se a construcao da query tiver bug
            # nosso, queremos que exploda, nao que seja engolida como falha
            # do arXiv.
            url = build_url(term, scope, max_results)
            try:
                parsed = parse_feed(self._fetch(url))
            except Exception:
                # Um termo que falha nao derruba a coleta inteira. O parse
                # precisa estar DENTRO do try: corpo vazio -- que e o que a API
                # devolve em HTTP simples -- faz ET.fromstring levantar
                # ParseError, e sem essa cobertura um unico termo ruim mata a
                # coleta de todos os outros.
                continue
            for paper in parsed:
                if paper.arxiv_id in seen:
                    continue
                if allowed.intersection(paper.categories):
                    seen[paper.arxiv_id] = paper
        return list(seen.values())
```

O `fetch` injetado em produção usa `httpx` com o User-Agent obrigatório:

```python
import httpx

def http_fetch(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    response.raise_for_status()
    return response.text
```

- [ ] **Passo 5: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_arxiv.py -v`
Esperado: 16 passed

- [ ] **Passo 6: Propor commit (aguardar aprovação)**

```bash
git add src/radar/arxiv.py tests/test_arxiv.py tests/fixtures/arxiv_response.xml
git commit -m "feat: adaptador arXiv com HTTPS travado e uniao por termo"
```

---

## Tarefa 5: Adaptador GitHub

**Arquivos:**
- Criar: `src/radar/github.py`, `tests/fixtures/github_search.json`
- Teste: `tests/test_github.py`

**Interfaces:**
- Consome: `Repo`, `Signal` da Tarefa 1; `classify_repos` da Tarefa 3.
- Produz: `parse_search(payload) -> list[Repo]`, `GitHubClient(fetch).signal_for(paper, today) -> Signal`.

- [ ] **Passo 1: Criar a fixture**

`tests/fixtures/github_search.json` — resposta reduzida, com os campos que o parser usa. Os números vêm do spike real com o arXiv ID do GPTQ:

```json
{
  "total_count": 4,
  "incomplete_results": false,
  "items": [
    {"full_name": "IST-DASLab/gptq",      "owner": {"login": "IST-DASLab"},
     "stargazers_count": 2360, "created_at": "2022-10-19T00:00:00Z"},
    {"full_name": "fpgaminer/GPTQ-triton", "owner": {"login": "fpgaminer"},
     "stargazers_count": 322,  "created_at": "2023-03-28T00:00:00Z"},
    {"full_name": "davisyoshida/jax-gptq", "owner": {"login": "davisyoshida"},
     "stargazers_count": 10,   "created_at": "2023-05-05T00:00:00Z"},
    {"full_name": "recente/fresh-impl",    "owner": {"login": "recente"},
     "stargazers_count": 4,    "created_at": "2026-08-20T00:00:00Z"}
  ]
}
```

- [ ] **Passo 2: Escrever o teste que falha**

`tests/test_github.py`:

```python
import json
from datetime import date
from pathlib import Path

import pytest

from radar.github import GitHubClient, build_search_url, parse_search
from radar.models import Paper

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "github_search.json").read_text())

PAPER = Paper(arxiv_id="2210.17323", title="GPTQ", abstract="",
              authors=["Elias Frantar"], categories=["cs.LG"], published="2022-10-31")
TODAY = date(2026, 8, 27)


def test_search_url_quotes_the_arxiv_id_and_scopes_to_readme():
    url = build_search_url("2210.17323")
    assert "%222210.17323%22" in url
    assert "in%3Areadme" in url or "in:readme" in url


def test_parse_extracts_the_fields_the_signal_needs():
    repos = parse_search(PAYLOAD)
    assert len(repos) == 4
    assert repos[0].full_name == "IST-DASLab/gptq"
    assert repos[0].owner == "IST-DASLab"
    assert repos[0].stars == 2360


def test_parse_of_empty_result_returns_empty():
    assert parse_search({"total_count": 0, "incomplete_results": False, "items": []}) == []


def test_error_payload_raises_instead_of_parsing_to_zero():
    """Rate limit parseado como zero repos vira "ninguem implementou este
    paper" -- despenca o score e descarta um paper bom, sem erro nenhum."""
    from radar.github import SearchUnusable
    with pytest.raises(SearchUnusable, match="items"):
        parse_search({"message": "API rate limit exceeded", "documentation_url": "x"})


def test_incomplete_search_raises_rather_than_undercounting():
    """O GitHub avisa quando a busca deu timeout. Contar em cima do parcial e
    truncamento silencioso."""
    from radar.github import SearchUnusable
    with pytest.raises(SearchUnusable, match="incompleta"):
        parse_search({"total_count": 104, "incomplete_results": True,
                      "items": [{"full_name": "a/b", "owner": {"login": "a"},
                                 "stargazers_count": 5,
                                 "created_at": "2024-01-01T00:00:00Z"}]})


def test_complete_search_flag_false_is_accepted():
    payload = {"total_count": 1, "incomplete_results": False,
               "items": [{"full_name": "a/b", "owner": {"login": "a"},
                          "stargazers_count": 5, "created_at": "2024-01-01T00:00:00Z"}]}
    assert len(parse_search(payload)) == 1


def test_signal_counts_total_and_independent_separately():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.total_impls == 4
    # IST-DASLab/gptq e pego como oficial (mais antigo E mais estrelado)
    assert s.independent_impls == 3


def test_signal_sums_stars_across_all_repos():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.stars_total == 2360 + 322 + 10 + 4


def test_velocity_counts_only_repos_created_in_the_last_14_days():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.velocity_14d == 1        # so recente/fresh-impl, de 2026-08-20


def test_velocity_window_boundary_is_inclusive():
    payload = {"total_count": 1, "incomplete_results": False, "items": [
        {"full_name": "a/b", "owner": {"login": "a"},
         "stargazers_count": 1, "created_at": "2026-08-13T00:00:00Z"}]}
    s = GitHubClient(fetch=lambda url: payload).signal_for(PAPER, today=TODAY)
    assert s.velocity_14d == 1


def test_repo_older_than_the_window_is_not_counted_as_velocity():
    payload = {"total_count": 1, "incomplete_results": False, "items": [
        {"full_name": "a/b", "owner": {"login": "a"},
         "stargazers_count": 1, "created_at": "2026-08-12T00:00:00Z"}]}
    s = GitHubClient(fetch=lambda url: payload).signal_for(PAPER, today=TODAY)
    assert s.velocity_14d == 0


def test_no_results_yields_a_zeroed_signal():
    s = GitHubClient(fetch=lambda url: {"total_count": 0, "incomplete_results": False, "items": []}).signal_for(
        PAPER, today=TODAY)
    assert s == type(s)(total_impls=0, independent_impls=0, velocity_14d=0,
                        stars_total=0, citations=0)


def test_classifications_are_exposed_for_the_audit_trail():
    client = GitHubClient(fetch=lambda url: PAYLOAD)
    _, classifications = client.signal_with_repos(PAPER, today=TODAY)
    flagged = [c for c in classifications if c.is_author]
    assert len(flagged) == 1
    assert flagged[0].reason == "mais_antigo_e_mais_estrelado"


def test_citations_default_to_zero_when_not_supplied():
    s = GitHubClient(fetch=lambda url: PAYLOAD).signal_for(PAPER, today=TODAY)
    assert s.citations == 0
```

- [ ] **Passo 3: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_github.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.github'`

- [ ] **Passo 4: Implementar**

`src/radar/github.py`:

```python
"""Adaptador do GitHub.

Verificado no spike: `q="<arxiv_id>" in:readme` na busca de repositorios devolve
104 resultados para o ID do GPTQ, com a distincao autor/independente visivel.

LIMITACAO ESTRUTURAL: `in:readme` so alcanca o README da branch padrao.
Implementacao que cita o paper apenas no codigo, num notebook ou no artigo e
invisivel. O sinal e um piso, nao uma contagem.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable
from urllib.parse import urlencode

from .authorship import classify_repos
from .models import Paper, Repo, RepoClassification, Signal

SEARCH_ENDPOINT = "https://api.github.com/search/repositories"
VELOCITY_WINDOW_DAYS = 14


def build_search_url(arxiv_id: str, per_page: int = 100) -> str:
    return f"{SEARCH_ENDPOINT}?{urlencode({'q': f'\"{arxiv_id}\" in:readme', 'per_page': per_page})}"


class SearchUnusable(RuntimeError):
    """A resposta nao sustenta um sinal. Melhor nenhum dado que dado errado."""


def parse_search(payload: dict) -> list[Repo]:
    """Converte a resposta de busca em repositorios, recusando o que nao presta.

    Duas recusas, ambas porque um sinal errado e pior que sinal nenhum num
    pipeline de pontuacao:

    - Payload SEM a chave `items` e resposta de erro (rate limit, por exemplo).
      Sem esta guarda ele parseia para zero repositorios em silencio, e zero
      significa "ninguem implementou este paper" -- despenca o score e descarta
      um paper que podia ser bom. Busca legitimamente vazia traz `items: []`,
      entao a chave discrimina os dois casos sem ambiguidade.

    - `incomplete_results: True` e o GitHub avisando que a busca deu timeout e
      o resultado veio parcial. Contar em cima disso e truncamento silencioso,
      proibido pelas restricoes do projeto. O paper e pulado hoje e volta na
      re-consulta de amanha.
    """
    if "items" not in payload:
        raise SearchUnusable(
            f"resposta sem a chave 'items' (provavel erro da API): "
            f"{sorted(payload)[:4]}"
        )
    if payload.get("incomplete_results"):
        raise SearchUnusable(
            f"busca incompleta segundo o proprio GitHub "
            f"(total_count={payload.get('total_count')}, "
            f"itens recebidos={len(payload['items'])})"
        )
    return [
        Repo(
            full_name=item["full_name"],
            owner=item["owner"]["login"],
            stars=item["stargazers_count"],
            created_at=item["created_at"],
        )
        for item in payload["items"]
    ]


class GitHubClient:
    def __init__(self, fetch: Callable[[str], dict]) -> None:
        self._fetch = fetch

    def signal_with_repos(
        self, paper: Paper, today: date, citations: int = 0
    ) -> tuple[Signal, list[RepoClassification]]:
        repos = parse_search(self._fetch(build_search_url(paper.arxiv_id)))
        classifications = classify_repos(repos, paper.authors, paper.abstract)

        cutoff = today - timedelta(days=VELOCITY_WINDOW_DAYS)
        velocity = sum(
            1 for r in repos
            if datetime.fromisoformat(r.created_at.replace("Z", "+00:00")).date() >= cutoff
        )

        signal = Signal(
            total_impls=len(repos),
            independent_impls=sum(1 for c in classifications if not c.is_author),
            velocity_14d=velocity,
            stars_total=sum(r.stars for r in repos),
            citations=citations,
        )
        return signal, classifications

    def signal_for(self, paper: Paper, today: date, citations: int = 0) -> Signal:
        return self.signal_with_repos(paper, today, citations)[0]
```

O `fetch` de produção usa `httpx` e envia o token quando existir:

```python
import os
import httpx

def http_fetch_json(url: str) -> dict:
    headers = {"User-Agent": "ai-radar/0.1", "Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.get(url, headers=headers, timeout=30.0)
    response.raise_for_status()
    return response.json()
```

- [ ] **Passo 5: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_github.py -v`
Esperado: 14 passed

- [ ] **Passo 6: Propor commit (aguardar aprovação)**

```bash
git add src/radar/github.py tests/test_github.py tests/fixtures/github_search.json
git commit -m "feat: adaptador GitHub com sinal de implementacao e trilha de auditoria"
```

---

## Tarefa 6: Estado em SQLite

**Arquivos:**
- Criar: `src/radar/store.py`
- Teste: `tests/test_store.py`

**Interfaces:**
- Consome: `Paper`, `Signal`, `RepoClassification`, `Judgment` das tarefas anteriores.
- Produz: `Store(path)` com `.init_schema()`, `.upsert_paper()`, `.record_signal()`, `.record_repos()`, `.record_judgment()`, `.mark_delivered()`, `.was_delivered()`, `.signal_delta()`, `.stalest_papers()`.

- [ ] **Passo 1: Escrever o teste que falha**

`tests/test_store.py`:

```python
import pytest

from radar.models import Judgment, Paper, Repo, RepoClassification, Signal
from radar.store import Store

P = Paper(arxiv_id="2508.11111", title="T", abstract="A",
          authors=["Elias Frantar"], categories=["cs.LG"], published="2026-08-20")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    return s


def test_upsert_is_idempotent(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.upsert_paper(P, seen_at="2026-08-28")
    assert len(store.all_papers()) == 1


def test_first_seen_is_preserved_across_upserts(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.upsert_paper(P, seen_at="2026-08-28")
    assert store.all_papers()[0]["first_seen"] == "2026-08-27"


def test_signals_are_append_only(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(2, 2, 1, 40), score=0.4, checked_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(9, 9, 7, 340), score=0.3, checked_at="2026-09-17")
    assert len(store.signal_history(P.arxiv_id)) == 2


def test_delta_reports_growth_between_first_and_last_check(store):
    """Ressurreicao: paper antigo voltando a ser implementado."""
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(2, 2, 0, 300), score=0.1, checked_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(9, 9, 7, 340), score=0.4, checked_at="2026-09-17")
    delta = store.signal_delta(P.arxiv_id)
    assert delta["independent_from"] == 2
    assert delta["independent_to"] == 9
    assert delta["days"] == 21


def test_delta_is_none_with_a_single_observation(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_signal(P.arxiv_id, Signal(2, 2, 0, 40), score=0.4, checked_at="2026-08-27")
    assert store.signal_delta(P.arxiv_id) is None


def test_repos_persist_the_authorship_reason(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.record_repos(P.arxiv_id, [
        RepoClassification(Repo("a/b", "a", 10, "2024-01-01T00:00:00Z"),
                           is_author=True, reason="sobrenome"),
        RepoClassification(Repo("c/d", "c", 5, "2024-02-01T00:00:00Z"),
                           is_author=False, reason=None),
    ])
    rows = {r["full_name"]: r for r in store.repos_for(P.arxiv_id)}
    assert rows["a/b"]["is_author_reason"] == "sobrenome"
    assert rows["c/d"]["is_author_reason"] is None


def test_delivered_paper_is_not_delivered_again(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    assert store.was_delivered(P.arxiv_id, channel="telegram") is False
    store.mark_delivered(P.arxiv_id, channel="telegram", at="2026-08-27", rank=1)
    assert store.was_delivered(P.arxiv_id, channel="telegram") is True


def test_delivery_channels_are_independent(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    store.mark_delivered(P.arxiv_id, channel="markdown", at="2026-08-27", rank=None)
    assert store.was_delivered(P.arxiv_id, channel="telegram") is False


def test_judgment_round_trips(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    j = Judgment(technique="Kernel INT4", summary="S", runs_on_3090="sim", rationale="R")
    store.record_judgment(P.arxiv_id, j, model="claude-opus-5", judged_at="2026-08-27")
    assert store.latest_judgment(P.arxiv_id).technique == "Kernel INT4"


def test_stalest_papers_come_first(store):
    for pid, seen in (("2508.00001", "2026-08-01"), ("2508.00002", "2026-08-25")):
        paper = Paper(arxiv_id=pid, title="T", abstract="A", authors=[],
                      categories=["cs.LG"], published="2026-08-01")
        store.upsert_paper(paper, seen_at=seen)
        store.touch_checked(pid, at=seen)
    assert [p["arxiv_id"] for p in store.stalest_papers(limit=2)] == ["2508.00001", "2508.00002"]


def test_stalest_respects_the_limit(store):
    for i in range(5):
        paper = Paper(arxiv_id=f"2508.0000{i}", title="T", abstract="A", authors=[],
                      categories=["cs.LG"], published="2026-08-01")
        store.upsert_paper(paper, seen_at="2026-08-01")
        store.touch_checked(paper.arxiv_id, at="2026-08-01")
    assert len(store.stalest_papers(limit=3)) == 3


def test_init_schema_is_idempotent(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    s.init_schema()
    assert s.all_papers() == []
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_store.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.store'`

- [ ] **Passo 3: Implementar**

`src/radar/store.py`:

```python
"""Estado em SQLite, versionado no repositorio.

`signals` e append-only de proposito: e da diferenca entre duas observacoes que
sai a deteccao de ressurreicao. Um paper antigo voltando a ser implementado nao
e uma descoberta nova -- e um delta numa entrada que ja existe.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from .models import Judgment, RepoClassification, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    abstract     TEXT NOT NULL,
    authors      TEXT NOT NULL,
    categories   TEXT NOT NULL,
    published    TEXT NOT NULL,
    first_seen   TEXT NOT NULL,
    last_checked TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    arxiv_id          TEXT NOT NULL REFERENCES papers(arxiv_id),
    checked_at        TEXT NOT NULL,
    total_impls       INTEGER NOT NULL,
    independent_impls INTEGER NOT NULL,
    velocity_14d      INTEGER NOT NULL,
    stars_total       INTEGER NOT NULL,
    citations         INTEGER NOT NULL DEFAULT 0,
    score             REAL,
    PRIMARY KEY (arxiv_id, checked_at)
);
CREATE TABLE IF NOT EXISTS repos (
    arxiv_id         TEXT NOT NULL REFERENCES papers(arxiv_id),
    full_name        TEXT NOT NULL,
    owner            TEXT NOT NULL,
    stars            INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    is_author        INTEGER NOT NULL,
    is_author_reason TEXT,
    PRIMARY KEY (arxiv_id, full_name)
);
CREATE TABLE IF NOT EXISTS judgments (
    arxiv_id     TEXT NOT NULL REFERENCES papers(arxiv_id),
    judged_at    TEXT NOT NULL,
    model        TEXT NOT NULL,
    technique    TEXT NOT NULL,
    summary      TEXT NOT NULL,
    runs_on_3090 TEXT NOT NULL,
    rationale    TEXT NOT NULL,
    PRIMARY KEY (arxiv_id, judged_at)
);
CREATE TABLE IF NOT EXISTS deliveries (
    arxiv_id     TEXT NOT NULL REFERENCES papers(arxiv_id),
    delivered_at TEXT NOT NULL,
    channel      TEXT NOT NULL,
    rank         INTEGER,
    PRIMARY KEY (arxiv_id, delivered_at, channel)
);
"""


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---------- papers ----------

    def upsert_paper(self, paper, seen_at: str) -> None:
        # first_seen so e gravado na insercao; ON CONFLICT nao o toca.
        self._conn.execute(
            """INSERT INTO papers
                 (arxiv_id, title, abstract, authors, categories, published, first_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(arxiv_id) DO UPDATE SET
                 title=excluded.title, abstract=excluded.abstract""",
            (paper.arxiv_id, paper.title, paper.abstract, json.dumps(paper.authors),
             json.dumps(paper.categories), paper.published, seen_at),
        )
        self._conn.commit()

    def all_papers(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM papers")]

    def touch_checked(self, arxiv_id: str, at: str) -> None:
        self._conn.execute("UPDATE papers SET last_checked=? WHERE arxiv_id=?", (at, arxiv_id))
        self._conn.commit()

    def stalest_papers(self, limit: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM papers ORDER BY last_checked IS NOT NULL, last_checked ASC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    # ---------- signals ----------

    def record_signal(self, arxiv_id: str, signal: Signal, score, checked_at: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO signals
                 (arxiv_id, checked_at, total_impls, independent_impls,
                  velocity_14d, stars_total, citations, score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (arxiv_id, checked_at, signal.total_impls, signal.independent_impls,
             signal.velocity_14d, signal.stars_total, signal.citations, score),
        )
        self._conn.commit()

    def signal_history(self, arxiv_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM signals WHERE arxiv_id=? ORDER BY checked_at ASC", (arxiv_id,))
        return [dict(r) for r in rows]

    def signal_delta(self, arxiv_id: str) -> dict | None:
        history = self.signal_history(arxiv_id)
        if len(history) < 2:
            return None
        first, last = history[0], history[-1]
        return {
            "independent_from": first["independent_impls"],
            "independent_to": last["independent_impls"],
            "stars_from": first["stars_total"],
            "stars_to": last["stars_total"],
            "days": (date.fromisoformat(last["checked_at"])
                     - date.fromisoformat(first["checked_at"])).days,
        }

    # ---------- repos ----------

    def record_repos(self, arxiv_id: str, classifications: list[RepoClassification]) -> None:
        self._conn.executemany(
            """INSERT OR REPLACE INTO repos
                 (arxiv_id, full_name, owner, stars, created_at, is_author, is_author_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(arxiv_id, c.repo.full_name, c.repo.owner, c.repo.stars,
              c.repo.created_at, int(c.is_author), c.reason) for c in classifications],
        )
        self._conn.commit()

    def repos_for(self, arxiv_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM repos WHERE arxiv_id=? ORDER BY stars DESC", (arxiv_id,))
        return [dict(r) for r in rows]

    # ---------- judgments ----------

    def record_judgment(self, arxiv_id: str, j: Judgment, model: str, judged_at: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO judgments
                 (arxiv_id, judged_at, model, technique, summary, runs_on_3090, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (arxiv_id, judged_at, model, j.technique, j.summary, j.runs_on_3090, j.rationale),
        )
        self._conn.commit()

    def latest_judgment(self, arxiv_id: str) -> Judgment | None:
        row = self._conn.execute(
            "SELECT * FROM judgments WHERE arxiv_id=? ORDER BY judged_at DESC LIMIT 1",
            (arxiv_id,)).fetchone()
        if row is None:
            return None
        return Judgment(technique=row["technique"], summary=row["summary"],
                        runs_on_3090=row["runs_on_3090"], rationale=row["rationale"])

    # ---------- deliveries ----------

    def mark_delivered(self, arxiv_id: str, channel: str, at: str, rank: int | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO deliveries VALUES (?, ?, ?, ?)",
            (arxiv_id, at, channel, rank))
        self._conn.commit()

    def was_delivered(self, arxiv_id: str, channel: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM deliveries WHERE arxiv_id=? AND channel=? LIMIT 1",
            (arxiv_id, channel)).fetchone()
        return row is not None
```

- [ ] **Passo 4: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_store.py -v`
Esperado: 12 passed

- [ ] **Passo 5: Propor commit (aguardar aprovação)**

```bash
git add src/radar/store.py tests/test_store.py
git commit -m "feat: estado SQLite append-only com delta e trilha de entrega"
```

---

## Tarefa 7: Julgamento por LLM

**Arquivos:**
- Criar: `src/radar/judge.py`
- Teste: `tests/test_judge.py`

**Interfaces:**
- Consome: `Paper`, `Judgment` da Tarefa 1; `load_model` da Tarefa 1.
- Produz: `JudgmentSchema` (pydantic), `build_prompt(paper) -> str`, `Judge(client, model).judge_one(paper) -> Judgment`, `build_batch_requests(papers, model) -> list[dict]`, `collect_batch_results(results) -> dict[str, Judgment]` e `submit_batch(client, papers, model)`. O caminho de lote é composto por essas três funções, não por um método em `Judge`.

**Assinaturas do SDK, confirmadas na referência:**
- Chamada única: `client.messages.parse(model=..., max_tokens=..., messages=[...], output_format=<PydanticModel>)` → `response.parsed_output`
- Batch: `client.messages.batches.create(requests=[Request(custom_id=..., params=MessageCreateParamsNonStreaming(...))])`, resultados por `client.messages.batches.results(id)` indexados por `result.custom_id`
- Imports: `from anthropic.types.message_create_params import MessageCreateParamsNonStreaming` e `from anthropic.types.messages.batch_create_params import Request`

- [ ] **Passo 1: Escrever o teste que falha**

`tests/test_judge.py`:

```python
import pytest

from radar.judge import HARDWARE_BRIEF, Judge, JudgmentSchema, build_prompt
from radar.models import Judgment, Paper

PAPER = Paper(arxiv_id="2508.11111", title="Fused INT4 Kernels",
              abstract="We present a fused INT4 by FP16 kernel.",
              authors=["A B"], categories=["cs.LG"], published="2026-08-20")


class FakeParsed:
    def __init__(self, parsed):
        self.parsed_output = parsed


class FakeMessages:
    def __init__(self, parsed):
        self._parsed = parsed
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return FakeParsed(self._parsed)


class FakeClient:
    def __init__(self, parsed):
        self.messages = FakeMessages(parsed)


def valid_schema():
    return JudgmentSchema(technique="Kernel INT4 fundido",
                          summary="Satura banda em batch unitario.",
                          runs_on_3090="sim", rationale="INT4 roda em Ampere.")


def test_hardware_brief_names_the_real_constraints():
    """O veredito so vale se o modelo souber o que a maquina nao tem."""
    for fact in ("Ampere", "24", "FP8", "936"):
        assert fact in HARDWARE_BRIEF


def test_prompt_includes_the_paper_and_the_hardware_brief():
    prompt = build_prompt(PAPER)
    assert PAPER.title in prompt
    assert PAPER.abstract in prompt
    assert HARDWARE_BRIEF in prompt


def test_schema_rejects_a_verdict_outside_the_enum():
    with pytest.raises(Exception):
        JudgmentSchema(technique="T", summary="S", runs_on_3090="talvez", rationale="R")


def test_judge_one_returns_a_domain_judgment():
    judge = Judge(client=FakeClient(valid_schema()), model="claude-opus-5")
    result = judge.judge_one(PAPER)
    assert isinstance(result, Judgment)
    assert result.runs_on_3090 == "sim"
    assert result.technique == "Kernel INT4 fundido"


def test_judge_one_passes_the_configured_model():
    client = FakeClient(valid_schema())
    Judge(client=client, model="claude-opus-5").judge_one(PAPER)
    assert client.messages.calls[0]["model"] == "claude-opus-5"


def test_judge_one_uses_structured_output_not_free_text():
    client = FakeClient(valid_schema())
    Judge(client=client, model="claude-opus-5").judge_one(PAPER)
    assert client.messages.calls[0]["output_format"] is JudgmentSchema


def test_batch_requests_are_keyed_by_arxiv_id():
    from radar.judge import build_batch_requests
    papers = [PAPER, Paper(arxiv_id="2508.22222", title="T2", abstract="A2",
                           authors=[], categories=["cs.LG"], published="2026-08-21")]
    requests = build_batch_requests(papers, model="claude-opus-5")
    assert [r["custom_id"] for r in requests] == ["2508.11111", "2508.22222"]


def test_batch_results_are_keyed_not_positional():
    """Resultados do Batch API chegam fora de ordem. Indexar por posicao e bug."""
    from radar.judge import collect_batch_results

    class R:
        def __init__(self, cid, tech):
            self.custom_id = cid
            self.result = type("Res", (), {
                "type": "succeeded",
                "message": type("M", (), {"content": [
                    type("B", (), {"type": "text", "text":
                        '{"technique":"%s","summary":"S","runs_on_3090":"sim",'
                        '"rationale":"R"}' % tech})()]})()})()

    out = collect_batch_results([R("2508.22222", "B"), R("2508.11111", "A")])
    assert out["2508.11111"].technique == "A"
    assert out["2508.22222"].technique == "B"


def test_batch_skips_failed_results_without_crashing():
    from radar.judge import collect_batch_results

    class Errored:
        custom_id = "2508.33333"
        result = type("Res", (), {"type": "errored"})()

    assert collect_batch_results([Errored()]) == {}
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_judge.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.judge'`

- [ ] **Passo 3: Implementar**

`src/radar/judge.py`:

```python
"""Camada de julgamento.

O radar (3 itens) usa chamada normal -- volume trivial, resultado imediato.
O feed usa o Batch API: metade do custo, e latencia e irrelevante num cron.

Resultados do batch chegam FORA DE ORDEM. Indexar por custom_id, nunca por
posicao.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .models import Judgment, Paper

HARDWARE_BRIEF = (
    "A maquina alvo tem uma NVIDIA RTX 3090: arquitetura Ampere GA102, 24 GB de "
    "VRAM, 936 GB/s de banda de memoria, PCIe 4.0, e SEM unidades FP8. Tecnicas "
    "que dependem de FP8, de multiplas GPUs, ou de mais de 24 GB nao rodam nela."
)

MAX_TOKENS = 1024


class JudgmentSchema(BaseModel):
    technique: str = Field(description="Rotulo curto da tecnica, ate 8 palavras")
    summary: str = Field(description="UMA frase dizendo o que a tecnica faz")
    runs_on_3090: Literal["sim", "sim_com_ressalva", "nao"]
    rationale: str = Field(description="Uma linha justificando o veredito de hardware")


def build_prompt(paper: Paper) -> str:
    return (
        f"{HARDWARE_BRIEF}\n\n"
        f"Paper (arXiv {paper.arxiv_id}):\n"
        f"Titulo: {paper.title}\n"
        f"Resumo: {paper.abstract}\n\n"
        f"Resuma a tecnica em uma frase e diga se ela roda nessa maquina. "
        f"Escreva em portugues, sem emoji, sem adjetivo promocional."
    )


def _to_domain(schema: JudgmentSchema) -> Judgment:
    return Judgment(technique=schema.technique, summary=schema.summary,
                    runs_on_3090=schema.runs_on_3090, rationale=schema.rationale)


class Judge:
    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    def judge_one(self, paper: Paper) -> Judgment:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": build_prompt(paper)}],
            output_format=JudgmentSchema,
        )
        return _to_domain(response.parsed_output)


def build_batch_requests(papers: list[Paper], model: str) -> list[dict]:
    """Devolve dicts para permanecer testavel sem o SDK instalado.

    O chamador converte em Request/MessageCreateParamsNonStreaming --
    ver submit_batch abaixo.
    """
    return [
        {
            "custom_id": paper.arxiv_id,
            "params": {
                "model": model,
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": build_prompt(paper)}],
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": JudgmentSchema.model_json_schema(),
                    }
                },
            },
        }
        for paper in papers
    ]


def collect_batch_results(results) -> dict[str, Judgment]:
    """Indexa por custom_id. Resultados do batch chegam fora de ordem."""
    out: dict[str, Judgment] = {}
    for result in results:
        if result.result.type != "succeeded":
            continue
        message = result.result.message
        text = next((b.text for b in message.content if b.type == "text"), None)
        if not text:
            continue
        try:
            out[result.custom_id] = _to_domain(JudgmentSchema(**json.loads(text)))
        except Exception:
            continue          # julgamento malformado nao derruba o lote
    return out


def submit_batch(client, papers: list[Paper], model: str):
    """Fio fino ate o SDK. Isolado aqui para o resto do modulo ficar testavel."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    return client.messages.batches.create(
        requests=[
            Request(custom_id=r["custom_id"],
                    params=MessageCreateParamsNonStreaming(**r["params"]))
            for r in build_batch_requests(papers, model)
        ]
    )
```

- [ ] **Passo 4: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_judge.py -v`
Esperado: 9 passed

- [ ] **Passo 5: Propor commit (aguardar aprovação)**

```bash
git add src/radar/judge.py tests/test_judge.py
git commit -m "feat: julgamento com saida estruturada e batch indexado por custom_id"
```

---

## Tarefa 8: Renderização

**Arquivos:**
- Criar: `src/radar/render.py`
- Teste: `tests/test_render.py`

**Interfaces:**
- Consome: `Paper`, `Signal`, `ScoreResult`, `Judgment`, e — para a trilha de auditoria — **linhas do store**, não `RepoClassification`. `render_markdown` recebe `repos` como `dict[str, list[dict]]` cujas chaves são as COLUNAS da tabela `repos` (`full_name`, `stars`, `is_author`, `is_author_reason`), que é o que `store.repos_for()` devolve. Atenção ao nome: a coluna é `is_author_reason`, enquanto o campo de `RepoClassification` se chama `reason` — passar o objeto tipado direto quebraria. O contrato entre store e render é travado por teste na Tarefa 10.
- Produz: `RadarItem` (dataclass agregadora), `render_telegram(items) -> str`, `render_markdown(day, items, feed, cuts) -> str`. Ambas puras.

- [ ] **Passo 1: Escrever o teste que falha**

`tests/test_render.py`:

```python
import pytest

from radar.models import Judgment, Paper, Signal
from radar.render import RadarItem, render_markdown, render_telegram

P = Paper(arxiv_id="2508.11111", title="Fused INT4 Kernels", abstract="A",
          authors=["A B"], categories=["cs.LG"], published="2026-08-20")
J = Judgment(technique="Kernel INT4 fundido",
             summary="Satura banda de memoria em batch unitario.",
             runs_on_3090="sim", rationale="INT4 roda nativo em Ampere.")


def item(score=0.53, delta=None, judgment=J, paper=P):
    return RadarItem(paper=paper, judgment=judgment,
                     signal=Signal(4, 4, 3, 60), score=score, delta=delta)


def test_telegram_output_has_no_emoji():
    text = render_telegram([item()])
    assert all(ord(c) < 0x2190 for c in text), "push do Telegram nao leva emoji"


def test_telegram_shows_technique_summary_numbers_and_verdict():
    text = render_telegram([item()])
    assert "Kernel INT4 fundido" in text
    assert "Satura banda" in text
    assert "4 impls independentes" in text
    assert "Roda na 3090: sim" in text
    assert "arxiv.org/abs/2508.11111" in text


def test_telegram_uses_delta_wording_for_a_revival():
    text = render_telegram([item(delta={"independent_from": 2, "independent_to": 9,
                                        "stars_from": 300, "stars_to": 340, "days": 21})])
    assert "2 -> 9 impls independentes em 21 dias" in text
    assert "4 impls independentes" not in text


def test_telegram_of_an_empty_list_is_empty():
    """Silencio e resultado valido. Nada de mandar item fraco por ter o que mandar."""
    assert render_telegram([]) == ""


def test_telegram_never_renders_more_than_three():
    with pytest.raises(ValueError, match="teto"):
        render_telegram([item() for _ in range(4)])


def test_markdown_lists_radar_items_first():
    md = render_markdown("2026-08-27", radar=[item()], feed=[], cuts={})
    assert md.index("## Radar") < md.index("## Feed")


def test_markdown_exposes_the_authorship_reason():
    md = render_markdown("2026-08-27", radar=[item()], feed=[],
                         cuts={}, repos={"2508.11111": [
                             {"full_name": "a/b", "is_author": 1,
                              "is_author_reason": "sobrenome", "stars": 10}]})
    assert "a/b" in md
    assert "sobrenome" in md


def test_markdown_reports_cuts_with_counts_and_reasons():
    md = render_markdown("2026-08-27", radar=[], feed=[],
                         cuts={"ja_estourou": 4, "abaixo_do_piso": 11, "ja_entregue": 2})
    assert "ja_estourou" in md and "4" in md
    assert "abaixo_do_piso" in md and "11" in md


def test_markdown_states_explicitly_when_nothing_was_cut():
    md = render_markdown("2026-08-27", radar=[item()], feed=[], cuts={})
    assert "Nenhum corte" in md


def test_markdown_never_omits_the_cuts_section():
    """Truncar em silencio faz o radar parecer que cobriu tudo."""
    md = render_markdown("2026-08-27", radar=[item()], feed=[], cuts={})
    assert "## Cortes" in md


def test_markdown_includes_the_full_feed_with_verdicts():
    feed_item = item(paper=Paper(arxiv_id="2508.99999", title="Outro", abstract="A",
                                 authors=[], categories=["cs.LG"], published="2026-08-21"))
    md = render_markdown("2026-08-27", radar=[], feed=[feed_item], cuts={})
    assert "2508.99999" in md
    assert "sim" in md
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_render.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.render'`

- [ ] **Passo 3: Implementar**

`src/radar/render.py`:

```python
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
```

- [ ] **Passo 4: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_render.py -v`
Esperado: 11 passed

- [ ] **Passo 5: Propor commit (aguardar aprovação)**

```bash
git add src/radar/render.py tests/test_render.py
git commit -m "feat: renderizacao com teto rigido e secao de cortes obrigatoria"
```

---

## Tarefa 9: Envio pelo Telegram

**Arquivos:**
- Criar: `src/radar/telegram.py`
- Teste: `tests/test_telegram.py`

**Interfaces:**
- Consome: nada das tarefas anteriores.
- Produz: `send(text, token, chat_id, post) -> bool`. `post` é injetado.

- [ ] **Passo 1: Escrever o teste que falha**

`tests/test_telegram.py`:

```python
import pytest

from radar.telegram import build_endpoint, send


def test_endpoint_embeds_the_token():
    assert build_endpoint("abc123").endswith("/botabc123/sendMessage")
    assert build_endpoint("abc123").startswith("https://")


def test_send_posts_text_and_chat_id():
    calls = []

    def fake_post(url, json):
        calls.append((url, json))
        return {"ok": True}

    assert send("mensagem", token="t", chat_id="42", post=fake_post) is True
    assert calls[0][1]["chat_id"] == "42"
    assert calls[0][1]["text"] == "mensagem"


def test_empty_text_is_not_sent():
    """Silencio e resultado valido; nao mandar mensagem vazia."""
    calls = []
    assert send("", token="t", chat_id="42", post=lambda u, json: calls.append(1)) is False
    assert calls == []


def test_whitespace_only_text_is_not_sent():
    calls = []
    assert send("   \n ", token="t", chat_id="42",
                post=lambda u, json: calls.append(1)) is False
    assert calls == []


def test_missing_credentials_raise_rather_than_fail_silently():
    with pytest.raises(ValueError, match="token"):
        send("oi", token="", chat_id="42", post=lambda u, json: None)
    with pytest.raises(ValueError, match="chat_id"):
        send("oi", token="t", chat_id="", post=lambda u, json: None)


def test_transport_failure_returns_false_without_raising():
    def failing_post(url, json):
        raise RuntimeError("timeout")

    assert send("oi", token="t", chat_id="42", post=failing_post) is False
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_telegram.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.telegram'`

- [ ] **Passo 3: Implementar**

`src/radar/telegram.py`:

```python
"""Envio do push. Transporte injetado para manter o modulo testavel offline."""
from __future__ import annotations

from typing import Callable

API_BASE = "https://api.telegram.org"


def build_endpoint(token: str) -> str:
    return f"{API_BASE}/bot{token}/sendMessage"


def send(text: str, token: str, chat_id: str, post: Callable[[str, dict], object]) -> bool:
    if not token:
        raise ValueError("token do Telegram ausente")
    if not chat_id:
        raise ValueError("chat_id do Telegram ausente")
    if not text.strip():
        return False      # silencio e resultado valido
    try:
        post(build_endpoint(token), {"chat_id": chat_id, "text": text,
                                     "disable_web_page_preview": False})
        return True
    except Exception:
        # Falha de entrega nao derruba o pipeline: o markdown ja foi gravado.
        return False
```

Transporte de produção:

```python
import httpx

def http_post(url: str, json: dict) -> dict:
    response = httpx.post(url, json=json, timeout=30.0)
    response.raise_for_status()
    return response.json()
```

- [ ] **Passo 4: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_telegram.py -v`
Esperado: 6 passed

- [ ] **Passo 5: Propor commit (aguardar aprovação)**

```bash
git add src/radar/telegram.py tests/test_telegram.py
git commit -m "feat: envio pelo Telegram com transporte injetado"
```

---

## Tarefa 10: Pipeline e CLI

**Arquivos:**
- Criar: `src/radar/pipeline.py`, `src/radar/cli.py`
- Teste: `tests/test_pipeline.py`

**Interfaces:**
- Consome: tudo das Tarefas 1 a 9.
- Produz: `run_day(...) -> DayResult` com `.radar`, `.feed`, `.cuts`, `.markdown`, `.push`. O CLI apenas monta os adaptadores reais e chama.

- [ ] **Passo 1: Escrever o teste que falha**

`tests/test_pipeline.py`:

```python
from datetime import date

import pytest

from radar.config import ScopeConfig, Thresholds
from radar.models import Judgment, Paper
from radar.pipeline import run_day
from radar.store import Store

SCOPE = ScopeConfig(categories=("cs.LG",), terms=("quantization",))
T = Thresholds(broke_out_stars=1000, broke_out_citations=200, score_floor=0.0)
TODAY = date(2026, 8, 27)


def paper(pid, authors=()):
    return Paper(arxiv_id=pid, title=f"T{pid}", abstract="A",
                 authors=list(authors), categories=["cs.LG"], published="2026-08-20")


def fake_signal(indep, stars, vel=1, cites=0):
    from radar.models import Signal
    return Signal(total_impls=indep, independent_impls=indep,
                  velocity_14d=vel, stars_total=stars, citations=cites)


def judgment(tech="T"):
    return Judgment(technique=tech, summary="S", runs_on_3090="sim", rationale="R")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "radar.db")
    s.init_schema()
    return s


def run(store, papers, signals, judgments=None, **kw):
    def judge_all(ps):
        if judgments is not None:
            return judgments
        return {p.arxiv_id: judgment(p.arxiv_id) for p in ps}

    return run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: papers,
        fetch_signal=lambda p, today: (signals[p.arxiv_id], []),
        judge_all=judge_all,
        **kw,
    )


def test_push_is_capped_at_three_even_with_many_candidates(store):
    papers = [paper(f"2508.0000{i}") for i in range(6)]
    signals = {p.arxiv_id: fake_signal(6 - i, 10 + i) for i, p in enumerate(papers)}
    result = run(store, papers, signals)
    assert len(result.radar) == 3


def test_radar_is_ordered_by_score_descending(store):
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(2, 500), "2508.00002": fake_signal(5, 10)}
    result = run(store, papers, signals)
    assert result.radar[0].paper.arxiv_id == "2508.00002"


def test_gated_papers_are_counted_as_cuts_not_delivered(store):
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(50, 9000), "2508.00002": fake_signal(3, 20)}
    result = run(store, papers, signals)
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002"]
    assert result.cuts["ja_estourou"] == 1


def test_every_in_scope_paper_reaches_the_feed_even_when_gated(store):
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(50, 9000), "2508.00002": fake_signal(3, 20)}
    result = run(store, papers, signals)
    assert {i.paper.arxiv_id for i in result.feed} == {"2508.00001", "2508.00002"}


def test_already_delivered_paper_is_not_pushed_twice(store):
    p = paper("2508.00001")
    store.upsert_paper(p, seen_at="2026-08-26")
    store.mark_delivered(p.arxiv_id, channel="telegram", at="2026-08-26", rank=1)
    result = run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert result.radar == []
    assert result.cuts["ja_entregue"] == 1


def test_pushed_papers_are_marked_delivered(store):
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert store.was_delivered("2508.00001", channel="telegram") is True


def test_score_below_the_floor_is_cut(store):
    strict = Thresholds(broke_out_stars=1000, broke_out_citations=200, score_floor=0.9)
    p = paper("2508.00001")
    result = run_day(
        store=store, scope=SCOPE, thresholds=strict, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: [p],
        fetch_signal=lambda pp, today: (fake_signal(1, 500), []),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
    )
    assert result.radar == []
    assert result.cuts["abaixo_do_piso"] == 1


def test_judgment_records_which_model_produced_it(store):
    """A coluna `model` existe para auditoria. Gravar vazio a torna inutil."""
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(4, 30)})
    row = store._conn.execute(
        "SELECT model FROM judgments WHERE arxiv_id=?", ("2508.00001",)).fetchone()
    assert row["model"] == "modelo-de-teste"


def test_signal_is_persisted_for_every_paper(store):
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert len(store.signal_history("2508.00001")) == 1


def test_second_run_produces_a_delta(store):
    p = paper("2508.00001")
    run(store, [p], {"2508.00001": fake_signal(2, 300)})
    run_day(
        store=store, scope=SCOPE, thresholds=T, today=date(2026, 9, 17), model="modelo-de-teste",
        fetch_papers=lambda scope: [p],
        fetch_signal=lambda pp, today: (fake_signal(9, 340, vel=7), []),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
    )
    delta = store.signal_delta("2508.00001")
    assert delta["independent_from"] == 2 and delta["independent_to"] == 9


def test_markdown_and_push_are_both_produced(store):
    p = paper("2508.00001")
    result = run(store, [p], {"2508.00001": fake_signal(4, 30)})
    assert "## Radar" in result.markdown
    assert "## Cortes" in result.markdown
    assert "arxiv.org/abs/2508.00001" in result.push


def test_empty_day_produces_markdown_but_empty_push(store):
    result = run(store, [], {})
    assert result.push == ""
    assert "## Cortes" in result.markdown


def test_non_executable_is_demoted_below_executable_with_lower_score(store):
    """Paper de FP8 nao roda em Ampere. Mesmo com score maior, entra depois."""
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(9, 10),    # score ALTO, mas nao roda
               "2508.00002": fake_signal(2, 40)}    # score menor, roda
    result = run(store, papers, signals, judgments={
        "2508.00001": Judgment("FP8", "S", "nao", "R"),
        "2508.00002": Judgment("INT4", "S", "sim", "R"),
    })
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002", "2508.00001"]


def test_non_executable_is_dropped_when_executables_fill_the_cap(store):
    papers = [paper(f"2508.0000{i}") for i in range(4)]
    signals = {p.arxiv_id: fake_signal(4, 20) for p in papers}
    judgments = {p.arxiv_id: Judgment("T", "S", "sim", "R") for p in papers[:3]}
    judgments["2508.00003"] = Judgment("FP8", "S", "nao", "R")
    result = run(store, papers, signals, judgments=judgments)
    assert len(result.radar) == 3
    assert "2508.00003" not in [i.paper.arxiv_id for i in result.radar]


def test_non_executable_still_enters_when_a_slot_remains(store):
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {p.arxiv_id: fake_signal(3, 20) for p in papers}
    result = run(store, papers, signals, judgments={
        "2508.00001": Judgment("T", "S", "sim", "R"),
        "2508.00002": Judgment("FP8", "S", "nao", "R"),
    })
    assert len(result.radar) == 2


def test_sim_com_ressalva_ranks_as_executable(store):
    """Ressalva nao e recusa: continua na frente do que nao roda."""
    papers = [paper("2508.00001"), paper("2508.00002")]
    signals = {"2508.00001": fake_signal(9, 10),    # score maior, nao roda
               "2508.00002": fake_signal(2, 40)}    # score menor, com ressalva
    result = run(store, papers, signals, judgments={
        "2508.00001": Judgment("FP8", "S", "nao", "R"),
        "2508.00002": Judgment("INT4", "S", "sim_com_ressalva", "R"),
    })
    assert result.radar[0].paper.arxiv_id == "2508.00002"


def test_non_executable_always_reaches_the_feed(store):
    """Rebaixar afeta o push, nunca o arquivo."""
    papers = [paper(f"2508.0000{i}") for i in range(4)]
    signals = {p.arxiv_id: fake_signal(4, 20) for p in papers}
    judgments = {p.arxiv_id: Judgment("T", "S", "sim", "R") for p in papers[:3]}
    judgments["2508.00003"] = Judgment("FP8", "S", "nao", "R")
    result = run(store, papers, signals, judgments=judgments)
    assert "2508.00003" in [i.paper.arxiv_id for i in result.feed]


def test_paper_whose_signal_fails_is_cut_not_fatal(store):
    """Uma busca do GitHub que falha num paper nao pode derrubar o digest do
    dia. O paper vira corte contado e volta na re-consulta de amanha."""
    papers = [paper("2508.00001"), paper("2508.00002")]

    def fetch_signal(p, today):
        if p.arxiv_id == "2508.00001":
            raise RuntimeError("busca incompleta segundo o proprio GitHub")
        return fake_signal(3, 20), []

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: papers,
        fetch_signal=fetch_signal,
        judge_all=lambda ps: {p.arxiv_id: judgment() for p in ps},
    )
    assert [i.paper.arxiv_id for i in result.radar] == ["2508.00002"]
    assert result.cuts["sinal_indisponivel"] == 1


def test_a_failing_signal_does_not_reach_the_feed_either(store):
    """Sem sinal nao ha o que reportar: o paper e corte, nao item de feed."""
    papers = [paper("2508.00001")]

    def fetch_signal(p, today):
        raise RuntimeError("rate limit")

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: papers,
        fetch_signal=fetch_signal,
        judge_all=lambda ps: {p.arxiv_id: judgment() for p in ps},
    )
    assert result.feed == []
    assert result.cuts["sinal_indisponivel"] == 1


def test_markdown_carries_the_authorship_audit_trail_from_the_store(store):
    """Trava o contrato implicito entre store e render.

    As colunas do banco (`is_author_reason`) precisam casar com as chaves que
    `render_markdown` le. Os testes das Tarefas 6 e 8 asseguram cada metade
    usando literais proprios, e nenhum dos dois garante que as metades
    concordam: renomear a coluna deixaria os dois verdes enquanto a trilha de
    auditoria sumia do markdown em silencio. Este teste passa dado real do
    store para o render e falha se qualquer um dos lados mudar de nome.
    """
    from radar.models import Repo, RepoClassification

    p = paper("2508.00001")
    classificacoes = [
        RepoClassification(Repo("lab/oficial", "lab", 900, "2024-01-01T00:00:00Z"),
                           is_author=True, reason="mais_antigo_e_mais_estrelado"),
        RepoClassification(Repo("terceiro/impl", "terceiro", 12, "2024-06-01T00:00:00Z"),
                           is_author=False, reason=None),
    ]
    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda scope: [p],
        fetch_signal=lambda pp, today: (fake_signal(4, 30), classificacoes),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
    )
    assert "lab/oficial — 900 estrelas — autor (mais_antigo_e_mais_estrelado)" in result.markdown
    assert "terceiro/impl — 12 estrelas — independente" in result.markdown


def test_cuts_total_plus_radar_never_exceeds_candidates(store):
    papers = [paper(f"2508.0000{i}") for i in range(5)]
    signals = {p.arxiv_id: fake_signal(3, 20) for p in papers}
    result = run(store, papers, signals)
    assert len(result.radar) + sum(result.cuts.values()) <= len(papers)
```

- [ ] **Passo 2: Rodar o teste e confirmar que falha**

Rodar: `python -m pytest tests/test_pipeline.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.pipeline'`

- [ ] **Passo 3: Implementar o pipeline**

`src/radar/pipeline.py`:

```python
"""Orquestracao. Unico modulo que conhece todas as pecas ao mesmo tempo.

Todos os servicos externos entram por injecao (fetch_papers, fetch_signal,
judge_all), o que torna o fluxo inteiro testavel offline.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from .config import ScopeConfig, Thresholds
from .models import Judgment, Paper, RepoClassification, Signal
from .render import RadarItem, render_markdown, render_telegram
from .scoring import evaluate
from .store import Store


@dataclass
class DayResult:
    radar: list[RadarItem]
    feed: list[RadarItem]
    cuts: dict[str, int]
    markdown: str
    push: str


def run_day(
    store: Store,
    scope: ScopeConfig,
    thresholds: Thresholds,
    today: date,
    model: str,
    fetch_papers: Callable[[ScopeConfig], list[Paper]],
    fetch_signal: Callable[[Paper, date], tuple[Signal, list[RepoClassification]]],
    judge_all: Callable[[list[Paper]], dict[str, Judgment]],
) -> DayResult:
    day = today.isoformat()
    papers = fetch_papers(scope)
    judgments = judge_all(papers) if papers else {}

    cuts: Counter[str] = Counter()
    candidates: list[tuple[RadarItem, bool]] = []   # (item, elegivel_para_push)
    repos_by_paper: dict[str, list[dict]] = {}

    for paper in papers:
        judgment = judgments.get(paper.arxiv_id)
        if judgment is None:
            cuts["sem_julgamento"] += 1
            continue

        try:
            signal, classifications = fetch_signal(paper, today)
        except Exception:
            # Falha de sinal num paper nao derruba o digest do dia inteiro.
            # `parse_search` levanta de proposito quando a resposta do GitHub e
            # de erro ou vem marcada como incompleta -- melhor pular o paper e
            # pega-lo na re-consulta de amanha do que gravar um zero falso que
            # significaria "ninguem implementou isto". Mesma licao da Tarefa 4.
            cuts["sinal_indisponivel"] += 1
            continue

        result = evaluate(signal, thresholds)

        store.upsert_paper(paper, seen_at=day)
        store.record_signal(paper.arxiv_id, signal, score=result.value, checked_at=day)
        store.record_repos(paper.arxiv_id, classifications)
        store.record_judgment(paper.arxiv_id, judgment, model=model, judged_at=day)
        store.touch_checked(paper.arxiv_id, at=day)
        repos_by_paper[paper.arxiv_id] = store.repos_for(paper.arxiv_id)

        item = RadarItem(paper=paper, judgment=judgment, signal=signal,
                         score=result.value or 0.0,
                         delta=store.signal_delta(paper.arxiv_id))

        # Todo paper no escopo vai para o feed, inclusive o cortado do radar.
        if result.gated_by is not None:
            cuts["ja_estourou"] += 1
            candidates.append((item, False))
        elif result.value < thresholds.score_floor:
            cuts["abaixo_do_piso"] += 1
            candidates.append((item, False))
        elif store.was_delivered(paper.arxiv_id, channel="telegram"):
            cuts["ja_entregue"] += 1
            candidates.append((item, False))
        else:
            candidates.append((item, True))

    feed = [item for item, _ in candidates]

    # Ordem: executavel na 3090 primeiro, score depois. Sem isso, um paper que
    # depende de FP8 -- inexecutavel em Ampere por definicao -- consome uma das
    # tres vagas competindo de igual para igual com o que voce pode testar hoje.
    # Rebaixar preserva a visao periferica sem deixar o inexecutavel disputar
    # espaco com o acionavel. Afeta o push apenas; o feed leva tudo.
    eligible = sorted(
        (i for i, ok in candidates if ok),
        key=lambda i: (i.judgment.runs_on_3090 != "nao", i.score),
        reverse=True,
    )
    radar = eligible[:thresholds.push_cap]

    for rank, item in enumerate(radar, start=1):
        store.mark_delivered(item.paper.arxiv_id, channel="telegram", at=day, rank=rank)
    for item in feed:
        store.mark_delivered(item.paper.arxiv_id, channel="markdown", at=day, rank=None)

    return DayResult(
        radar=radar,
        feed=feed,
        cuts=dict(cuts),
        markdown=render_markdown(day, radar=radar, feed=feed,
                                 cuts=dict(cuts), repos=repos_by_paper),
        push=render_telegram(radar),
    )
```

- [ ] **Passo 4: Rodar os testes e confirmar que passam**

Rodar: `python -m pytest tests/test_pipeline.py -v`
Esperado: 21 passed

- [ ] **Passo 5: Implementar o CLI**

`src/radar/cli.py`:

```python
"""Ponto de entrada. Monta os adaptadores reais e chama o pipeline."""
from __future__ import annotations

import argparse
import os
import time
from datetime import date, timezone, datetime
from pathlib import Path

import anthropic
import httpx

from .arxiv import USER_AGENT, ArxivClient
from .config import DEFAULT_SCOPE, load_model, load_thresholds
from .github import GitHubClient
from .judge import Judge, collect_batch_results, submit_batch
from .pipeline import run_day
from .store import Store
from .telegram import send

GITHUB_SLEEP_SECONDS = 2.5   # 10 req/min sem token; com token da folga


def _arxiv_fetch(url: str) -> str:
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    r.raise_for_status()
    return r.text


def _github_fetch(url: str) -> dict:
    headers = {"User-Agent": "ai-radar/0.1", "Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.get(url, headers=headers, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _telegram_post(url: str, json: dict) -> dict:
    r = httpx.post(url, json=json, timeout=30.0)
    r.raise_for_status()
    return r.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar")
    parser.add_argument("--db", type=Path, default=Path("data/radar.db"))
    parser.add_argument("--out", type=Path, default=Path("radar"))
    parser.add_argument("--dry-run", action="store_true",
                        help="nao envia o push nem grava entregas de telegram")
    args = parser.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    store = Store(args.db)
    store.init_schema()

    arxiv = ArxivClient(fetch=_arxiv_fetch)
    github = GitHubClient(fetch=_github_fetch)
    client = anthropic.Anthropic()
    model = load_model()

    def fetch_signal(paper, day):
        time.sleep(GITHUB_SLEEP_SECONDS)
        return github.signal_with_repos(paper, today=day)

    def judge_all(papers):
        if not papers:
            return {}
        batch = submit_batch(client, papers, model)
        while True:
            status = client.messages.batches.retrieve(batch.id).processing_status
            if status == "ended":
                break
            time.sleep(30)
        return collect_batch_results(client.messages.batches.results(batch.id))

    result = run_day(
        store=store, scope=DEFAULT_SCOPE, thresholds=load_thresholds(), today=today,
        model=model,
        fetch_papers=arxiv.recent, fetch_signal=fetch_signal, judge_all=judge_all,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{today.isoformat()}.md").write_text(result.markdown, encoding="utf-8")
    print(f"radar: {len(result.radar)} · feed: {len(result.feed)} · cortes: {result.cuts}")

    if not args.dry_run:
        sent = send(result.push,
                    token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                    chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
                    post=_telegram_post)
        print(f"push enviado: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Passo 6: Rodar a suíte inteira**

Rodar: `python -m pytest -v`
Esperado: tudo passa, offline.

- [ ] **Passo 7: Propor commit (aguardar aprovação)**

```bash
git add src/radar/pipeline.py src/radar/cli.py tests/test_pipeline.py
git commit -m "feat: pipeline diario com teto rigido e contabilidade de cortes"
```

---

## Tarefa 11: Workflow do GitHub Actions

**Arquivos:**
- Criar: `.github/workflows/radar.yml`
- Criar: `README.md` (só a seção de operação)

**Interfaces:**
- Consome: o CLI da Tarefa 10.
- Produz: execução diária automatizada.

**Nota de aprovação:** este é o passo que exige repositório no GitHub. Criar o repositório, o primeiro push e configurar segredos são ações que precisam de aprovação explícita do Lucas, uma por uma.

- [ ] **Passo 1: Escrever o workflow**

`.github/workflows/radar.yml`:

```yaml
name: radar

on:
  schedule:
    - cron: '0 9 * * *'      # 09:00 UTC = 06:00 em Brasilia
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Rodar sem enviar o push'
        type: boolean
        default: false

permissions:
  contents: write            # necessario para commitar o db e o markdown

concurrency:
  group: radar
  cancel-in-progress: false  # nunca cancelar: o run parcial ja gravou estado

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Instalar
        run: pip install -e .

      - name: Rodar o radar
        env:
          ANTHROPIC_API_KEY:  ${{ secrets.ANTHROPIC_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID:   ${{ secrets.TELEGRAM_CHAT_ID }}
          GH_TOKEN:           ${{ secrets.GH_TOKEN }}
        run: |
          python -m radar.cli ${{ inputs.dry_run && '--dry-run' || '' }}

      - name: Commitar estado e digest
        run: |
          git config user.name  "radar-bot"
          git config user.email "radar-bot@users.noreply.github.com"
          git add data/radar.db radar/
          git diff --staged --quiet || git commit -m "radar: digest de $(date -u +%F)"
          git push
```

- [ ] **Passo 2: Validar a sintaxe do workflow localmente**

Rodar:

```bash
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/radar.yml')); print('yaml valido')"
```

Esperado: `yaml valido`

- [ ] **Passo 3: Escrever a seção de operação do README**

`README.md` precisa conter, no mínimo:

```markdown
## Operação

Roda diariamente às 09:00 UTC via GitHub Actions. Para rodar à mão sem enviar push:

    python -m radar.cli --dry-run

### Segredos necessários

| Segredo | Obrigatório | Para quê |
|---|---|---|
| `ANTHROPIC_API_KEY` | sim | julgamento e resumo |
| `TELEGRAM_BOT_TOKEN` | sim | push diário |
| `TELEGRAM_CHAT_ID` | sim | destino do push |
| `GH_TOKEN` | não | eleva o rate limit de busca de 10 para 30 req/min |

**Segredos de Actions não viajam com o repositório.** Se o repo for movido,
renomeado ou recriado, todos precisam ser repostos — e a falha aparece em
runtime, não no push.

### Calibração pendente

`RADAR_BROKE_OUT_STARS` (1000), `RADAR_BROKE_OUT_CITATIONS` (200) e
`RADAR_SCORE_FLOOR` (0.0) são chutes. As duas primeiras semanas rodam com o piso
em zero, e a seção de cortes de cada digest registra o que foi barrado por qual
limiar. Calibrar depois de observar a distribuição real.
```

- [ ] **Passo 4: Propor a criação do repositório (aguardar aprovação, item por item)**

Apresentar ao Lucas, **um de cada vez**, esperando o sim antes de cada:

1. `git init` e primeiro commit local
2. Criar o repositório no GitHub (privado)
3. `git push` inicial
4. Configurar os quatro segredos

- [ ] **Passo 5: Primeira execução real em dry-run**

Depois de tudo configurado, disparar `workflow_dispatch` com `dry_run: true` e conferir no log: quantos papers vieram do arXiv, quantos passaram o portão, quanto custou. Só então rodar sem dry-run.

---

## Auto-revisão do plano

Conferido contra a spec antes de entregar.

**Cobertura:** seção 3 (arXiv + escopo) → Tarefas 1 e 4. Seção 4 (sinal, autoria, portão) → Tarefas 2, 3, 5. Seção 5 (LLM, batch) → Tarefa 7. Seção 6 (SQLite) → Tarefa 6. Seção 7 (entrega) → Tarefas 8 e 9. Seção 8 (Actions) → Tarefa 11. Seção 9 (restrições globais) → travadas por teste nas tarefas correspondentes: teto de 3 na 8 e na 10, cortes obrigatórios na 8, sem emoji na 8, aprovação de git na 11.

**Sem Semantic Scholar.** A spec lista `citations` como opcional. O plano passa `citations=0` em toda parte e o campo existe no schema e na fórmula. Adicionar a fonte depois é uma função nova, não uma mudança de arquitetura — decisão consciente para não inflar o escopo do primeiro corte.

**Achado da varredura pré-voo (corrigido):** a primeira versão do pipeline chamava `record_judgment(..., model="")`. O schema aceita, mas o registro fica sem dizer qual modelo julgou — e a coluna existe exatamente para isso. `run_day` agora recebe `model` e o repassa; a Tarefa 10 tem teste travando o comportamento.

**Consistência de tipos:** `Signal`, `ScoreResult`, `RadarItem` e `Judgment` têm os mesmos campos em todas as tarefas que os tocam. `evaluate()` devolve `ScoreResult` em 2, 10. `classify_repos()` devolve `list[RepoClassification]` em 3, 5, 6.

## Ordem de execução

Tarefas 1 a 10 rodam inteiras offline, num Mac, sem chave de API e sem repositório no GitHub. Só a Tarefa 11 precisa de infra externa — e ela é a única que exige aprovação de git.
