# Segundo Escopo e Julgamento Reescrito — Plano de Implementação

> **Para trabalhadores agênticos:** SUB-SKILL OBRIGATÓRIA: use
> superpowers:subagent-driven-development (recomendado) ou
> superpowers:executing-plans para implementar tarefa a tarefa. Os passos usam
> caixas (`- [ ]`) para rastreio.

**Objetivo:** ligar um segundo escopo (harness de agentes) ao lado do escopo de
inferência, trocar o eixo de julgamento que não discrimina por uma taxonomia
fechada mais um veredito acionável, e preencher com dado real o campo de
citações que esteve constante em zero desde o dia um.

**Arquitetura:** nada muda na forma. Núcleo puro, borda fina de IO, cada serviço
externo atrás de um adaptador que recebe o transporte por injeção. O segundo
escopo não é um segundo pipeline: é a mesma `run_day` chamada duas vezes, com a
composição do dia acontecendo por cima. O OpenAlex entra como quarto adaptador,
irmão de `arxiv`, `github` e `judge`.

**Stack:** Python 3.12, `anthropic`, `httpx`, `pydantic`, `pytest`, sqlite3.
Nenhuma dependência nova — o OpenAlex usa o `httpx` que já está lá.

**Spec:** `docs/2026-08-29-segundo-escopo-spec.md`

---

## Restrições globais

**Git exige aprovação por ação.** Nenhum `git add`, `git commit`, `git push` ou
criação de repositório sem aprovação explícita do Lucas para aquela ação
específica. Os passos de commit deste plano são **propostas**: mostrar o comando
e esperar o sim.

**Sem trailer de co-autoria** em nenhuma mensagem de commit. Mensagens em
português, imperativo, sem emoji.

**A suíte atual tem 195 testes e nenhum pode quebrar.** Cada tarefa termina com
a suíte inteira verde. Uma tarefa que deixa a suíte vermelha não está pronta,
mesmo que o teste novo passe.

**Testes rodam sem rede.** Todo adaptador recebe o transporte por injeção; nenhum
teste pode fazer requisição de verdade.

**A camada pura continua pura.** `scoring.py`, `authorship.py` e `render.py` não
importam `httpx`, `anthropic` nem `sqlite3`. Existe teste que trava isso.

**`citations = None` significa desconhecido, nunca zero.** Nenhum caminho pode
converter um para o outro. Esta é a restrição que a tarefa 2 existe para
estabelecer e que todas as seguintes precisam preservar.

**`ganho_fator` é razão de melhora, sempre > 0.** Pontos percentuais de
qualidade não viram fator — ficam só em `ganho_texto`.

**Todo corte é contado e chega ao markdown.** Restrição global do projeto desde
a spec original; nenhuma tarefa aqui pode introduzir descarte silencioso.

**A cota da Anthropic está esgotada até 2026-09-01 00:00 UTC.** Tarefas 1 a 10
rodam offline e não são afetadas; as Tarefas 5-bis e 11 esperam.

**Ambiente:** `/Users/luskoliveira/.pyenv/versions/3.12.3/bin/python`, testes com
`PYTHONPATH=src <python> -m pytest`. Não rodar `pip install`. Se um teste falhar
de forma inexplicável após editar fonte, limpar `__pycache__` e `.pytest_cache`.

**Nunca trocar o modelo** por um mais barato. `claude-opus-5`, lido de
`RADAR_MODEL` com esse default.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Tarefas |
|---|---|---|
| `src/radar/config.py` | `ScopeConfig.name`, `AGENT_SCOPE` | 1 |
| `src/radar/models.py` | `Signal.citations` nulável, `Judgment` novo | 2, 4 |
| `src/radar/scoring.py` | portão que não dispara em `None` | 2 |
| `src/radar/openalex.py` | **novo** — adaptador de citações | 3 |
| `src/radar/judge.py` | schema, briefing e prompt novos | 5 |
| `src/radar/store.py` | `papers.scope`, `judgments` novo | 6 |
| `src/radar/render.py` | usa `pratica`; `compose_day` | 7, 9 |
| `src/radar/pipeline.py` | escopo e citações no laço | 8 |
| `src/radar/cli.py` | dois escopos, OpenAlex, composição | 10 |
| `scripts/migrar_e_rejulgar.py` | **novo** — operação pontual | 11 |

---

## Tarefa 1: `ScopeConfig.name` e `AGENT_SCOPE`

**Arquivos:** Modificar `src/radar/config.py`. Teste: `tests/test_config.py`.

**Interfaces:**
- Produz: `ScopeConfig(name, categories, terms)` — `name` é o **primeiro** campo
  posicional, e `AGENT_SCOPE`, `DEFAULT_SCOPE.name == "inferencia"`.
- Consumido por: tarefas 6, 8 e 10.

**Por que `name` vem primeiro:** todo construtor de `ScopeConfig` no código e nos
testes usa argumentos nomeados. Pôr `name` primeiro deixa o campo obrigatório
sem default, que é o que impede alguém de criar escopo anônimo — e a tarefa 6
depende de `name` existir sempre.

- [ ] **Passo 1: escrever o teste que falha**

```python
# tests/test_config.py
from radar.config import AGENT_SCOPE, DEFAULT_SCOPE


def test_cada_escopo_tem_nome_proprio():
    assert DEFAULT_SCOPE.name == "inferencia"
    assert AGENT_SCOPE.name == "agentes"


def test_o_escopo_de_agentes_exclui_cs_lg():
    # cs.LG triplica o volume com RL e robotica; medido em 2026-08-29:
    # 75 papers/dia com cs.LG contra 25/dia sem. Ver spec secao 2.
    assert "cs.LG" not in AGENT_SCOPE.categories
    assert set(AGENT_SCOPE.categories) == {"cs.AI", "cs.CL", "cs.SE", "cs.MA"}


def test_o_escopo_de_agentes_nao_carrega_termo_morto():
    # `tool retrieval` foi medido e nao trouxe um paper inedito sequer:
    # tudo que ele acha ja vem por `tool use` ou `tool calling`.
    assert "tool retrieval" not in AGENT_SCOPE.terms
    assert len(AGENT_SCOPE.terms) == 17


def test_os_dois_escopos_nao_compartilham_termo():
    assert not (set(AGENT_SCOPE.terms) & set(DEFAULT_SCOPE.terms))
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_config.py -v`
Esperado: FAIL com `ImportError: cannot import name 'AGENT_SCOPE'`

- [ ] **Passo 3: implementar**

Em `src/radar/config.py`, adicionar `name` ao dataclass e o escopo novo:

```python
@dataclass(frozen=True)
class ScopeConfig:
    name: str                      # 'inferencia' | 'agentes'
    categories: tuple[str, ...]
    terms: tuple[str, ...]


DEFAULT_SCOPE = ScopeConfig(
    name="inferencia",
    categories=("cs.LG", "cs.CL", "cs.DC", "cs.AR", "cs.PF"),
    terms=(
        "quantization", "speculative decoding", "KV cache",
        "inference latency", "inference throughput", "sparsity",
        "pruning", "low-rank", "attention kernel", "memory bandwidth",
        "model serving", "efficient inference",
    ),
)

# Medido em 2026-08-29 pela mesma consulta que o pipeline usa: ~25 papers/dia.
# A lista ingenua tinha 20 termos sobre cs.AI/cs.CL/cs.LG/cs.SE/cs.MA e dava
# ~75/dia, com `agentic`, `trajectory` e `planning` saturando o teto de 200 por
# semana -- os tres capturam trajetoria de robo e planejamento classico, nao
# harness. Tirar cs.LG e os tres cortou dois tercos sem perder nada especifico.
AGENT_SCOPE = ScopeConfig(
    name="agentes",
    categories=("cs.AI", "cs.CL", "cs.SE", "cs.MA"),
    terms=(
        "agent harness", "LLM agent", "agent trajectory", "tool use",
        "tool calling", "function calling", "agent memory",
        "context management", "context engineering", "prompt caching",
        "agent evaluation", "agent benchmark", "computer use", "code agent",
        "self-correction", "guardrail", "agent orchestration",
    ),
)
```

- [ ] **Passo 4: corrigir os construtores existentes**

`ScopeConfig(...)` aparece em testes que constroem escopo sintético. Todos
precisam de `name=`. Encontre-os com:

```bash
grep -rn 'ScopeConfig(' src tests
```

Cada ocorrência ganha `name="teste"` (ou nome descritivo). **Não** dê default a
`name` para calar o erro — o default é exatamente o que permitiria escopo
anônimo chegar ao banco.

