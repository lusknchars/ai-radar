# Radar de Técnicas — Spec

**Data:** 2026-08-27
**Desenho de origem:** `docs/2026-08-23-radar-desenho.md` (revisado após spike de 27/ago)
**Status:** spec para revisão. Nenhum código escrito.

---

## 1. Objetivo

Um hub pessoal que responde duas perguntas por dia sobre engenharia de inferência e eficiência de modelos:

**Radar** — o que vale a pena e ainda não estourou.
**Feed** — o que saiu hoje no meu escopo.

São produtos diferentes que compartilham a mesma esteira. O que muda entre eles é apenas o filtro e o canal de entrega.

### Não-objetivos

Não é agregador de notícias de IA em geral. Não cobre visão, áudio, robótica, agentes ou RAG. Não tem interface web. Não tem usuários além de um. Não busca completude: cobertura parcial com sinal alto é preferível a cobertura total com ruído.

---

## 2. As duas trilhas

| | Radar | Feed |
|---|---|---|
| Pergunta | vale a pena e não estourou? | o que saiu hoje? |
| Filtro | score de implementação | só escopo |
| Volume | **teto rígido de 3** | tudo que passa no escopo (10 a 40/dia) |
| Enriquecimento | sinal do GitHub + julgamento | resumo de uma linha |
| Entrega | push no Telegram | markdown no repositório |

O feed nunca entra no Telegram. Se entrar, afoga os três itens do radar e a coisa toda vira ruído — o modo de falha que o teto existe para evitar.

---

## 3. Fonte e escopo

### Descoberta: arXiv API

**Pegadinha registrada e medida:** a API só responde em **HTTPS com User-Agent explícito**. Em HTTP ela devolve **301 com corpo vazio**. A falha é silenciosa porque `raise_for_status()` não levanta em 3xx e o httpx não segue redirect por padrão — o chamador recebe zero byte e nenhum erro.

```
https://export.arxiv.org/api/query
  ?search_query=<query>
  &sortBy=submittedDate&sortOrder=descending
  &max_results=100
```

**Categorias:** `cs.LG`, `cs.CL`, `cs.DC`, `cs.AR`, `cs.PF`

**Termos de escopo**, cada um consultado como query separada e unida por `arxiv_id`:

```
quantization          "speculative decoding"   "KV cache"
"inference latency"   "inference throughput"   sparsity
pruning               "low-rank"               "attention kernel"
"memory bandwidth"    "model serving"          "efficient inference"
```

Uma query por termo, com **intervalo de 3 segundos** entre chamadas (etiqueta pedida pelo arXiv). Doze termos custam ~36 segundos por execução — irrelevante num cron diário.

Consultas separadas em vez de uma query booleana gigante porque a API do arXiv trata mal query longa com aspas aninhadas, e porque a união em código é trivial e depurável.

### Filtro de escopo

Um paper entra se o termo aparece em `title` ou `abstract` e **pelo menos uma** de suas categorias está na lista — não apenas a primária. Cross-listing é comum em trabalho de eficiência (primária `cs.AI`, secundária `cs.LG`), e a descoberta favorece recall de propósito: cinco filtros a jusante (termo, sinal do GitHub, portão de atenção, piso de score, teto de 3) cuidam da precisão. Papers já presentes no banco não reentram como novidade — viram atualização de sinal.

---

## 4. O sinal

Para cada paper candidato, uma busca no GitHub:

```
GET /search/repositories?q="<arxiv_id>"+in:readme&per_page=100
```

Verificado no spike: o ID do GPTQ (`2210.17323`) devolve 104 repositórios, e a distinção autor/independente é visível no resultado.

### Métricas por paper

| Campo | Definição |
|---|---|
| `total_impls` | repositórios distintos que citam o arXiv ID |
| `independent_impls` | destes, os cujo dono **não** é autor do paper |
| `velocity_14d` | repositórios criados nos últimos 14 dias |
| `stars_total` | soma de estrelas de todos os repositórios |
| `citations` | contagem via Semantic Scholar (opcional; 0 se indisponível) |

### Fórmula: portão, depois razão

Duas etapas, e a ordem importa.

**Etapa 1 — portão de atenção.** Um paper que já estourou não é material de radar *por definição*. Ele não recebe score baixo; ele não é pontuado.

```python
BROKE_OUT_STARS     = 1000   # calibravel
BROKE_OUT_CITATIONS = 200    # calibravel

if stars_total > BROKE_OUT_STARS or citations > BROKE_OUT_CITATIONS:
    return None   # fora do radar; segue para o feed com motivo 'ja_estourou'
```

**Etapa 2 — razão entre os que passaram.**

