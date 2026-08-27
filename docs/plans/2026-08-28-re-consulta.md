# Re-consulta de Sinal — Plano de Implementação

> **Para executores agênticos:** SUB-SKILL OBRIGATÓRIA: usar `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans`. Os passos usam checkbox (`- [ ]`).

**Objetivo:** ligar a re-consulta diária de sinal, para que papers já no banco acumulem uma segunda observação e a detecção de ressurreição — o argumento inteiro do desenho append-only de `signals` — deixe de estar dormente.

**Arquitetura:** em vez de um segundo laço paralelo, o `run_day` passa a montar uma **lista de trabalho** de `(paper, judgment, is_new)` e iterar uma vez só. Papers novos entram com o julgamento vindo do LLM; re-consultados entram com o julgamento **lido do banco**. O flag `is_new` controla três coisas e só três: o motivo de corte quando falta julgamento, quais gravações acontecem, e se o item pode chegar ao feed.

**Stack:** Python 3.12, sqlite3, pytest. Nenhuma dependência nova.

**Spec:** `docs/2026-08-28-re-consulta-spec.md` (emenda a `docs/2026-08-27-radar-spec.md` §6 e §4)

---

## Restrições globais

**Sem trailer de co-autoria** em nenhum commit. Commits em `feat/radar-pipeline` estão pré-autorizados; **nada de remote, push ou criação de repositório**. Mensagens em português, imperativo, sem emoji.

**Nenhum paper é entregue duas vezes.** Sem exceção, nem para ressurreição. A guarda `was_delivered` já existe no laço e passa a ser o único obstáculo entre um paper antigo e uma segunda entrega — é agora que ela ganha função de verdade.

**Re-consulta não gasta token.** Julgamento é lido do banco, nunca re-gerado. Se algum caminho chamar `judge_all` com paper re-consultado, o plano falhou.

**Re-consultado nunca entra no feed.** O feed responde "o que saiu hoje".

**Nada de truncamento silencioso.** Todo corte contado com motivo, e a seção `## Re-consulta` aparece mesmo quando nada se moveu.

**Testes rodam sem rede.** A suíte atual tem 161 testes; nenhum pode quebrar.

**Ambiente:** `/Users/luskoliveira/.pyenv/versions/3.12.3/bin/python`, testes com `PYTHONPATH=src ... -m pytest`. Não rodar `pip install`. Se um teste falhar de forma inexplicável após editar fonte, limpar `__pycache__` e `.pytest_cache`.

---

## Estrutura de arquivos

| Arquivo | Mudança |
|---|---|
| `src/radar/store.py` | ganha `papers_to_recheck(limit) -> list[Paper]` |
| `src/radar/config.py` | ganha `RECHECK_LIMIT` e `load_recheck_limit()` |
| `src/radar/pipeline.py` | laço passa a iterar lista de trabalho; re-consulta entra nela |
| `src/radar/render.py` | ganha a seção `## Re-consulta` |
| `src/radar/cli.py` | passa o limite adiante |

Nenhum arquivo novo. `scoring.py`, `authorship.py`, `arxiv.py`, `github.py`, `judge.py` e `telegram.py` não são tocados.

---

## Tarefa 1: `Store.papers_to_recheck`

**Arquivos:** Modificar `src/radar/store.py`. Teste: `tests/test_store.py`.

**Interfaces:**
- Consome: `stalest_papers(limit)`, que já existe e ordena nunca-checados primeiro, depois mais antigos.
- Produz: `papers_to_recheck(limit: int) -> list[Paper]` — objetos `Paper` reconstruídos, não linhas de banco.

**Por que devolver `Paper` e não a linha:** `authors` e `categories` estão gravados como JSON. Quem decodifica deve ser quem codificou. Deixar `json.loads` vazar para o pipeline espalharia conhecimento do formato de armazenamento por dois módulos.

- [ ] **Passo 1: Escrever os testes que falham**

Em `tests/test_store.py`:

```python
def test_papers_to_recheck_returns_paper_objects(store):
    """Quem codificou o JSON e quem decodifica. O pipeline nao deve saber
    que authors e categories viajam serializados."""
    store.upsert_paper(P, seen_at="2026-08-27")
    papers = store.papers_to_recheck(limit=10)
    assert len(papers) == 1
    assert isinstance(papers[0], Paper)
    assert papers[0].arxiv_id == P.arxiv_id


def test_papers_to_recheck_round_trips_sequences_as_tuples(store):
    store.upsert_paper(P, seen_at="2026-08-27")
    recuperado = store.papers_to_recheck(limit=10)[0]
    assert recuperado.authors == P.authors
    assert recuperado.categories == P.categories
    assert isinstance(recuperado.authors, tuple)


def test_papers_to_recheck_puts_never_checked_first(store):
    velho = Paper(arxiv_id="2508.00001", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01")
    nunca = Paper(arxiv_id="2508.00002", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01")
    store.upsert_paper(velho, seen_at="2026-08-01")
    store.touch_checked(velho.arxiv_id, at="2026-08-01")
    store.upsert_paper(nunca, seen_at="2026-08-01")
    assert [p.arxiv_id for p in store.papers_to_recheck(limit=10)] == \
        ["2508.00002", "2508.00001"]


def test_papers_to_recheck_respects_the_limit(store):
    for i in range(5):
        store.upsert_paper(
            Paper(arxiv_id=f"2508.0000{i}", title="T", abstract="A", authors=[],
                  categories=["cs.LG"], published="2026-08-01"), seen_at="2026-08-01")
    assert len(store.papers_to_recheck(limit=3)) == 3


def test_papers_to_recheck_is_empty_on_a_fresh_database(store):
    assert store.papers_to_recheck(limit=10) == []
```

- [ ] **Passo 2: Rodar e confirmar que falham**

`PYTHONPATH=src python -m pytest tests/test_store.py -v` → FAIL com `AttributeError: 'Store' object has no attribute 'papers_to_recheck'`

- [ ] **Passo 3: Implementar**

Em `src/radar/store.py`, logo depois de `stalest_papers`:

```python
    def papers_to_recheck(self, limit: int) -> list[Paper]:
        """Os papers da vez na rotacao de re-consulta, ja como objetos.

        `authors` e `categories` viajam como JSON nesta tabela; quem codificou
        e quem decodifica. Devolver linhas cruas espalharia conhecimento do
        formato de armazenamento para o pipeline.
        """
        return [
            Paper(
                arxiv_id=row["arxiv_id"],
                title=row["title"],
                abstract=row["abstract"],
                authors=json.loads(row["authors"]),
                categories=json.loads(row["categories"]),
                published=row["published"],
            )
            for row in self.stalest_papers(limit)
        ]
```

E acrescentar `Paper` ao import do topo:

```python
from .models import Judgment, Paper, RepoClassification, Signal
```

- [ ] **Passo 4: Rodar e confirmar que passam**

`PYTHONPATH=src python -m pytest tests/test_store.py -v` → 5 testes novos passam; a suíte inteira segue verde (166).

- [ ] **Passo 5: Commit**

```bash
git add src/radar/store.py tests/test_store.py
git commit -m "feat: papers_to_recheck devolve Paper, nao linha de banco"
```

---

## Tarefa 2: O limite de re-consulta

**Arquivos:** Modificar `src/radar/config.py`. Teste: `tests/test_config.py`.

**Interfaces:**
- Produz: `RECHECK_LIMIT = 30` e `load_recheck_limit() -> int`.

**Nota:** ao contrário de `PUSH_CAP`, este limite **é** configurável por ambiente. `PUSH_CAP` é decisão de produto sobre legibilidade do digest; este é orçamento operacional, que muda com o tamanho do banco e com a presença de `GH_TOKEN`.

- [ ] **Passo 1: Escrever os testes que falham**

```python
def test_recheck_limit_defaults_to_thirty(monkeypatch):
    monkeypatch.delenv("RADAR_RECHECK_LIMIT", raising=False)
    from radar.config import load_recheck_limit
    assert load_recheck_limit() == 30


def test_recheck_limit_is_configurable_unlike_the_push_cap(monkeypatch):
    """PUSH_CAP e decisao de produto e nao se mexe por ambiente. Este e
    orcamento operacional: muda com o tamanho do banco e com GH_TOKEN."""
    monkeypatch.setenv("RADAR_RECHECK_LIMIT", "5")
    from radar.config import load_recheck_limit
    assert load_recheck_limit() == 5
```