- [ ] **Passo 5: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 199 passed (195 + 4 novos), 5 skipped

- [ ] **Passo 6: propor commit**

```bash
git add src/radar/config.py tests/test_config.py
git commit -m "feat: escopo ganha nome e entra o escopo de agentes"
```

---

## Tarefa 2: `citations` nulável e o portão que respeita `None`

**Arquivos:** Modificar `src/radar/models.py` e `src/radar/scoring.py`.
Testes: `tests/test_models.py`, `tests/test_scoring.py`.

**Interfaces:**
- Produz: `Signal.citations: int | None`, default `None`.
- `evaluate` trata `None` como **desconhecido**: não dispara portão, e contribui
  `0` para a atenção.

**O achado que motiva a tarefa:** `signals.citations` é `0` nas 1088 linhas do
seed. `GitHubClient.signal_with_repos` recebe `citations: int = 0` e nenhum
chamador jamais passou outro valor. O portão de 200 citações nunca disparou, e
`atencao = log1p(stars) + log1p(citations)` sempre foi só estrelas.

**A distinção que a tarefa estabelece:** `0` é "ninguém citou". `None` é "não
sabemos". A tarefa 3 mostra que ~8% dos papers não resolvem no OpenAlex — se
esses virarem `0`, o bug volta com outra roupa.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_scoring.py
from radar.config import Thresholds
from radar.models import Signal
from radar.scoring import evaluate

LIMIARES = Thresholds(broke_out_stars=1000, broke_out_citations=200,
                      score_floor=0.0)


def test_citacao_desconhecida_nao_dispara_o_portao():
    # Um paper sem citacao resolvida nao pode ser cortado por citacao:
    # nao sabemos o numero. Cortar aqui seria inventar dado.
    s = Signal(total_impls=3, independent_impls=3, velocity_14d=1,
               stars_total=10, citations=None)
    assert evaluate(s, LIMIARES).gated_by is None


def test_citacao_desconhecida_contribui_zero_para_atencao():
    # log1p(0) == 0, entao desconhecido e "ninguem citou" pontuam igual.
    # Isso e deliberado: a alternativa seria descartar o paper, e um paper
    # sem DOI no OpenAlex nao merece sumir do radar.
    conhecida = Signal(total_impls=3, independent_impls=3, velocity_14d=1,
                       stars_total=10, citations=0)
    desconhecida = Signal(total_impls=3, independent_impls=3, velocity_14d=1,
                          stars_total=10, citations=None)
    assert evaluate(desconhecida, LIMIARES).value == evaluate(conhecida, LIMIARES).value


def test_citacao_conhecida_acima_do_limiar_ainda_corta():
    s = Signal(total_impls=3, independent_impls=3, velocity_14d=1,
               stars_total=10, citations=201)
    assert evaluate(s, LIMIARES).gated_by == "citacoes"


def test_citacao_negativa_continua_sendo_erro():
    s = Signal(total_impls=3, independent_impls=3, velocity_14d=1,
               stars_total=10, citations=-1)
    try:
        evaluate(s, LIMIARES)
    except ValueError as e:
        assert "citations" in str(e)
    else:
        raise AssertionError("citacao negativa deveria explodir")
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_scoring.py -v -k desconhecid`
Esperado: FAIL — `Signal(citations=None)` passa hoje, mas `evaluate` compara
`None > 200` e levanta `TypeError`.

- [ ] **Passo 3: implementar em `models.py`**

```python
@dataclass(frozen=True)
class Signal:
    total_impls: int
    independent_impls: int
    velocity_14d: int
    stars_total: int
    citations: int | None = None    # None = desconhecido, NUNCA zero
```

- [ ] **Passo 4: implementar em `scoring.py`**

```python
def evaluate(signal: Signal, thresholds: Thresholds) -> ScoreResult:
    for name, value in (
        ("total_impls", signal.total_impls),
        ("independent_impls", signal.independent_impls),
        ("velocity_14d", signal.velocity_14d),
        ("stars_total", signal.stars_total),
        ("citations", signal.citations),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} negativo: {value}")

    if signal.stars_total > thresholds.broke_out_stars:
        return ScoreResult(value=None, gated_by="estrelas")
    # `None` e desconhecido: nao ha numero para comparar com o limiar, e
    # inventar zero para poder comparar seria fabricar dado. O paper passa.
    if signal.citations is not None and signal.citations > thresholds.broke_out_citations:
        return ScoreResult(value=None, gated_by="citacoes")

    strength = log1p(signal.independent_impls) * (1 + 0.5 * log1p(signal.velocity_14d))
    attention = log1p(signal.stars_total) + log1p(signal.citations or 0)
    return ScoreResult(value=strength / (1 + attention), gated_by=None)
```

- [ ] **Passo 5: mutação — provar que o teste pega**

Troque `if signal.citations is not None and signal.citations >` por
`if (signal.citations or 0) >`. Rode
`pytest tests/test_scoring.py -k desconhecida`. Deve continuar **passando** —
o que mostra que aquele teste sozinho não trava a distinção. Agora troque para
`if (signal.citations or 999) >`: `test_citacao_desconhecida_nao_dispara_o_portao`
falha. Restaure.

Este passo existe porque `or 0` é a refatoração errada mais provável, e ela é
silenciosa: só quebra quando alguém depois trocar o default.

- [ ] **Passo 6: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 203 passed, 5 skipped

- [ ] **Passo 7: propor commit**

```bash
git add src/radar/models.py src/radar/scoring.py tests/test_scoring.py
git commit -m "feat: citacao desconhecida deixa de ser zero e nao dispara portao"
```

---

## Tarefa 3: `OpenAlexClient`

**Arquivos:** Criar `src/radar/openalex.py`. Teste: `tests/test_openalex.py`.

**Interfaces:**
- Produz: `OpenAlexClient(fetch).citations_for(ids: list[str]) -> dict[str, int | None]`
- `MAX_POR_LOTE = 50`
- Consumido por: tarefas 8 e 10.

**Medições que travam o desenho (2026-08-29):**

| o que | resultado |
|---|---|
| Semantic Scholar sem chave | `429` na 1ª chamada, **2 sucessos em 6** |
| OpenAlex, filtro OR por DOI | **5 de 5 numa requisição, 0,38s** |
| Contagem real | LoRA 2527, FlashAttention 461, GPTQ 136 |
| Resolução | ~92% — "Attention Is All You Need" **não** resolve |

**Três armadilhas que os testes precisam travar:**

1. O DOI volta em **caixa baixa** (`arxiv.`) e a consulta usa `arXiv.`. Casamento
   case-insensitive, ou toda linha se perde calada.
2. **Ausente é `None`, não `0`.** Papers anteriores a ~2022 podem não ter DOI
   `10.48550/arXiv.*`.
3. **Falha da API inteira degrada para `None` em todos**, nunca para `0`.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_openalex.py
import pytest
from radar.openalex import MAX_POR_LOTE, OpenAlexClient, build_url


def test_a_url_pede_so_os_dois_campos_que_importam():
    url = build_url(["2608.27428"])
    assert "select=doi%2Ccited_by_count" in url or "select=doi,cited_by_count" in url
    assert "10.48550/arXiv.2608.27428" in url


def test_a_url_junta_varios_ids_num_filtro_or():
    url = build_url(["2608.27428", "2608.27351"])
    assert "%7C" in url or "|" in url


def test_lote_acima_do_teto_e_recusado():
    with pytest.raises(ValueError, match="50"):
        build_url([f"26{i:02d}.00001" for i in range(51)])


def test_o_doi_volta_em_caixa_baixa_e_ainda_casa():
    # A API responde `arxiv.` mesmo tendo sido consultada com `arXiv.`.
    # Sem casamento case-insensitive toda linha se perde em silencio.
    resposta = {"results": [
        {"doi": "https://doi.org/10.48550/arxiv.2608.27428", "cited_by_count": 7},
    ]}
    c = OpenAlexClient(fetch=lambda url: resposta)
    assert c.citations_for(["2608.27428"]) == {"2608.27428": 7}


def test_paper_ausente_vira_none_e_nunca_zero():
    # "Attention Is All You Need" nao resolve: o arXiv so passou a cunhar DOI
    # automatico por volta de 2022. Gravar 0 aqui recria o bug que esta
    # tarefa existe para consertar.
    resposta = {"results": [
        {"doi": "https://doi.org/10.48550/arxiv.2608.27428", "cited_by_count": 7},
    ]}
    c = OpenAlexClient(fetch=lambda url: resposta)
    r = c.citations_for(["2608.27428", "1706.03762"])
    assert r["1706.03762"] is None
    assert r["1706.03762"] != 0


def test_zero_de_verdade_e_preservado_como_zero():
    resposta = {"results": [
        {"doi": "https://doi.org/10.48550/arxiv.2608.27428", "cited_by_count": 0},
    ]}
    c = OpenAlexClient(fetch=lambda url: resposta)
    assert c.citations_for(["2608.27428"]) == {"2608.27428": 0}


def test_falha_da_api_degrada_para_none_em_todos():
    def explode(url):
        raise RuntimeError("openalex fora do ar")
    c = OpenAlexClient(fetch=explode)
    r = c.citations_for(["2608.27428", "2608.27351"])
    assert r == {"2608.27428": None, "2608.27351": None}


def test_lista_vazia_nao_faz_requisicao():
    def nao_deveria(url):
        raise AssertionError("nao pode chamar a rede com lista vazia")
    assert OpenAlexClient(fetch=nao_deveria).citations_for([]) == {}
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_openalex.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.openalex'`