```python
signal    = log1p(independent_impls) * (1 + 0.5 * log1p(velocity_14d))
attention = log1p(stars_total) + log1p(citations)
score     = signal / (1 + attention)
```

Implementação independente é o numerador porque construir custa caro e ninguém constrói por hype. Atenção é o denominador porque é exatamente o que você veria sem o radar.

### Por que o portão, e não só a razão

A primeira versão desta spec usava apenas a razão, sem portão. Um teste de sanidade com os números reais do GPTQ derrubou essa versão: com 103 implementações, 3000 estrelas e 2500 citações, o GPTQ marcava 0,4275 e ficava em **terceiro lugar** — acima de casos que o radar deveria priorizar. O `log1p` comprime demais no topo, e um numerador enorme quase compensa um denominador enorme.

Com o portão, o comportamento fica correto:

| Caso | indep | estrelas | citações | resultado |
|---|---:|---:|---:|---|
| Joia escondida | 4 | 60 | 0 | **0,5332** |
| Novo e ignorado | 2 | 15 | 0 | 0,4512 |
| Ressurreição de paper antigo | 9 | 340 | 120 | 0,4039 |
| Só os autores, ninguém replicou | 0 | 800 | 30 | 0,0000 |
| GPTQ hoje | 103 | 3000 | 2500 | cortado no portão |
| Hype sem implementação | 1 | 5000 | 50 | cortado no portão |

O portão também simplifica o resto: a razão só precisa ordenar dentro do conjunto "ainda não estourou", que é um trabalho muito mais fácil do que ordenar o universo inteiro.

**Os dois limiares não estão calibrados** e não há como calibrá-los sem dados. Rodam nos valores acima durante as duas primeiras semanas, com todo corte registrado no markdown do dia para revisão.

### Detecção de autoria (heurística declarada)

Um repositório é marcado `is_author=True` se **qualquer** condição valer:

1. O login do dono casa (normalizado, sem acento, minúsculo) com o sobrenome de algum autor do paper
2. O `full_name` do repositório aparece no texto do abstract
3. É simultaneamente o mais antigo **e** o mais estrelado entre os que citam o paper

**Esta heurística erra, e o erro é assimétrico e conhecido.** Laboratório publicando sob nome de organização (`IST-DASLab/gptq`) não casa por sobrenome e só é pego pela regra 3. Reimplementação de terceiro que por acaso seja a mais antiga e mais estrelada é marcada como autor por engano, deprimindo o score.

Mitigação: gravar `is_author_reason` junto com a flag, para que toda decisão seja auditável no markdown. Não corrigir automaticamente — registrar e revisar.

### Orçamento de rate limit

GitHub search: 10 req/min sem token, 30/min com token, reset por minuto.

**Em quantos papers cada etapa roda** (evita ambiguidade entre as secoes):

| Etapa | Alvo | Volume tipico |
|---|---|---|
| Sinal do GitHub | todo paper novo no escopo do dia | 10 a 40 buscas |
| Re-consulta de sinal | papers ja no banco, mais antigos primeiro | o que sobrar do orcamento |
| Julgamento por LLM | todo paper novo no escopo do dia | 10 a 40 chamadas |
| Push do Telegram | os 3 de maior score | 3 |

O pipeline dorme entre chamadas em vez de estourar o limite, e a re-consulta e a primeira coisa a ser cortada quando o orcamento acaba — descoberta nova tem prioridade sobre atualizacao.

---

## 5. Julgamento por LLM

### Modelo

`claude-opus-5` via SDK oficial `anthropic` (Python), com `thinking: {type: "adaptive"}` e `output_config: {effort: "low"}` — a tarefa é curta e bem definida, não precisa de esforço alto.

### Saída estruturada

Usar `output_config.format` com este schema, via `client.messages.parse()`:

```python
{
  "type": "object",
  "properties": {
    "technique":    {"type": "string"},   # rótulo curto, ex "INT4 kernel para Ampere"
    "summary":      {"type": "string"},   # UMA frase, o que a técnica faz
    "runs_on_3090": {"type": "string", "enum": ["sim", "sim_com_ressalva", "nao"]},
    "rationale":    {"type": "string"}    # uma linha justificando o veredito
  },
  "required": ["technique", "summary", "runs_on_3090", "rationale"],
  "additionalProperties": false
}
```

O classificador `runs_on_3090` recebe no prompt as restrições da máquina: **Ampere GA102, 24 GB, sem unidades FP8, 936 GB/s de banda, PCIe 4.0**. Papers que dependem de FP8, de multi-GPU, ou de mais de 24 GB recebem `nao` com a razão explícita.

### Batch API para o feed