- [ ] **Passo 2: Rodar e confirmar que falham**

Esperado: `ImportError: cannot import name 'load_recheck_limit'`

- [ ] **Passo 3: Implementar**

Em `src/radar/config.py`:

```python
RECHECK_LIMIT = 30   # papers re-consultados por dia; ver spec da re-consulta, secao 6
```

e, junto das outras funções de carga:

```python
def load_recheck_limit() -> int:
    # Configuravel, ao contrario de PUSH_CAP: aquele e decisao de produto sobre
    # legibilidade do digest; este e orcamento operacional, que muda com o
    # tamanho do banco e com a presenca de GH_TOKEN.
    return _env_int("RADAR_RECHECK_LIMIT", RECHECK_LIMIT)
```

- [ ] **Passo 4: Rodar e confirmar que passam** — 168 na suíte.

- [ ] **Passo 5: Commit**

```bash
git add src/radar/config.py tests/test_config.py
git commit -m "feat: limite de re-consulta configuravel por ambiente"
```

---

## Tarefa 3: Laço sobre lista de trabalho (refatoração sem mudança de comportamento)

**Arquivos:** Modificar `src/radar/pipeline.py`. Sem teste novo.

**Interfaces:** nenhuma mudança externa. `run_day` mantém assinatura e retorno.

**O ponto desta tarefa:** transformar o laço `for paper in papers:` num laço sobre uma lista de trabalho de tuplas `(paper, judgment, is_new)`, com `is_new` sempre `True`. **Nenhum comportamento muda.** Os 168 testes atuais são a especificação: se algum quebrar, a refatoração está errada.

Fazer isso separado de acrescentar a re-consulta é deliberado — deixa um estado intermediário verificável, e o revisor consegue julgar a reestruturação sem ela estar misturada com feature nova.

- [ ] **Passo 1: Rodar a suíte e anotar o número**

`PYTHONPATH=src python -m pytest tests/ -q` → 168 passed. Este é o alvo a preservar.

- [ ] **Passo 2: Reestruturar**

Substituir, em `run_day`:

```python
    judgments = judge_all(papers) if papers else {}
    candidates: list[tuple[RadarItem, bool]] = []   # (item, elegivel_para_push)
    repos_by_paper: dict[str, list[dict]] = {}

    for paper in papers:
        judgment = judgments.get(paper.arxiv_id)
        if judgment is None:
            cuts["sem_julgamento"] += 1
            continue
```

por:

```python
    judgments = judge_all(papers) if papers else {}

    # Lista de trabalho: (paper, julgamento, e_novo). Papers novos trazem o
    # julgamento do LLM; re-consultados trarao o julgamento lido do banco.
    # `e_novo` controla tres coisas e so tres: o motivo de corte quando falta
    # julgamento, quais gravacoes acontecem, e se o item pode chegar ao feed.
    trabalho: list[tuple[Paper, Judgment | None, bool]] = [
        (p, judgments.get(p.arxiv_id), True) for p in papers
    ]

    candidates: list[tuple[RadarItem, bool, bool]] = []   # (item, elegivel, e_novo)
    repos_by_paper: dict[str, list[dict]] = {}

    for paper, judgment, e_novo in trabalho:
        if judgment is None:
            cuts["sem_julgamento" if e_novo else "reconsulta_sem_julgamento"] += 1
            continue
```

Dentro do laço, trocar as gravações incondicionais por gravações que respeitam `e_novo`:

```python
        result = evaluate(signal, thresholds)

        if e_novo:
            store.upsert_paper(paper, seen_at=day)
            store.record_judgment(paper.arxiv_id, judgment, model=model, judged_at=day)
        store.record_signal(paper.arxiv_id, signal, score=result.value, checked_at=day)
        store.record_repos(paper.arxiv_id, classifications)
        store.touch_checked(paper.arxiv_id, at=day)
        repos_by_paper[paper.arxiv_id] = store.repos_for(paper.arxiv_id)
```

E trocar cada `candidates.append((item, False))` por `candidates.append((item, False, e_novo))`, e o `candidates.append((item, True))` por `candidates.append((item, True, e_novo))`.