- [ ] **Passo 3: implementar**

```python
# src/radar/openalex.py
"""Adaptador de citacoes.

O Semantic Scholar foi medido primeiro e reprovado: sem chave devolve 429 na
primeira chamada e acertou 2 de 6 tentativas com espera crescente. Uma fonte
que falha dois tercos das vezes gravaria zeros silenciosos -- exatamente o
defeito que este modulo existe para consertar.

O OpenAlex resolve 50 papers numa requisicao em 0,38s sem chave nenhuma; basta
um `mailto:` no User-Agent para cair no pool "polite".
"""
from __future__ import annotations

import logging
from typing import Callable
from urllib.parse import urlencode

_log = logging.getLogger(__name__)

BASE = "https://api.openalex.org/works"
MAX_POR_LOTE = 50          # teto de `per-page` da API
USER_AGENT = "ai-radar/0.1 (mailto:luskoliveira@protonmail.com)"

_PREFIXO = "https://doi.org/10.48550/arXiv."


def build_url(arxiv_ids: list[str]) -> str:
    if len(arxiv_ids) > MAX_POR_LOTE:
        raise ValueError(
            f"{len(arxiv_ids)} ids num lote; o teto da API e {MAX_POR_LOTE}"
        )
    filtro = "|".join(f"{_PREFIXO}{i}" for i in arxiv_ids)
    return f"{BASE}?" + urlencode({
        "filter": f"doi:{filtro}",
        "select": "doi,cited_by_count",
        "per-page": str(MAX_POR_LOTE),
    })


def _id_do_doi(doi: str) -> str:
    """Extrai o arXiv ID de um DOI do OpenAlex.

    A API responde `arxiv.` mesmo tendo sido consultada com `arXiv.`. Casar
    sensivel a caixa faz TODA linha se perder, e o sintoma seria citacoes
    sempre nulas -- indistinguivel do bug que estamos consertando.
    """
    marca = "10.48550/arxiv."
    baixa = doi.lower()
    if marca not in baixa:
        return ""
    return doi[baixa.index(marca) + len(marca):]


class OpenAlexClient:
    def __init__(self, fetch: Callable[[str], dict]) -> None:
        self._fetch = fetch

    def citations_for(self, arxiv_ids: list[str]) -> dict[str, int | None]:
        """Devolve citacoes por id. Ausente e `None`, jamais `0`."""
        if not arxiv_ids:
            return {}

        # Comeca tudo desconhecido. So um resultado explicito vira numero.
        fora: dict[str, int | None] = {i: None for i in arxiv_ids}

        for inicio in range(0, len(arxiv_ids), MAX_POR_LOTE):
            fatia = arxiv_ids[inicio:inicio + MAX_POR_LOTE]
            try:
                payload = self._fetch(build_url(fatia))
            except Exception:
                # Degrada para desconhecido, nunca para zero: a diferenca entre
                # "ninguem citou" e "nao perguntamos" e a razao deste modulo.
                _log.warning("openalex falhou para %d ids; ficam desconhecidos",
                             len(fatia))
                continue
            for obra in payload.get("results", []):
                ident = _id_do_doi(obra.get("doi") or "")
                if ident in fora:
                    fora[ident] = obra.get("cited_by_count")
        return fora
```

- [ ] **Passo 4: rodar os testes novos**

Run: `PYTHONPATH=src <python> -m pytest tests/test_openalex.py -v`
Esperado: 8 passed

- [ ] **Passo 5: mutação — provar que o caso da caixa está travado**

Em `_id_do_doi`, troque `baixa = doi.lower()` por `baixa = doi`. Rode
`pytest tests/test_openalex.py -k caixa_baixa`. Deve **falhar**. Restaure.

- [ ] **Passo 6: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 211 passed, 5 skipped

- [ ] **Passo 7: propor commit**

```bash
git add src/radar/openalex.py tests/test_openalex.py
git commit -m "feat: adaptador de citacoes pelo OpenAlex"
```

---
## Tarefa 4: `Judgment` ganha família, prática e ganho

**Arquivos:** Modificar `src/radar/models.py`. Teste: `tests/test_models.py`.

**Interfaces:**
- Produz: `FAMILIAS`, `PRATICAS`, `GANHO_EIXOS` (frozensets) e o `Judgment` com
  os campos novos.
- Consumido por: tarefas 5, 6 e 7.

**Os campos novos entram com default nesta tarefa, e perdem o default na
tarefa 7.** É o que mantém a suíte verde no caminho: todo construtor existente
de `Judgment` continua válido enquanto os consumidores migram um por vez.
`runs_on_3090` segue vivo aqui e morre na tarefa 7.

**Por que 19 famílias e não 18:** `outro` não é preguiça de taxonomia, é
instrumento. Sem ele o modelo é forçado a encaixar mal e o erro fica invisível;
com ele, a frequência de `outro` mede se a taxonomia está errada. O gate da
spec é 10%.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_models.py
import pytest
from radar.models import FAMILIAS, GANHO_EIXOS, PRATICAS, Judgment


def julgamento(**kw):
    base = dict(technique="t", familia="cache_kv", pratica="testar",
                ganho_eixo="velocidade", ganho_fator=2.3,
                ganho_texto="2.3x mais rapido que vLLM",
                resumo="r", porque="p")
    return Judgment(**{**base, **kw})


def test_a_taxonomia_tem_dezenove_valores_com_o_escape():
    assert len(FAMILIAS) == 19
    assert "outro" in FAMILIAS


def test_familia_fora_da_taxonomia_e_recusada():
    with pytest.raises(ValueError, match="familia"):
        julgamento(familia="quantizacao_magica")


def test_pratica_fora_do_conjunto_e_recusada():
    assert PRATICAS == frozenset({"adotar", "testar", "observar", "nao_aplica"})
    with pytest.raises(ValueError, match="pratica"):
        julgamento(pratica="talvez")


def test_ganho_eixo_fora_do_conjunto_e_recusado():
    assert GANHO_EIXOS == frozenset(
        {"velocidade", "memoria", "custo", "qualidade", "nenhum"})
    with pytest.raises(ValueError, match="ganho_eixo"):
        julgamento(ganho_eixo="elegancia")


def test_sem_eixo_de_ganho_nao_pode_haver_fator():
    # Um fator sem dimensao e numero solto. Se o paper nao alega nada,
    # nao existe 2.3 de coisa nenhuma.
    with pytest.raises(ValueError, match="ganho_fator"):
        julgamento(ganho_eixo="nenhum", ganho_fator=2.3)


def test_sem_eixo_de_ganho_o_fator_nulo_e_valido():
    j = julgamento(ganho_eixo="nenhum", ganho_fator=None, ganho_texto="")
    assert j.ganho_fator is None


def test_fator_precisa_ser_razao_de_melhora():
    # Fator e razao: 2.3x melhor. Zero e negativo nao sao razao de melhora,
    # e um zero aqui viraria coordenada invalida no grafico do jornal.
    for ruim in (0, -1.0, 0.0):
        with pytest.raises(ValueError, match="ganho_fator"):
            julgamento(ganho_fator=ruim)