O feed é trabalho diário não sensível a latência, então usa `client.messages.batches.create()` — **50% do custo**. O radar (3 itens) usa chamadas normais, porque o volume é trivial e o resultado é imediato.

Resultados do batch chegam **fora de ordem**; indexar por `custom_id`, nunca por posição.

### Custo estimado

Quarenta itens/dia, entrada de ~600 tokens (abstract) e saída de ~200:

```
24.000 tok entrada × $5/M  = $0,12
 8.000 tok saída   × $25/M = $0,20
                     total ≈ $0,32/dia  ≈  $9,60/mês
```

Com o Batch API no feed, cai para perto de **$5/mês**. Esse é o número com Opus 5. Trocar para `claude-sonnet-5` ou `claude-haiku-4-5` reduz mais, mas é decisão sua, não default meu — a spec fixa Opus 5 e deixa o modelo configurável por variável de ambiente.

---

## 6. Estado

SQLite versionado no repositório, em `data/radar.db`.

```sql
CREATE TABLE papers (
    arxiv_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    abstract     TEXT NOT NULL,
    authors      TEXT NOT NULL,      -- JSON: lista de nomes
    categories   TEXT NOT NULL,      -- JSON: lista
    published    TEXT NOT NULL,      -- ISO date
    first_seen   TEXT NOT NULL,
    last_checked TEXT
);

CREATE TABLE signals (              -- append-only: e daqui que sai o delta
    arxiv_id          TEXT NOT NULL REFERENCES papers(arxiv_id),
    checked_at        TEXT NOT NULL,
    total_impls       INTEGER NOT NULL,
    independent_impls INTEGER NOT NULL,
    velocity_14d      INTEGER NOT NULL,
    stars_total       INTEGER NOT NULL,
    citations         INTEGER NOT NULL DEFAULT 0,
    score             REAL    NOT NULL,
    PRIMARY KEY (arxiv_id, checked_at)
);

CREATE TABLE repos (
    arxiv_id         TEXT NOT NULL REFERENCES papers(arxiv_id),
    full_name        TEXT NOT NULL,
    owner            TEXT NOT NULL,
    stars            INTEGER NOT NULL,
    created_at       TEXT NOT NULL,
    is_author        INTEGER NOT NULL,   -- 0/1
    is_author_reason TEXT,               -- qual regra disparou; auditavel
    PRIMARY KEY (arxiv_id, full_name)
);

CREATE TABLE judgments (
    arxiv_id      TEXT NOT NULL REFERENCES papers(arxiv_id),
    judged_at     TEXT NOT NULL,
    model         TEXT NOT NULL,
    technique     TEXT NOT NULL,
    summary       TEXT NOT NULL,
    runs_on_3090  TEXT NOT NULL,
    rationale     TEXT NOT NULL,
    PRIMARY KEY (arxiv_id, judged_at)
);

CREATE TABLE deliveries (
    arxiv_id     TEXT NOT NULL REFERENCES papers(arxiv_id),
    delivered_at TEXT NOT NULL,
    channel      TEXT NOT NULL,     -- 'telegram' | 'markdown'
    rank         INTEGER,
    PRIMARY KEY (arxiv_id, delivered_at, channel)
);
```

`signals` ser append-only é o que compra a detecção de ressurreição: um paper antigo voltando a ser implementado aparece como **delta entre duas linhas** da mesma entrada. Nenhum paper é entregue duas vezes no Telegram — `deliveries` é consultado antes de montar o push.

### Re-consulta

Todo dia o pipeline re-consulta o sinal dos papers já no banco, priorizando: vistos há mais tempo primeiro, dentro do orçamento de rate limit que sobrar depois dos candidatos novos.

---

## 7. Entrega

### Telegram (radar, teto de 3)

Texto puro, sem emoji, um bloco por item:

```
[TECNICA] Kernel INT4 fundido para Ampere
Multiplicacao INT4xFP16 que satura banda de memoria em batch unitario.
4 impls independentes · 60 estrelas · +3 em 14 dias
Roda na 3090: sim
arxiv.org/abs/2508.12345
```

Quando o item é ressurreição em vez de novidade, a linha de números vira delta:

```
2 -> 9 impls independentes em 21 dias · 340 estrelas
```

### Ordenação do push: executável primeiro

O push ordena por **(executa na 3090, score)**, não por score puro. Todos os itens com veredito `sim` ou `sim_com_ressalva` vêm antes de qualquer `nao`, e cada grupo é ordenado por score internamente.

Motivo: sem isso, um paper que depende de FP8 — inexecutável em Ampere por definição — consome uma das três vagas competindo de igual para igual com técnicas que você pode testar hoje. Rebaixar preserva a visão periférica (o item ainda entra se sobrar vaga, e sempre aparece no feed) sem deixar o inexecutável disputar espaço com o acionável.