Por fim, ajustar as duas comprehensions do final:

```python
    eligible = sorted(
        (i for i, ok, _ in candidates if ok),
        key=lambda i: (i.judgment.runs_on_3090 != "nao", i.score),
        reverse=True,
    )
    radar = eligible[:PUSH_CAP]

    # Spec da re-consulta, secao 4: re-consultado entra no radar, nunca no
    # feed. O feed responde "o que saiu hoje", e um paper de 2022 nao saiu
    # hoje. Restricao do codigo, nao consequencia acidental.
    feed = [item for item, _, e_novo in candidates if e_novo and item not in radar]
```

E a guarda de falha de sinal também precisa do motivo distinto:

```python
        except Exception:
            cuts["sinal_indisponivel"] += 1
            if not e_novo:
                # A rotacao precisa avancar mesmo quando a busca falha, ou
                # `stalest_papers` devolve os mesmos trinta para sempre.
                store.touch_checked(paper.arxiv_id, at=day)
            continue
```

- [ ] **Passo 3: Rodar a suíte inteira**

`PYTHONPATH=src python -m pytest tests/ -q` → **168 passed**, exatamente como antes. Se qualquer teste falhar, a refatoração mudou comportamento e está errada.

- [ ] **Passo 4: Commit**

```bash
git add src/radar/pipeline.py
git commit -m "refactor: laco do run_day itera lista de trabalho

Sem mudanca de comportamento; os 168 testes existentes sao a especificacao.
Prepara a re-consulta, que entra como mais itens na mesma lista em vez de
um segundo laco paralelo."
```

---

## Tarefa 4: A re-consulta entra na lista de trabalho

**Arquivos:** Modificar `src/radar/pipeline.py`. Teste: `tests/test_pipeline.py`.

**Interfaces:**
- Consome: `store.papers_to_recheck(limit)` da Tarefa 1, `store.latest_judgment(arxiv_id)` que já existe.
- Produz: `run_day(..., recheck_limit: int = 0)`. Default **zero** — chamador que não pede re-consulta não ganha nenhuma, e os testes existentes seguem inalterados.

- [ ] **Passo 1: Escrever os testes que falham**

Em `tests/test_pipeline.py`:

```python
def test_a_rechecked_paper_can_reach_the_radar_with_delta_wording(store):
    """O caso que a feature existe para pegar: paper guardado, nunca entregue
    porque o sinal era fraco, volta quando o sinal cresce."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 300), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment("GPTQ"), model="m", judged_at="2026-08-01")

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 340, vel=7), []),
        judge_all=lambda ps: {},
        recheck_limit=10,
    )
    assert [i.paper.arxiv_id for i in result.radar] == ["2210.17323"]
    assert result.radar[0].delta is not None
    assert "2 -> 9 impls independentes" in result.push


def test_a_rechecked_paper_never_reaches_the_feed(store):
    """O feed responde 'o que saiu hoje'. Um paper de 2022 nao saiu hoje."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 300), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    store.mark_delivered(p.arxiv_id, channel="telegram", at="2026-08-01", rank=1)

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 340), []),
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.feed == []
    assert result.cuts["ja_entregue"] == 1


def test_an_already_delivered_paper_never_comes_back(store):
    """Spec secao 6, sem excecao: nenhum paper e entregue duas vezes."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 300), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    store.mark_delivered(p.arxiv_id, channel="telegram", at="2026-08-01", rank=1)

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(99, 10), []),   # sinal enorme
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.radar == []
    assert result.push == ""


def test_recheck_reuses_the_stored_judgment_and_never_calls_the_llm(store):
    """Re-consulta nao gasta token. Re-julgar trinta papers por dia
    multiplicaria a conta para produzir texto que ja esta no banco."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_signal(p.arxiv_id, fake_signal(2, 30), score=0.11, checked_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment("Tecnica Guardada"), model="m",
                          judged_at="2026-08-01")

    julgados = []
    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 40), []),
        judge_all=lambda ps: julgados.extend(ps) or {}, recheck_limit=10,
    )
    assert julgados == []                                   # o LLM nao foi chamado
    assert result.radar[0].judgment.technique == "Tecnica Guardada"


def test_a_rechecked_paper_without_a_stored_judgment_is_cut_distinctly(store):
    """Motivo distinto do `sem_julgamento` dos novos: la o LLM falhou, aqui e
    linha antiga sem julgamento. Causas e consertos diferentes."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")     # sem record_judgment

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (fake_signal(9, 40), []),
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.cuts["reconsulta_sem_julgamento"] == 1
    assert "sem_julgamento" not in result.cuts


def test_recheck_respects_the_limit(store):
    for i in range(5):
        pp = paper(f"2508.0000{i}")
        store.upsert_paper(pp, seen_at="2026-08-01")
        store.record_judgment(pp.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    vistos = []
    run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (vistos.append(pp.arxiv_id) or (fake_signal(1, 5), [])),
        judge_all=lambda ps: {}, recheck_limit=2,
    )
    assert len(vistos) == 2


def test_a_paper_discovered_today_is_not_also_rechecked(store):
    """Sem a de-duplicacao, um paper novo entraria duas vezes na lista de
    trabalho e teria o sinal buscado duas vezes."""
    p = paper("2508.00001")
    vistos = []
    run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[p], cuts={}),
        fetch_signal=lambda pp, t: (vistos.append(pp.arxiv_id) or (fake_signal(4, 20), [])),
        judge_all=lambda ps: {pp.arxiv_id: judgment() for pp in ps},
        recheck_limit=10,
    )
    assert vistos == ["2508.00001"]


def test_recheck_advances_the_rotation_even_when_the_signal_fails(store):
    """Sem touch_checked na falha, `stalest_papers` devolveria os mesmos
    papers para sempre e a rotacao nunca chegaria aos demais."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")

    result = run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (_ for _ in ()).throw(RuntimeError("GitHub fora")),
        judge_all=lambda ps: {}, recheck_limit=10,
    )
    assert result.cuts["sinal_indisponivel"] == 1
    assert store.all_papers()[0]["last_checked"] == TODAY.isoformat()


def test_recheck_is_off_by_default(store):
    """recheck_limit=0 por default: os chamadores existentes nao ganham
    re-consulta sem pedir."""
    p = paper("2210.17323")
    store.upsert_paper(p, seen_at="2026-08-01")
    store.record_judgment(p.arxiv_id, judgment(), model="m", judged_at="2026-08-01")
    vistos = []
    run_day(
        store=store, scope=SCOPE, thresholds=T, today=TODAY, model="modelo-de-teste",
        fetch_papers=lambda s: Discovery(papers=[], cuts={}),
        fetch_signal=lambda pp, t: (vistos.append(pp.arxiv_id) or (fake_signal(1, 5), [])),
        judge_all=lambda ps: {},
    )
    assert vistos == []
```

- [ ] **Passo 2: Rodar e confirmar que falham**

Esperado: `TypeError: run_day() got an unexpected keyword argument 'recheck_limit'`

- [ ] **Passo 3: Implementar**

Acrescentar o parâmetro à assinatura de `run_day`, depois de `dry_run`:

```python
    dry_run: bool = False,
    recheck_limit: int = 0,
) -> DayResult:
```

E, logo depois de montar `trabalho` com os papers novos:

```python
    # Re-consulta (spec da re-consulta, secao 3): entra DEPOIS dos novos, que
    # tem prioridade de orcamento, e e a primeira coisa cortada quando o
    # orcamento acaba. Julgamento vem do banco -- re-consulta nao gasta token.
    if recheck_limit > 0:
        novos_ids = {p.arxiv_id for p in papers}
        for antigo in store.papers_to_recheck(limit=recheck_limit):
            if antigo.arxiv_id in novos_ids:
                continue     # ja esta na lista como novidade; nao buscar duas vezes
            trabalho.append((antigo, store.latest_judgment(antigo.arxiv_id), False))
```

- [ ] **Passo 4: Rodar e confirmar que passam**

`PYTHONPATH=src python -m pytest tests/test_pipeline.py -v` → 9 testes novos passam. Suíte inteira: **177**.

- [ ] **Passo 5: Commit**