def test_fator_abaixo_de_um_e_valido_porque_e_piora_relativa_declarada():
    # 0.8 significa "entrega 80% do baseline". E razao positiva, e o paper
    # pode legitimamente alegar isso ao trocar qualidade por velocidade.
    assert julgamento(ganho_fator=0.8).ganho_fator == 0.8
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_models.py -v -k familia`
Esperado: FAIL com `ImportError: cannot import name 'FAMILIAS'`

- [ ] **Passo 3: implementar**

Em `src/radar/models.py`, acima de `Judgment`:

```python
# Fechado por decisao de produto. O seed de 2026-08-29 produziu 1088 valores
# distintos de `technique` para 1088 papers: uma taxonomia com N categorias
# para N itens nao agrega nada, e agregacao e a razao de existir do acervo.
FAMILIAS = frozenset({
    # inferencia
    "quantizacao", "cache_kv", "decodificacao_especulativa",
    "esparsidade_e_poda", "kernels_e_atencao", "serving_e_batching",
    "arquitetura_eficiente", "destilacao", "treino_eficiente",
    # agentes
    "uso_de_ferramenta", "memoria_e_contexto", "planejamento_e_decomposicao",
    "orquestracao_multiagente", "avaliacao_de_agente", "recuperacao_de_falha",
    "agentes_de_codigo", "seguranca_e_guardrails", "recuperacao_e_rag",
    # escape, e instrumento de medicao: frequencia alta de `outro` significa
    # que faltam familias, e as que faltam se descobrem lendo o que caiu aqui.
    "outro",
})

PRATICAS = frozenset({"adotar", "testar", "observar", "nao_aplica"})
GANHO_EIXOS = frozenset({"velocidade", "memoria", "custo", "qualidade", "nenhum"})
```

E o dataclass:

```python
@dataclass(frozen=True)
class Judgment:
    technique: str
    summary: str
    runs_on_3090: str = "sim_com_ressalva"   # morre na tarefa 7
    rationale: str = ""                      # morre na tarefa 7
    familia: str = "outro"
    pratica: str = "observar"
    ganho_eixo: str = "nenhum"
    ganho_fator: float | None = None
    ganho_texto: str = ""
    resumo: str = ""
    porque: str = ""

    def __post_init__(self) -> None:
        if self.runs_on_3090 not in VALID_VERDICTS:
            raise ValueError(
                f"runs_on_3090={self.runs_on_3090!r} invalido; "
                f"use um de {sorted(VALID_VERDICTS)}"
            )
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
```

- [ ] **Passo 4: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 219 passed, 5 skipped. **Nenhum teste existente pode quebrar** — é
para isso que os campos novos entram com default.

- [ ] **Passo 5: propor commit**

```bash
git add src/radar/models.py tests/test_models.py
git commit -m "feat: julgamento ganha familia, pratica e ganho alegado"
```

---

## Tarefa 5: schema, briefing e prompt novos no julgador

**Arquivos:** Modificar `src/radar/judge.py`. Teste: `tests/test_judge.py`.

**Interfaces:**
- Consome: `FAMILIAS`, `PRATICAS`, `GANHO_EIXOS` da tarefa 4.
- Produz: `JudgmentSchema` com os campos novos, `LEITOR_BRIEF` no lugar de
  `HARDWARE_BRIEF`.

**O que sai e por quê:** `runs_on_3090` respondeu `sim_com_ressalva` em **566 de
1088 papers (52%)** no seed. Um eixo cuja resposta modal é "mais ou menos" não
separa nada e custa um campo de saída estruturada em todo julgamento.

**O `Literal` do Pydantic precisa dos 19 valores literais**, não de
`Literal[*FAMILIAS]` — `frozenset` não tem ordem estável, e um schema JSON que
muda de ordem entre execuções invalida cache de prompt. Escreva a tupla à mão e
deixe o teste garantir que ela bate com `FAMILIAS`.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_judge.py
from radar.judge import LEITOR_BRIEF, JudgmentSchema, build_prompt
from radar.models import FAMILIAS, GANHO_EIXOS, PRATICAS, Paper


def test_o_schema_cobre_exatamente_a_taxonomia():
    # Se alguem adicionar familia em models.py e esquecer do judge, o modelo
    # nunca consegue emitir o valor novo e o campo morre calado.
    campo = JudgmentSchema.model_fields["familia"]
    assert set(campo.annotation.__args__) == FAMILIAS


def test_o_schema_cobre_exatamente_as_praticas_e_os_eixos():
    assert set(JudgmentSchema.model_fields["pratica"].annotation.__args__) == PRATICAS
    eixo = JudgmentSchema.model_fields["ganho_eixo"].annotation.__args__
    assert set(eixo) == GANHO_EIXOS


def test_o_schema_proibe_campo_extra():
    # `additionalProperties: false` e exigido pelo contrato de saida
    # estruturada; sem ele a API rejeita o lote inteiro e todo paper do dia
    # vira `sem_julgamento`.
    assert JudgmentSchema.model_json_schema()["additionalProperties"] is False


def test_o_schema_nao_pergunta_mais_de_hardware():
    assert "runs_on_3090" not in JudgmentSchema.model_fields


def test_o_prompt_descreve_o_leitor_e_nao_a_placa():
    p = Paper(arxiv_id="2608.1", title="T", abstract="A", authors=(),
              categories=("cs.AI",), published="2026-08-01")
    texto = build_prompt(p)
    assert "infra pequena" in texto.lower()
    assert "3090" not in texto
    assert "RTX" not in texto


def test_o_prompt_pede_as_tres_perguntas_do_resumo():
    p = Paper(arxiv_id="2608.1", title="T", abstract="A", authors=(),
              categories=("cs.AI",), published="2026-08-01")
    texto = build_prompt(p)
    for exigencia in ("substitui", "custa", "quebra"):
        assert exigencia in texto.lower()
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_judge.py -v -k taxonomia`
Esperado: FAIL com `KeyError: 'familia'`

- [ ] **Passo 3: implementar**

Substitua `HARDWARE_BRIEF` por:

```python
LEITOR_BRIEF = (
    "O leitor e um engenheiro de AI/ML com INFRA PEQUENA: uma GPU de 24 GB ou "
    "APIs de terceiros, sem cluster, sem treino de modelo base, orcamento de "
    "nuvem baixo, time pequeno. Ele decide o que adotar nas praticas do dia a "
    "dia, nao o que pesquisar."
)
```

O schema:

```python
_FAMILIAS = (
    "quantizacao", "cache_kv", "decodificacao_especulativa",
    "esparsidade_e_poda", "kernels_e_atencao", "serving_e_batching",
    "arquitetura_eficiente", "destilacao", "treino_eficiente",
    "uso_de_ferramenta", "memoria_e_contexto", "planejamento_e_decomposicao",
    "orquestracao_multiagente", "avaliacao_de_agente", "recuperacao_de_falha",
    "agentes_de_codigo", "seguranca_e_guardrails", "recuperacao_e_rag",
    "outro",
)


class JudgmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technique: str = Field(description="Rotulo curto da tecnica, ate 8 palavras")
    familia: Literal[_FAMILIAS] = Field(
        description="A familia da tecnica. Use 'outro' apenas quando nenhuma "
                    "das dezoito couber de verdade -- encaixar a forca destroi "
                    "a agregacao, que e para o que este campo existe.")
    pratica: Literal["adotar", "testar", "observar", "nao_aplica"] = Field(
        description="O que o leitor faz com isso. 'adotar': da para usar ja, "
                    "com infra pequena, ganho claro, sem pre-requisito exotico. "
                    "'testar': plausivel com infra pequena, mas o ganho depende "
                    "de validacao no caso concreto. 'observar': importa, e exige "
                    "escala, hardware ou dado que ele nao tem. 'nao_aplica': "
                    "fora do que ele faz.")
    ganho_eixo: Literal["velocidade", "memoria", "custo", "qualidade", "nenhum"] = Field(
        description="Em que dimensao o paper alega melhorar. 'nenhum' quando o "
                    "paper nao faz alegacao quantificada -- resposta legitima "
                    "e frequente, nao use as outras por educacao.")
    ganho_fator: float | None = Field(
        default=None,
        description="O ganho como FATOR MULTIPLICATIVO de melhora, quando e so "
                    "quando o paper permite. '2.3x mais rapido' vira 2.3. "
                    "'reduz memoria em 60%' vira 2.5, que e 1/0.4. "
                    "'+3 pontos de acuracia' NAO vira fator: e null, porque "
                    "pontos percentuais nao sao razao. Com ganho_eixo='nenhum', "
                    "sempre null.")
    ganho_texto: str = Field(
        description="A alegacao como o paper a faz, em texto curto, para que o "
                    "numero seja auditavel ate a frase que o originou. String "
                    "vazia quando nao ha alegacao.")
    resumo: str = Field(
        description="Ate TRES frases, nesta ordem: o que a tecnica substitui, o "
                    "que ela custa (memoria, latencia, complexidade ou qualidade "
                    "perdida), e o que quebra se o leitor adotar.")
    porque: str = Field(description="Uma linha justificando o veredito de pratica")
```

O prompt:

```python
def build_prompt(paper: Paper) -> str:
    return (
        f"{LEITOR_BRIEF}\n\n"
        f"Paper (arXiv {paper.arxiv_id}):\n"
        f"Titulo: {paper.title}\n"
        f"Resumo: {paper.abstract}\n\n"
        f"Classifique a tecnica numa familia, diga o que o leitor faz com ela, "
        f"e extraia a alegacao de ganho se houver. No resumo diga o que ela "
        f"substitui, o que custa, e o que quebra. "
        f"Escreva em portugues, sem emoji, sem adjetivo promocional."
    )
```

E `_to_domain`:

```python
def _to_domain(schema: JudgmentSchema) -> Judgment:
    return Judgment(
        technique=schema.technique, familia=schema.familia,
        pratica=schema.pratica, ganho_eixo=schema.ganho_eixo,
        ganho_fator=schema.ganho_fator, ganho_texto=schema.ganho_texto,
        resumo=schema.resumo, porque=schema.porque,
        summary=schema.resumo,       # ponte ate a tarefa 7
    )
```

- [ ] **Passo 4: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 225 passed, 5 skipped

- [ ] **Passo 5: propor commit**

```bash
git add src/radar/judge.py tests/test_judge.py
git commit -m "feat: julgador pergunta familia e pratica no lugar de hardware"
```


---

## Bloqueio conhecido: cota da Anthropic até 2026-09-01

A conta bateu o teto de uso em 2026-08-29 — o seed de 1088 papers a consumiu — e
**só volta em 2026-09-01 00:00 UTC**. Verificado com uma chamada real:

```
BadRequestError: 400 — You have reached your specified API usage limits.
You will regain access on 2026-09-01 at 00:00 UTC.  (req_011CeXkpGtoVXDVGYixDabyy)
```

**O que isso trava:** a Tarefa 11 inteira, e o passo de fumaça da Tarefa 5-bis
abaixo. **O que isso não trava:** as Tarefas 1 a 10, que rodam offline contra a
suíte. Execute-as normalmente e pare antes da 11.

---

## Tarefa 5-bis: teste de fumaça do schema contra a API real

**Quando:** depois da Tarefa 5, e **só a partir de 2026-09-01**.
**Arquivos:** nenhum. É verificação, não código.

**Por que existe como tarefa própria.** Este projeto já perdeu dois lotes
inteiros para defeitos que nenhum teste com SDK falseado poderia pegar:

1. `JudgmentSchema` sem `additionalProperties` — a API rejeitou o lote inteiro.
2. `custom_id` com ponto — `400`, o lote inteiro recusado, e os 195 testes
   passando porque todos falseiam o SDK.

O schema novo introduz uma terceira coisa nunca exercitada ao vivo:
**`ganho_fator: float | None`**, que o Pydantic emite como
`{"anyOf": [{"type": "number"}, {"type": "null"}]}`. Se a saída estruturada não
aceitar `anyOf`, **todo lote falha e a Tarefa 11 queima US$ 4 sem gravar nada**.
Foi exatamente esse o risco que o seed correu.

- [ ] **Passo 1: uma chamada, um paper, ao vivo**

```bash
set -a; . ~/.config/secrets/personal.env; set +a
PYTHONPATH=src <python> - <<'EOF'
import anthropic
from radar.judge import Judge
from radar.models import Paper
p = Paper(arxiv_id="2205.14135", title="FlashAttention: Fast and Memory-Efficient "
          "Exact Attention with IO-Awareness",
          abstract="Tiling e recomputacao reduzem leituras e escritas na HBM; "
                   "treina BERT-large 15% mais rapido e GPT-2 3x mais rapido.",
          authors=("Tri Dao",), categories=("cs.LG",), published="2022-05-27")
j = Judge(anthropic.Anthropic(), "claude-opus-5").judge_one(p)
print("familia :", j.familia)
print("pratica :", j.pratica)
print("ganho   :", j.ganho_fator, "em", j.ganho_eixo)
print("texto   :", j.ganho_texto)
print("resumo  :", j.resumo)
EOF
```

- [ ] **Passo 2: julgar o resultado, não só a ausência de erro**

Três coisas precisam estar certas, e a primeira é a que o teste existe para
provar:

1. **A chamada não levantou `BadRequestError`** — o `anyOf` foi aceito.
2. `familia` é um dos 19, e é plausível (`kernels_e_atencao` para o
   FlashAttention).
3. `ganho_fator` é `3.0` ou próximo, e `ganho_eixo` é `velocidade` — o paper
   alega "3x mais rápido" e a extração precisa achar isso.

**Se o passo 1 falhar por schema**, o conserto é trocar `float | None` por
`float` com sentinela documentada (`0.0` = sem alegação) e refazer a validação
da Tarefa 4. **Não prossiga para a Tarefa 11 sem este passo verde** — ela é a
que gasta dinheiro.

- [ ] **Passo 3: um lote de dois, para exercitar o caminho do Batch**

O `judge_one` usa chamada normal; a Tarefa 11 usa o Batch API, que já mostrou
ter validações próprias. Submeta dois papers pelo caminho de lote e confirme que
volta com os dois `custom_id` corretos antes de mandar 1088.

---

## Tarefa 6: `papers.scope` e a tabela `judgments` nova

**Arquivos:** Modificar `src/radar/store.py`. Teste: `tests/test_store.py`.

**Interfaces:**
- Produz: `upsert_paper(paper, seen_at, scope)` — `scope` **obrigatório, sem
  default**; `record_judgment` e `latest_judgment` com os campos novos;
  `papers_por_familia()` para o jornal.
- Consumido por: tarefas 8, 10, 11 e pelo plano do jornal.

**Sem default em `scope`** de propósito: um default deixaria um chamador novo
gravar linha sem escopo em silêncio, e a coluna existe justamente para fatiar o
acervo.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_store.py
import pytest


def test_upsert_exige_escopo_explicito(store, paper):
    # Sem default: um chamador que esquece o escopo tem que quebrar alto,
    # nao gravar linha anonima.
    with pytest.raises(TypeError):
        store.upsert_paper(paper, seen_at="2026-08-29")


def test_o_escopo_gravado_volta_na_leitura(store, paper):
    store.upsert_paper(paper, seen_at="2026-08-29", scope="agentes")
    assert store.all_papers()[0]["scope"] == "agentes"