Se num dia nenhum candidato passar do piso de score, **o push não é enviado**. Silêncio é resultado válido; mandar item fraco só para ter o que mandar destrói a confiança no canal.

### Markdown (feed, tudo)

`radar/YYYY-MM-DD.md`, commitado pelo próprio workflow:

1. Os 3 itens do radar, com os números crus e o `is_author_reason` de cada repositório contado
2. Todos os demais candidatos do dia, com resumo de uma linha e veredito 3090
3. **O que foi cortado e por quê** — contagem por motivo (fora de escopo, score abaixo do piso, já entregue antes)

O item 3 é obrigatório. Truncar em silêncio faz um radar parecer que cobriu tudo quando não cobriu.

---

## 8. Execução

GitHub Actions, cron diário às 09:00 UTC (06:00 em Brasília).

```yaml
on:
  schedule:
    - cron: '0 9 * * *'
  workflow_dispatch:
```

Passos: checkout, setup do Python 3.12, instalar dependências, rodar o pipeline, commitar `data/radar.db` e `radar/*.md`, enviar o push do Telegram.

**Segredos necessários:** `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, e `GH_TOKEN` (opcional, eleva o rate limit de 10 para 30 req/min).

Nota operacional: segredos de Actions **não viajam com o repositório**. Se o repo for movido, renomeado ou recriado, todos precisam ser repostos ou o workflow falha em runtime, não no push.

---

## 9. Restrições globais

**Git exige aprovação por ação.** Nenhum `git init`, `commit`, `push` ou criação de repositório sem aprovação explícita do Lucas para aquela ação. Isso vale para a criação inicial do repositório. O commit feito *pelo workflow em execução* é outra coisa — é o robô operando dentro de um repositório que já foi autorizado a existir.

**Sem trailer de co-autoria** em nenhuma mensagem de commit.

**Nada de truncamento silencioso.** Todo corte é contado e registrado no markdown do dia.

**Toda decisão heurística é auditável.** `is_author_reason` e o motivo de corte são gravados, não inferidos depois.

**O teto de 3 é rígido**, não orientação. Nenhum caminho no código o ultrapassa.

---

## 10. Riscos e limitações conhecidas

**A heurística de autoria erra.** Já detalhado na seção 4. É a maior fonte de erro do score e não tem solução limpa sem intervenção manual. Aceita conscientemente, com registro auditável.

**Cobertura do GitHub é parcial.** `in:readme` só encontra papers citados no README da branch padrão. Implementação que cita o paper apenas no código, no artigo, ou num notebook é invisível. O sinal é um piso, não uma contagem.

**Papers sem arXiv ID são invisíveis.** Trabalho publicado só em conferência, blog de laboratório ou repositório sem paper não entra. Limitação estrutural da escolha de chave canônica.

**O escopo estreito exclui de propósito.** Técnicas de eficiência que apareçam fora das cinco categorias do arXiv passam batido. É o preço do sinal alto sobre a cobertura.

**Nem o piso de score nem os limiares do portão estão calibrados.** Não há como calibrar sem dados. As duas primeiras semanas rodam com o piso em zero e o portão nos valores iniciais, com tudo indo para o markdown — inclusive o que foi cortado e por qual limiar — para observar a distribuição real antes de fixar os cortes.

---

## 11. Decisões travadas

| Decisão | Escolha | Motivo |
|---|---|---|
| Sinal primário | implementação independente | construir custa caro; ninguém constrói por hype |
| Descoberta | arXiv, não GitHub | spike de 27/ago: busca por palavra-chave no GitHub é ruidosa demais |
| Pontuação | GitHub por arXiv ID | spike confirmou: 1 requisição, sinal limpo |
| Escopo | inferência, eficiência, sistemas | volume baixo, e alimenta o quant-bench |
| Teto do push | 3 itens, rígido | único mecanismo contra virar pasta não lida |
| Ordem do push | executável na 3090 primeiro, depois score | inexecutável não disputa vaga com o acionável |
| Entrega | Telegram + markdown no repo | push para ler, repo para grepar |
| Modelo | `claude-opus-5`, configurável | default do padrão; troca é decisão do usuário |
| Feed via Batch API | sim | 50% do custo, e latência é irrelevante num cron |
| Estado | SQLite append-only no repo | delta é o que torna ressurreição detectável |
| Execução | GitHub Actions | sem servidor; o repo é banco e arquivo |

---

## 12. Próximo passo

Converter esta spec em plano de implementação com tarefas em TDD, na linha do que foi feito para o quant-bench. Nenhum código antes disso.