```bash
git add src/radar/pipeline.py tests/test_pipeline.py
git commit -m "feat: re-consulta de sinal entra na lista de trabalho do dia"
```

---

## Tarefa 5: A seção `## Re-consulta` no markdown

**Arquivos:** Modificar `src/radar/render.py` e `src/radar/pipeline.py`. Teste: `tests/test_render.py`.

**Interfaces:**
- Consome: `RadarItem` com `.delta` preenchido.
- Produz: `render_markdown(..., rechecked: list[RadarItem] | None = None, rechecked_total: int = 0)`.

**Regra de conteúdo:** a seção informa **quantos** foram re-consultados e lista **apenas os que se moveram**. Listar trinta papers cujo sinal está igual é ruído, e o teto de legibilidade é a restrição de produto mais forte do projeto. Quando nada se moveu, a seção diz isso explicitamente — pela mesma razão que a seção de Cortes é obrigatória mesmo vazia.

- [ ] **Passo 1: Escrever os testes que falham**

Em `tests/test_render.py`:

```python
def test_recheck_section_lists_only_what_moved():
    mexeu = item(delta={"independent_from": 2, "independent_to": 9,
                        "stars_from": 300, "stars_to": 340, "days": 21})
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={},
                         rechecked=[mexeu], rechecked_total=30)
    assert "30 papers re-consultados" in md
    assert "1 com movimento" in md
    assert "2 -> 9 impls independentes em 21 dias" in md


def test_recheck_section_is_explicit_when_nothing_moved():
    """Silencio ambiguo faz parecer que o trabalho nao foi feito."""
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={},
                         rechecked=[], rechecked_total=30)
    assert "30 papers re-consultados, nenhum com movimento" in md


def test_recheck_section_is_absent_when_no_recheck_ran():
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={})
    assert "## Re-consulta" not in md


def test_recheck_section_shows_the_current_score():
    mexeu = item(score=0.4032,
                 delta={"independent_from": 2, "independent_to": 9,
                        "stars_from": 300, "stars_to": 340, "days": 21})
    md = render_markdown("2026-08-27", radar=[], feed=[], cuts={},
                         rechecked=[mexeu], rechecked_total=5)
    assert "score 0.4032" in md
```

- [ ] **Passo 2: Rodar e confirmar que falham**

Esperado: `TypeError: render_markdown() got an unexpected keyword argument 'rechecked'`

- [ ] **Passo 3: Implementar**

Acrescentar os parâmetros a `render_markdown`:

```python
def render_markdown(
    day: str,
    radar: list[RadarItem],
    feed: list[RadarItem],
    cuts: dict[str, int],
    repos: dict[str, list[dict]] | None = None,
    rechecked: list[RadarItem] | None = None,
    rechecked_total: int = 0,
) -> str:
```

e, depois da seção Feed e antes da seção Cortes:

```python
    # Seccao presente apenas quando houve re-consulta. Lista so quem se moveu:
    # trinta linhas de "nada mudou" e ruido, e o teto de legibilidade e a
    # restricao de produto mais forte deste projeto. Mas quando nada se moveu,
    # diz isso -- silencio ambiguo faz parecer que o trabalho nao foi feito.
    if rechecked_total:
        out.append("## Re-consulta")
        out.append("")
        if rechecked:
            out.append(f"{rechecked_total} papers re-consultados. "
                       f"{len(rechecked)} com movimento:")
            out.append("")
            for it in rechecked:
                d = it.delta or {}
                out.append(
                    f"- {it.paper.arxiv_id} — "
                    f"{d.get('independent_from')} -> {d.get('independent_to')} "
                    f"impls independentes em {d.get('days')} dias — "
                    f"score {it.score:.4f}"
                )
        else:
            out.append(f"{rechecked_total} papers re-consultados, nenhum com movimento.")
        out.append("")
```

Em `src/radar/pipeline.py`, acumular os re-consultados que se moveram e repassar:

```python
    # "Movimento" e o delta existir e as implementacoes independentes terem
    # mudado. Delta existe para todo paper com duas observacoes; so vale
    # reportar quem de fato mudou.
    reconsultados_com_movimento = [
        item for item, _, e_novo in candidates
        if not e_novo and item.delta
        and item.delta["independent_to"] != item.delta["independent_from"]
    ]
    total_reconsultado = sum(1 for _, _, e_novo in candidates if not e_novo)
```