def test_o_julgamento_guarda_familia_pratica_e_ganho(store, paper, julgamento):
    store.upsert_paper(paper, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(paper.arxiv_id, julgamento, "claude-opus-5", "2026-08-29")
    lido = store.latest_judgment(paper.arxiv_id)
    assert lido.familia == julgamento.familia
    assert lido.pratica == julgamento.pratica
    assert lido.ganho_fator == julgamento.ganho_fator
    assert lido.ganho_texto == julgamento.ganho_texto


def test_ganho_fator_nulo_volta_nulo_e_nao_zero(store, paper, julgamento_sem_ganho):
    store.upsert_paper(paper, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(paper.arxiv_id, julgamento_sem_ganho,
                          "claude-opus-5", "2026-08-29")
    assert store.latest_judgment(paper.arxiv_id).ganho_fator is None


def test_citacao_desconhecida_persiste_como_nula(store, paper):
    from radar.models import ScoreResult, Signal
    store.upsert_paper(paper, seen_at="2026-08-29", scope="inferencia")
    s = Signal(total_impls=1, independent_impls=1, velocity_14d=0,
               stars_total=0, citations=None)
    store.record_signal(paper.arxiv_id, s, ScoreResult(value=1.0, gated_by=None),
                        "2026-08-29")
    assert store.signal_history(paper.arxiv_id)[0]["citations"] is None


def test_papers_por_familia_conta_o_acervo(store, paper, julgamento):
    store.upsert_paper(paper, seen_at="2026-08-29", scope="inferencia")
    store.record_judgment(paper.arxiv_id, julgamento, "claude-opus-5", "2026-08-29")
    assert store.papers_por_familia()[julgamento.familia] == 1
```

**Fixtures novas em `tests/conftest.py`:**

```python
@pytest.fixture
def julgamento():
    from radar.models import Judgment
    return Judgment(technique="t", familia="cache_kv", pratica="testar",
                    ganho_eixo="velocidade", ganho_fator=2.3,
                    ganho_texto="2.3x sobre vLLM", resumo="r", porque="p")


@pytest.fixture
def julgamento_sem_ganho():
    from radar.models import Judgment
    return Judgment(technique="t", familia="outro", pratica="observar",
                    ganho_eixo="nenhum", ganho_fator=None,
                    ganho_texto="", resumo="r", porque="p")
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_store.py -v -k escopo`
Esperado: FAIL — `upsert_paper` ainda aceita dois argumentos.

- [ ] **Passo 3: implementar o esquema**

```sql
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    abstract     TEXT NOT NULL,
    authors      TEXT NOT NULL,
    categories   TEXT NOT NULL,
    published    TEXT NOT NULL,
    first_seen   TEXT NOT NULL,
    last_checked TEXT,
    scope        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS judgments (
    arxiv_id     TEXT NOT NULL REFERENCES papers(arxiv_id),
    judged_at    TEXT NOT NULL,
    model        TEXT NOT NULL,
    technique    TEXT NOT NULL,
    familia      TEXT NOT NULL,
    pratica      TEXT NOT NULL,
    ganho_eixo   TEXT NOT NULL,
    ganho_fator  REAL,              -- NULL e legitimo: nem todo paper alega
    ganho_texto  TEXT NOT NULL,
    resumo       TEXT NOT NULL,
    porque       TEXT NOT NULL,
    PRIMARY KEY (arxiv_id, judged_at)
);
```

`signals.citations` passa a aceitar `NULL` — remova o `NOT NULL` da coluna.

- [ ] **Passo 4: implementar os métodos**

```python
    def upsert_paper(self, paper, seen_at: str, scope: str) -> None:
        ...  # INSERT ... ON CONFLICT preservando first_seen, gravando scope

    def papers_por_familia(self) -> dict[str, int]:
        """Contagem por familia sobre o julgamento mais recente de cada paper."""
        linhas = self._conn.execute("""
            SELECT j.familia, COUNT(*) FROM judgments j
            JOIN (SELECT arxiv_id, MAX(judged_at) m FROM judgments
                  GROUP BY arxiv_id) u
              ON j.arxiv_id = u.arxiv_id AND j.judged_at = u.m
            GROUP BY j.familia
        """)
        return {f: n for f, n in linhas}
```

- [ ] **Passo 5: mutação — provar o contrato store↔leitura**

Renomeie a coluna `familia` para `familia_x` no DDL e nos `INSERT`, deixando o
`SELECT` de `latest_judgment` como está. Rode a suíte: `test_store` deve falhar.
Se passar, o teste não está tocando a coluna e o contrato não está travado.
Restaure. **Este passo existe porque essa exata lacuna já apareceu neste
projeto** — `test_render` passou 11/11 cego enquanto a coluna estava renomeada.

- [ ] **Passo 6: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 231 passed, 5 skipped

- [ ] **Passo 7: propor commit**

```bash
git add src/radar/store.py tests/test_store.py tests/conftest.py
git commit -m "feat: banco guarda escopo, familia, pratica e ganho"
```

---

## Tarefa 7: `render.py` usa `pratica`, e `runs_on_3090` morre

**Arquivos:** Modificar `src/radar/render.py` e `src/radar/models.py`.
Teste: `tests/test_render.py`.

**Interfaces:**
- `Judgment` perde `runs_on_3090`, `rationale` e `summary`, e os campos novos
  perdem o default. Depois desta tarefa, `Judgment` sem `familia` é `TypeError`.

**Esta é a tarefa de limpeza.** As tarefas 4 a 6 deixaram pontes para manter a
suíte verde; aqui elas caem todas de uma vez, e a suíte é a rede.

- [ ] **Passo 1: escrever o teste que falha**

```python
# tests/test_render.py
def test_o_item_mostra_a_pratica_e_nao_o_hardware(item_radar):
    saida = render_markdown("2026-08-29", [item_radar], [], {})
    assert "testar" in saida
    assert "3090" not in saida


def test_o_ganho_alegado_aparece_rotulado_como_alegado(item_radar):
    # O rotulo e inegociavel: numero de abstract apresentado como medicao e
    # exatamente o hype de que este projeto existe para fugir.
    saida = render_markdown("2026-08-29", [item_radar], [], {})
    assert "2.3" in saida
    assert "alegado" in saida.lower()


def test_sem_ganho_nao_ha_rotulo_de_alegacao(item_sem_ganho):
    saida = render_markdown("2026-08-29", [item_sem_ganho], [], {})
    assert "alegado" not in saida.lower()
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_render.py -v -k pratica`
Esperado: FAIL — o render ainda imprime o veredito de hardware.

- [ ] **Passo 3: limpar `Judgment`**

```python
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
```

Remova `VALID_VERDICTS` e a validação de `runs_on_3090` do `__post_init__`.
Remova a ponte `summary=schema.resumo` de `judge.py`.

- [ ] **Passo 4: ajustar o render**

Onde o item imprimia o veredito de hardware, passa a imprimir `pratica` e, se
`ganho_fator` não for nulo, o ganho com o rótulo:

```python
if item.judgment.ganho_fator is not None:
    linhas.append(
        f"  ganho {item.judgment.ganho_fator:g}x em "
        f"{item.judgment.ganho_eixo} — alegado pelos autores, nao verificado"
    )
```

- [ ] **Passo 5: mutação — provar que o rótulo está travado**

Apague ` — alegado pelos autores, nao verificado` da f-string. Rode
`pytest tests/test_render.py -k rotulado`. Deve **falhar**. Restaure.

- [ ] **Passo 6: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 234 passed, 5 skipped. Todo construtor de `Judgment` em `src` e
`tests` precisa ter sido migrado — é esta rodada que prova.

- [ ] **Passo 7: propor commit**

```bash
git add src/radar/models.py src/radar/render.py src/radar/judge.py tests/
git commit -m "feat: markdown mostra pratica e ganho rotulado; sai o hardware"
```

---
## Tarefa 8: escopo e citações no pipeline

**Arquivos:** Modificar `src/radar/pipeline.py` e `src/radar/github.py`.
Teste: `tests/test_pipeline.py`.

**Interfaces:**
- `run_day` ganha `fetch_citations: Callable[[list[str]], dict[str, int | None]] | None = None`.
  Default `None` mantém todo teste existente válido.
- `GitHubClient.signal_with_repos(paper, today)` **perde** o parâmetro
  `citations`, e `signal_for` idem.

**A decisão de desenho:** o GitHub não sabe de citação e nunca soube — o
parâmetro `citations: int = 0` existia com default e nenhum chamador jamais
passou outro valor. Em vez de fazê-lo carregar dado alheio, o `run_day` compõe:
busca as citações uma vez para todos os ids descobertos, e sobrescreve o campo
no `Signal` com `dataclasses.replace`. GitHub mede GitHub, OpenAlex mede
citação, o pipeline junta.

**Uma requisição por execução**, não uma por paper: 40 ids cabem num lote de 50.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_pipeline.py
def test_o_escopo_do_run_chega_ao_banco(store, escopo_falso):
    r = run_day(store=store, scope=escopo_falso, ...)
    assert store.all_papers()[0]["scope"] == escopo_falso.name


def test_as_citacoes_sao_buscadas_uma_vez_so_para_todos(store, escopo_falso):
    chamadas = []
    def buscar(ids):
        chamadas.append(list(ids))
        return {i: 5 for i in ids}
    run_day(..., fetch_citations=buscar)
    assert len(chamadas) == 1
    assert len(chamadas[0]) == 3      # os tres papers descobertos


def test_a_citacao_buscada_entra_no_sinal_gravado(store, escopo_falso):
    run_day(..., fetch_citations=lambda ids: {i: 42 for i in ids})
    assert store.signal_history(PAPER_ID)[0]["citations"] == 42


def test_sem_buscador_de_citacao_o_sinal_fica_desconhecido(store, escopo_falso):
    # Nao zero: nao perguntamos.
    run_day(..., fetch_citations=None)
    assert store.signal_history(PAPER_ID)[0]["citations"] is None


def test_paper_ausente_no_openalex_fica_desconhecido_e_nao_zerado(store, escopo_falso):
    run_day(..., fetch_citations=lambda ids: {ids[0]: 3})   # so o primeiro
    historia = {p["arxiv_id"]: p for p in store.all_signals()}
    assert historia[OUTRO_ID]["citations"] is None


def test_um_paper_ja_no_banco_pelo_outro_escopo_nao_e_redescoberto(store, escopo_falso):
    # Primeiro escopo grava; segundo escopo o encontra e corta por ja_conhecido.
    run_day(store=store, scope=ESCOPO_A, ...)
    r = run_day(store=store, scope=ESCOPO_B, ...)   # mesma descoberta
    assert r.cuts["ja_conhecido"] == 3
    assert store.all_papers()[0]["scope"] == ESCOPO_A.name
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_pipeline.py -v -k citac`
Esperado: FAIL — `run_day() got an unexpected keyword argument 'fetch_citations'`

- [ ] **Passo 3: limpar `github.py`**

```python
    def signal_with_repos(
        self, paper: Paper, today: date
    ) -> tuple[Signal, list[RepoClassification]]:
        ...
        signal = Signal(
            total_impls=len(repos),
            independent_impls=sum(1 for c in classifications if not c.is_author),
            velocity_14d=velocity,
            stars_total=sum(r.stars for r in repos),
        )                       # citations fica None: o GitHub nao sabe disso
        return signal, classifications

    def signal_for(self, paper: Paper, today: date) -> Signal:
        return self.signal_with_repos(paper, today)[0]
```

- [ ] **Passo 4: implementar no pipeline**

Depois da descoberta e do filtro de `known_ids`, antes do laço de sinal:

```python
    # Uma requisicao para o dia inteiro: 40 ids cabem no lote de 50 do OpenAlex.
    # Sem buscador, todo mundo fica desconhecido -- que e diferente de zero e
    # e a unica resposta honesta quando nao se perguntou.
    citacoes: dict[str, int | None] = {}
    if fetch_citations is not None:
        citacoes = fetch_citations([p.arxiv_id for p, _, _ in trabalho])
```

E dentro do laço, logo após `fetch_signal`:

```python
        signal = replace(signal, citations=citacoes.get(paper.arxiv_id))
```

E `upsert_paper` passa a receber o escopo:

```python
        store.upsert_paper(paper, seen_at=day, scope=scope.name)
```

- [ ] **Passo 5: mutação — provar que desconhecido não vira zero**

Troque `citacoes.get(paper.arxiv_id)` por `citacoes.get(paper.arxiv_id, 0)`.
Rode `pytest tests/test_pipeline.py -k ausente_no_openalex`. Deve **falhar**.
Restaure.

- [ ] **Passo 6: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 240 passed, 5 skipped

- [ ] **Passo 7: propor commit**

```bash
git add src/radar/pipeline.py src/radar/github.py tests/test_pipeline.py
git commit -m "feat: pipeline grava escopo e compoe citacao do OpenAlex"
```

---

## Tarefa 9: `compose_day`

**Arquivos:** Modificar `src/radar/render.py`. Teste: `tests/test_render.py`.

**Interfaces:**
- Produz: `compose_day(day: str, por_escopo: dict[str, DayResult]) -> str`
- Consumido por: tarefa 10.

**`render_markdown` não é reaberta.** Ela é a função mais coberta do projeto e o
custo de mexer nela é maior que o de compor por cima. `compose_day` chama o
markdown já pronto de cada `DayResult` e costura.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_render.py
def test_a_composicao_traz_as_duas_secoes_na_ordem(res_inferencia, res_agentes):
    saida = compose_day("2026-08-29",
                        {"inferencia": res_inferencia, "agentes": res_agentes})
    assert saida.index("Inferência") < saida.index("Agentes")


def test_escopo_com_radar_vazio_ainda_aparece(res_inferencia, res_vazio):
    # Um escopo silencioso e informacao: sumir com a secao faria parecer que
    # o escopo nao rodou.
    saida = compose_day("2026-08-29",
                        {"inferencia": res_inferencia, "agentes": res_vazio})
    assert "Agentes" in saida


def test_a_composicao_nao_perde_corte_de_nenhum_escopo(res_inferencia, res_agentes):
    saida = compose_day("2026-08-29",
                        {"inferencia": res_inferencia, "agentes": res_agentes})
    for motivo in ("abaixo_do_piso", "ja_conhecido"):
        assert motivo in saida


def test_o_cabecalho_do_dia_aparece_uma_vez_so(res_inferencia, res_agentes):
    saida = compose_day("2026-08-29",
                        {"inferencia": res_inferencia, "agentes": res_agentes})
    assert saida.count("# Radar — 2026-08-29") == 1
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_render.py -v -k composicao`
Esperado: FAIL com `ImportError: cannot import name 'compose_day'`

- [ ] **Passo 3: implementar**

```python
ROTULO = {"inferencia": "Inferência", "agentes": "Agentes"}
ORDEM = ("inferencia", "agentes")


def compose_day(day: str, por_escopo: dict[str, DayResult]) -> str:
    """Costura o markdown de cada escopo num arquivo unico do dia.

    Nao reabre `render_markdown`: cada DayResult ja traz o seu markdown
    pronto e testado. Aqui so se remove o cabecalho duplicado e se rotula
    a secao.
    """
    out = [f"# Radar — {day}", ""]
    for nome in ORDEM:
        r = por_escopo.get(nome)
        if r is None:
            continue
        out.append(f"## {ROTULO[nome]}")
        out.append("")
        corpo = r.markdown.split("\n")
        # A primeira linha de cada markdown e o cabecalho `# Radar — <dia>`;
        # ele vira uma vez so, no topo do arquivo composto.
        if corpo and corpo[0].startswith("# Radar"):
            corpo = corpo[1:]
        out.extend(corpo)
        out.append("")
    return "\n".join(out)
```

- [ ] **Passo 4: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 244 passed, 5 skipped

- [ ] **Passo 5: propor commit**

```bash
git add src/radar/render.py tests/test_render.py
git commit -m "feat: compoe o markdown do dia a partir dos dois escopos"
```

---

## Tarefa 10: a CLI roda os dois escopos

**Arquivos:** Modificar `src/radar/cli.py`. Teste: `tests/test_cli.py`.

**Interfaces:** Consome `AGENT_SCOPE` (1), `OpenAlexClient` (3),
`fetch_citations` (8), `compose_day` (9).

**A ordem importa e é decisão travada:** `inferencia` primeiro, `agentes`
depois. O primeiro escopo a descobrir um paper fica com ele; o segundo o corta
por `ja_conhecido`.

**A re-consulta roda uma vez só**, na primeira passada, com o limite global.
Ela opera sobre `papers` inteira e não conhece escopo — passar `recheck_limit`
nas duas execuções re-consultaria o dobro do orçamento.

- [ ] **Passo 1: escrever os testes que falham**

```python
# tests/test_cli.py
def test_a_cli_roda_os_dois_escopos_na_ordem(monkeypatch, tmp_path):
    vistos = []
    def falso_run_day(*, scope, recheck_limit, **kw):
        vistos.append((scope.name, recheck_limit))
        return DayResult(radar=[], feed=[], cuts={}, markdown="# Radar — x",
                         push="")
    monkeypatch.setattr("radar.cli.run_day", falso_run_day)
    _executar(args, db_path, today)
    assert [n for n, _ in vistos] == ["inferencia", "agentes"]


def test_a_reconsulta_roda_uma_vez_so(monkeypatch, tmp_path):
    # Passar o orcamento nas duas execucoes re-consultaria o dobro.
    ...
    assert [r for _, r in vistos] == [RECHECK_LIMIT, 0]


def test_o_arquivo_do_dia_e_um_so(tmp_path):
    # Dois escopos, um arquivo: `radar/<dia>.md`.
    ...
    assert len(list((tmp_path / "radar").glob("*.md"))) == 1


def test_o_push_concatena_os_dois_radares(monkeypatch):
    ...
    assert "inferencia-1" in enviado and "agentes-1" in enviado
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_cli.py -v -k dois_escopos`
Esperado: FAIL — a CLI chama `run_day` uma vez.

- [ ] **Passo 3: implementar**

Em `_executar`, o transporte do OpenAlex:

```python
def _openalex_fetch(url: str) -> dict:
    r = httpx.get(url, headers={"User-Agent": OPENALEX_UA}, timeout=30.0)
    r.raise_for_status()
    return r.json()
```

E o laço:

```python
    openalex = OpenAlexClient(fetch=_openalex_fetch)
    resultados: dict[str, DayResult] = {}

    for i, escopo in enumerate((DEFAULT_SCOPE, AGENT_SCOPE)):
        resultados[escopo.name] = run_day(
            store=store, scope=escopo, thresholds=limiares, today=hoje,
            model=modelo, fetch_papers=arxiv.recent,
            fetch_signal=fetch_signal, judge_all=judge_all,
            fetch_citations=openalex.citations_for,
            dry_run=args.dry_run,
            # A re-consulta e global e roda uma vez so: ela varre `papers`
            # inteira e nao conhece escopo. Ligar nas duas passadas gastaria
            # o dobro do orcamento re-consultando os mesmos papers.
            recheck_limit=load_recheck_limit() if i == 0 else 0,
        )

    markdown = compose_day(hoje.isoformat(), resultados)
    push = "\n\n".join(r.push for r in resultados.values() if r.push)
```

- [ ] **Passo 4: rodar a suíte inteira**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 248 passed, 5 skipped

- [ ] **Passo 5: ensaio a seco de verdade**

```bash
set -a; . ~/.config/secrets/personal.env; set +a
export GH_TOKEN="$(gh auth token)"
PYTHONPATH=src <python> -m radar.cli --dry-run
```

Confira, sem gravar nada: os dois escopos aparecem, o segundo tem cortes por
`ja_conhecido`, e a contagem de papers bate com a ordem de grandeza medida
(~15 e ~25). **Anote quantos papers de agentes foram cortados por
`ja_conhecido`** — é a medição de sobreposição que a spec §7 pede.

- [ ] **Passo 6: propor commit**

```bash
git add src/radar/cli.py tests/test_cli.py
git commit -m "feat: CLI roda inferencia e agentes numa execucao"
```

---

## Tarefa 11: migração, re-julgamento e o gate de aceite

**Arquivos:** Criar `scripts/migrar_e_rejulgar.py`. Sem teste automatizado —
é operação pontual, e o gate do passo 5 é a verificação.

**Esta tarefa gasta dinheiro real (~US$ 4) e destrói dados.** Ela é a única do
plano com pré-condição obrigatória.

**PRÉ-CONDIÇÃO:** a Tarefa 5-bis precisa ter passado. Ela custa uma chamada;
esta custa US$ 4 e destrói dados.

- [ ] **Passo 1: copiar o banco, e provar a cópia**

```bash
cp data/radar.db "data/radar.db.bak-$(date +%Y%m%d-%H%M%S)"
ls -la data/*.bak-*
<python> -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); \
print('papers:', c.execute('select count(*) from papers').fetchone()[0])" \
  data/radar.db.bak-*
```

Esperado: `papers: 1088`. **Sem essa saída, não prossiga** — a migração é
irreversível e a cópia é a única volta.

- [ ] **Passo 2: migrar o esquema**

O script reconstrói `judgments` com a forma nova, **descarta as linhas antigas**
(elas carregam `runs_on_3090`, que deixou de existir, e serão substituídas
dentro da hora), preenche `papers.scope = 'inferencia'` nas 1088 linhas — foi
de `DEFAULT_SCOPE` que vieram — e afrouxa `signals.citations` para aceitar
`NULL`.

`papers`, `signals`, `repos` e `deliveries` **não são tocadas**: são o ativo
caro.

- [ ] **Passo 3: verificar que só `judgments` mudou**

```bash
<python> - <<'EOF'
import sqlite3
n = sqlite3.connect('data/radar.db')
v = sqlite3.connect([p for p in __import__('glob').glob('data/*.bak-*')][0])
for t in ('papers','signals','repos','deliveries'):
    a = v.execute(f'select count(*) from {t}').fetchone()[0]
    b = n.execute(f'select count(*) from {t}').fetchone()[0]
    print(f'{t}: antes {a} depois {b} {"OK" if a==b else "!!! DIVERGIU"}')
print('judgments:', n.execute('select count(*) from judgments').fetchone()[0], '(esperado 0)')
EOF
```

- [ ] **Passo 4: re-julgar os 1088**

Mesmo molde do `seed.py` que rodou em 2026-08-29: lê os papers do banco, submete
um lote, grava. **Não** toca em arXiv nem em GitHub, e não gasta rate limit.

O prazo do lote precisa ser explícito e longo:

```python
PRAZO_LOTE = 4 * 60 * 60   # BATCH_TIMEOUT_SECONDS e 45min, orcamento de cron
                           # diario. Um lote de 1088 pode passar disso, e um
                           # lote que estoura devolve {} -- lote pago, nada
                           # gravado. Foi o risco que o seed correu.
```

Roda em segundo plano; o lote em si leva poucos minutos (no seed, 60 dos 64
minutos foram GitHub, que aqui não roda).

- [ ] **Passo 5: O GATE — medir a distribuição**

```bash
<python> - <<'EOF'
import sqlite3
c = sqlite3.connect('data/radar.db'); c.row_factory = sqlite3.Row
tot = c.execute('select count(*) from judgments').fetchone()[0]
print(f'julgamentos: {tot}\n')
for campo, teto in (('pratica', 0.45), ('familia', None)):
    print(f'--- {campo} ---')
    for r in c.execute(f'select {campo} v, count(*) q from judgments '
                       f'group by 1 order by q desc'):
        pct = r['q'] / tot
        marca = ''
        if campo == 'pratica' and pct > 0.45:   marca = '  <<< REPROVA (>45%)'
        if campo == 'familia' and r['v'] == 'outro' and pct > 0.10:
            marca = '  <<< REPROVA (outro >10%)'
        print(f"  {r['v']:32} {r['q']:>5}  {pct:6.1%}{marca}")
cob = c.execute("select count(*) from judgments where ganho_eixo != 'nenhum'").fetchone()[0]
print(f"\ncobertura de ganho: {cob}/{tot} = {cob/tot:.1%}"
      f"{'  <<< REPROVA (<35%)' if cob/tot < 0.35 else ''}")
EOF
```

**Os três gates da spec §7:**

| gate | limite | se reprovar |
|---|---|---|
| valor modal de `pratica` | ≤ 45% | o eixo não discrimina; volta à prancheta |
| `outro` | ≤ 10% | faltam famílias; leia o que caiu em `outro` |
| cobertura de ganho | ≥ 35% | a seção de avanço **sai** do jornal |

**Se `pratica` reprovar, o plano do jornal não começa.** Trocar um eixo inútil
(`runs_on_3090`, 52%) por outro eixo inútil seria o pior resultado possível
desta obra, e a tela construída em cima disso herdaria o defeito.

- [ ] **Passo 6: propor commit**

```bash
git add scripts/migrar_e_rejulgar.py
git commit -m "chore: script de migracao e re-julgamento do acervo"
```

---

## Auto-revisão do plano

**Cobertura da spec.** §2 (escopo medido) → Tarefa 1. §3 (coluna, execução,
mesclagem) → Tarefas 6, 8, 9, 10. §4 (schema novo) → Tarefas 4 e 5. §4.1
(famílias) → Tarefa 4. §4.2 (prática) → Tarefas 4, 5, 7. §4.3 (resumo) →
Tarefa 5. §4.4 (ganho) → Tarefas 4, 5, 7. §4-bis (OpenAlex) → Tarefas 2, 3, 8.
§5 (migração) → Tarefa 11. §6 (orçamento) → verificado no ensaio da Tarefa 10.
§7 (gates) → Tarefa 11 passo 5. §8 (testes) → todos presentes: teste 1 e 2 na
Tarefa 8, 3 na 4, 4 na 9, 5 na 10, 6 na 11 passo 3, 7 e 8 na 4, 9 na 6.

**Consistência de tipos.** `ScopeConfig.name` nasce na Tarefa 1 e é consumido
como `scope.name` nas 8 e 10. `Signal.citations: int | None` nasce na 2 e é
respeitado na 3, 6 e 8. `Judgment` ganha campos com default na 4, os
consumidores migram nas 5, 6 e 7, e os defaults caem na 7 — depois disso todo
construtor precisa passar tudo, e a suíte inteira é quem prova.
`fetch_citations` tem default `None` na 8, então nenhum teste existente ganha
busca de citação sem pedir; quem liga é a CLI na 10, explicitamente.

**A ponte que precisa ser desmontada.** A Tarefa 5 grava `summary=schema.resumo`
em `_to_domain` só para manter a suíte verde enquanto o render ainda lê
`summary`. A Tarefa 7 passo 3 remove essa linha. **Se ela sobreviver, dois
campos guardam o mesmo texto para sempre** — é a dívida mais provável deste
plano e está marcada nos dois lugares.

**Uma escolha que vale registrar.** A Tarefa 8 remove `citations` de
`github.py` em vez de fazê-lo repassar o valor. O parâmetro estava lá com
default `0` desde o dia um e nenhum chamador jamais passou outro valor — ele é
a origem do defeito, não a solução dele.

## Ordem de execução

Estritamente 1 → 5 → **5-bis** → 6 → 11. As dependências são reais: 6 precisa
de 1, 8 precisa de 3 e 6, 10 precisa de tudo, e 11 precisa do esquema já migrado
no código.

**5-bis e 11 estão bloqueadas até 2026-09-01** pela cota da conta. Tudo o mais
roda offline. Se a data ainda não chegou, execute 1 a 10, pare, e retome em 5-bis.

**A tarefa 11 é a única com efeito irreversível e custo em dinheiro.** Ela não
pode ser antecipada, e o gate do passo 5 é o portão para o plano do jornal.