e passar às duas na chamada de `render_markdown`:

```python
        markdown=render_markdown(day, radar=radar, feed=feed,
                                 cuts=dict(cuts), repos=repos_by_paper,
                                 rechecked=reconsultados_com_movimento,
                                 rechecked_total=total_reconsultado),
```

- [ ] **Passo 4: Rodar e confirmar que passam** — suíte em **181**.

- [ ] **Passo 5: Commit**

```bash
git add src/radar/render.py src/radar/pipeline.py tests/test_render.py
git commit -m "feat: secao de re-consulta no markdown, so com quem se moveu"
```

---

## Tarefa 6: Ligar na CLI

**Arquivos:** Modificar `src/radar/cli.py`. Teste: `tests/test_cli.py`.

**Interfaces:** Consome `load_recheck_limit()` da Tarefa 2 e o `recheck_limit` de `run_day` da Tarefa 4.

- [ ] **Passo 1: Escrever o teste que falha**

```python
def test_the_cli_passes_the_configured_recheck_limit(monkeypatch, tmp_path):
    """Sem esta ligacao a re-consulta existe e nunca roda -- exatamente o
    estado em que stalest_papers ficou desde que foi escrita."""
    monkeypatch.setenv("RADAR_RECHECK_LIMIT", "7")
    capturado = {}

    def fake_run_day(**kwargs):
        capturado.update(kwargs)
        raise SystemExit(0)

    monkeypatch.setattr("radar.cli.run_day", fake_run_day)
    monkeypatch.setattr("radar.cli.anthropic", type("A", (), {"Anthropic": lambda: None}))
    with pytest.raises(SystemExit):
        cli.main(["--dry-run", "--db", str(tmp_path / "r.db"), "--out", str(tmp_path)])
    assert capturado["recheck_limit"] == 7
```

- [ ] **Passo 2: Rodar e confirmar que falha**

Esperado: `KeyError: 'recheck_limit'`

- [ ] **Passo 3: Implementar**

Em `src/radar/cli.py`, no import de config acrescentar `load_recheck_limit`, e na chamada de `run_day`:

```python
        dry_run=args.dry_run,
        recheck_limit=load_recheck_limit(),
    )
```

- [ ] **Passo 4: Rodar a suíte inteira** — **182 passed**.

- [ ] **Passo 5: Commit**

```bash
git add src/radar/cli.py tests/test_cli.py
git commit -m "feat: CLI liga a re-consulta com o limite configurado"
```

---

## Auto-revisão do plano

**Cobertura da spec.** §2 (significado de ressurreição) → Tarefa 4, testes de delta e de já-entregue. §3 (onde entra) → Tarefas 3 e 4. §4 (elegibilidade) → Tarefa 4, testes de radar e de feed. §5 (não gasta token) → Tarefa 4, `test_recheck_reuses_the_stored_judgment_and_never_calls_the_llm` e `test_a_rechecked_paper_without_a_stored_judgment_is_cut_distinctly`. §6 (orçamento, `touch_checked` na falha) → Tarefas 1, 2 e 4. §7 (markdown) → Tarefa 5. §8 (testes) → todos presentes.

**Consistência de tipos.** `papers_to_recheck` devolve `list[Paper]` em 1 e é consumido como tal em 4. `candidates` passa a `tuple[RadarItem, bool, bool]` na Tarefa 3 e todos os consumidores são ajustados na mesma tarefa. `render_markdown` ganha dois parâmetros com default na Tarefa 5, então os chamadores existentes seguem válidos.

**Uma escolha que vale registrar:** `recheck_limit` tem default `0`, não `RECHECK_LIMIT`. Assim nenhum teste existente ganha re-consulta sem pedir, e a Tarefa 3 pode ser uma refatoração de verdade sem mudança de comportamento. Quem liga a feature é a CLI, explicitamente, na Tarefa 6.

## Ordem de execução

Sequencial e obrigatória: 1 e 2 são independentes entre si mas ambas precedem 4; 3 precede 4; 5 depende de 4; 6 depende de 2 e 4. Tudo roda offline.
