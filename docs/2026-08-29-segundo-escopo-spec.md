# Segundo escopo e julgamento reescrito — Spec

**Data:** 2026-08-29
**Estado:** aprovado, aguardando plano
**Depende de:** `docs/2026-08-27-radar-spec.md` (spec principal), `docs/2026-08-28-re-consulta-spec.md`

---

## 1. Por que existe

O radar hoje varre doze termos de inferência eficiente — quantização, cache KV,
decodificação especulativa, esparsidade, kernels, serving. É a literatura certa
para uma bancada de quantização e é a literatura errada para quem trabalha com
harness de agentes.

Além disso, o julgamento produziu, no seed de 2026-08-29, **1088 valores
distintos de `technique` para 1088 papers**. O campo é prosa livre e boa prosa,
mas uma taxonomia com N categorias para N itens não é taxonomia. Não existe a
pergunta "o que andou acontecendo em cache KV neste trimestre", porque não
existe o grupo — existem quarenta frases únicas que falam disso.

E o eixo de veredito, `runs_on_3090`, respondeu `sim_com_ressalva` em **566 de
1088 papers (52%)**. Um eixo cuja resposta modal é "mais ou menos" não separa
nada, e custa um campo de saída estruturada em todo julgamento.

Esta spec conserta as três coisas de uma vez, porque as três são a mesma edição:
o schema de julgamento e o lote que o preenche.

### Não-objetivos

Reprodução de papers. Não há infraestrutura para isso e não é o produto. O
produto é um jornal pessoal de técnicas de AI/ML Engineering para quem tem infra
pequena, não uma bancada de experimentos.

Ampliar o escopo de inferência. Ele fica exatamente como está.

O caderno de práticas (papers que colidem com práticas declaradas do time) fica
para uma spec futura: ele depende de um insumo — as práticas escritas — que não
existe ainda.

---

## 2. O segundo escopo

### Medição, não estimativa

Antes de propor o escopo, mediu-se o volume de sete dias pela mesma consulta que
o pipeline usa. Uma primeira lista de vinte termos sobre `cs.AI, cs.CL, cs.LG,
cs.SE, cs.MA` devolveu **526 papers em 7 dias (~75/dia)**, com `agentic`,
`trajectory` e `planning` saturando o teto de 200 resultados — ou seja, 75/dia é
piso, não teto.

O diagnóstico foi que `cs.LG` traz RL e robótica, e que os três termos genéricos
capturam trajetória de robô e planejamento clássico, não harness. Retirando a
categoria e os três termos, a lista apertada devolveu **177 papers em 7 dias
(~25/dia)**, com um único termo morto (`tool retrieval`, zero papers inéditos).

O escopo de inferência atual, medido pelo mesmo método, é **102 em 7 dias
(~15/dia)**.

**Total operacional: ~40 papers/dia.**

### Definição

```python
AGENT_SCOPE = ScopeConfig(
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
```

`cs.LG` está fora **por decisão**, não por esquecimento: é a categoria que
triplica o volume com literatura de RL e robótica. Quem reintroduzi-la precisa
re-medir e justificar.

`tool retrieval` está fora porque a medição mostrou zero papers inéditos: tudo o
que ele traz já vem por `tool use` ou `tool calling`.

---

## 3. Como dois escopos convivem

### A coluna

`papers` ganha `scope TEXT NOT NULL` com valor em `('inferencia', 'agentes')`.

Um paper pode casar com os dois escopos — um trabalho sobre cache KV para
agentes de código, por exemplo. **O primeiro escopo que o descobrir fica com
ele**, e a ordem de execução é `inferencia` depois `agentes`. Isso é arbitrário
e declarado: a alternativa (um paper em dois escopos) duplicaria a linha no
jornal e quebraria a chave primária de `papers`.

Migração das 1088 linhas existentes: todas recebem `scope = 'inferencia'`,
porque foi de `DEFAULT_SCOPE` que vieram.

### A execução

`ScopeConfig` ganha um campo **`name: str`**. Sem ele o pipeline não tem como
dizer ao `store` qual escopo gravar, e a auto-revisão desta spec pegou
exatamente isso: a primeira redação afirmava que nada mudava de assinatura, o
que era falso.

Com `name` no `ScopeConfig`, `run_day` de fato **não muda de assinatura** — ele
já recebe um `scope` e já opera sobre um. O CLI passa a chamá-lo uma vez por
escopo, em sequência, e mescla os dois resultados.

Consequências que precisam estar corretas:

- **`PUSH_CAP` não muda.** Ele continua 3 e continua morando só em `config.py`.
  Duas execuções de `run_day` produzem no máximo 3 cada, o que dá 6 no push
  diário. Isso é o comportamento desejado — as duas literaturas têm scores
  incomparáveis, e forçá-las a disputar as mesmas três vagas faria a de maior
  volume engolir a outra.
- **`known_ids()` precisa ser global, não por escopo.** É o que impede o segundo
  escopo de re-descobrir e re-julgar o que o primeiro acabou de gravar. Ele já é
  global hoje; o teste que trava isso precisa existir.
- **A re-consulta continua uma só**, com `RECHECK_LIMIT` global. Ela opera sobre
  `papers` inteira e não conhece escopo.

### A mesclagem

`render_markdown` não ganha parâmetro de escopo. Em vez disso entra uma função
nova e fina em `render.py`:

```python
def compose_day(day: str, por_escopo: dict[str, DayResult]) -> str
```

Ela produz o arquivo do dia com uma seção por escopo, preservando a ordem
`inferencia`, `agentes`. O push do dia é a concatenação dos dois `push`.

Manter `render_markdown` intacta é deliberado: ela é a função mais coberta por
teste do projeto, e o custo de reabri-la é maior que o de compor por cima.

---

## 4. O julgamento reescrito

### O schema novo

```python
class JudgmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technique:   str          # manchete em prosa livre — continua
    familia:     Literal[...] # 19 valores fechados — o eixo de agregação
    pratica:     Literal["adotar", "testar", "observar", "nao_aplica"]
    ganho_eixo:  Literal["velocidade", "memoria", "custo", "qualidade", "nenhum"]
    ganho_fator: float | None # 2.3 quando o paper alega um fator; None quando não
    ganho_texto: str          # a alegação como o paper a faz, verbatim, para auditoria
    resumo:      str          # reescrito para o leitor certo
    porque:      str          # uma linha justificando `pratica`
```

`runs_on_3090` **sai**. `rationale` vira `porque` e passa a justificar `pratica`
em vez de hardware. `summary` vira `resumo` e muda de conteúdo (§4.3).

`technique` fica. É boa manchete; o erro nunca foi o campo, foi usá-lo como eixo
de agregação.

### 4.1 `familia` — o eixo fechado

Dezenove valores. Nove de inferência, nove de agentes, e um escape.

**Inferência:** `quantizacao`, `cache_kv`, `decodificacao_especulativa`,
`esparsidade_e_poda`, `kernels_e_atencao`, `serving_e_batching`,
`arquitetura_eficiente`, `destilacao`, `treino_eficiente`.

**Agentes:** `uso_de_ferramenta`, `memoria_e_contexto`,
`planejamento_e_decomposicao`, `orquestracao_multiagente`,
`avaliacao_de_agente`, `recuperacao_de_falha`, `agentes_de_codigo`,
`seguranca_e_guardrails`, `recuperacao_e_rag`.

**Escape:** `outro`.

O `outro` não é preguiça de taxonomia — é instrumento. Sem ele o modelo é
forçado a encaixar mal e o erro fica invisível. Com ele, **a frequência de
`outro` mede se a taxonomia está errada** (§7).

A família não é derivada do escopo: um paper descoberto pelo escopo de agentes
pode ser legitimamente `cache_kv`. É por isso que os dois campos existem
separados — `scope` diz por onde ele entrou, `familia` diz do que ele trata.

### 4.2 `pratica` — o veredito acionável

Substitui `runs_on_3090`. O critério que vai na `description` do campo:

- **`adotar`** — dá para usar já, com infra pequena, com ganho claro e sem
  pré-requisito exótico.
- **`testar`** — plausível com infra pequena, mas o ganho depende de validação
  no caso concreto.
- **`observar`** — importa, e exige escala, hardware ou dado que não estão
  disponíveis.
- **`nao_aplica`** — fora do que se faz aqui.

O briefing de hardware é substituído por um briefing de leitor:

```
O leitor é um engenheiro de AI/ML com INFRA PEQUENA: uma GPU de 24 GB ou
APIs de terceiros, sem cluster, sem treino de modelo base, orçamento de
nuvem baixo, time pequeno. Ele decide o que adotar nas práticas do dia a
dia, não o que pesquisar.
```

### 4.3 `resumo` — escrito para quem vai ler

Hoje é "UMA frase dizendo o que a técnica faz" — abstract comprimido. Passa a
ser no máximo três frases que respondem, nesta ordem:

1. **O que substitui** — que prática atual ela troca.
2. **O que custa** — memória, latência, complexidade, ou qualidade perdida.
3. **O que quebra** — o que deixa de funcionar se você adotar.

Um resumo que não diz custo nem trade-off é propaganda, e propaganda é
exatamente o que um radar anti-hype não pode produzir. A instrução de estilo
existente — português, sem emoji, sem adjetivo promocional — continua valendo.

### 4.4 `ganho` — a alegação quantificada

Os três campos existem para uma coisa só: tornar plotável a pergunta "o que
mudou na literatura ao longo do tempo". Sem um número estruturado, o acervo
sabe *que* técnicas apareceram e não sabe *quanto* elas alegam entregar.

- **`ganho_eixo`** — em que dimensão o paper alega melhorar: `velocidade`,
  `memoria`, `custo`, `qualidade`, ou `nenhum` quando o paper não faz alegação
  quantificada. `nenhum` é resposta legítima e frequente.
- **`ganho_fator`** — o número, normalizado como **fator multiplicativo de
  melhora**, quando e somente quando o paper permite. "2.3x mais rápido" vira
  `2.3`. "reduz memória em 60%" vira `2.5` (1 / 0.4). "+3 pontos de acurácia"
  **não vira fator**: é `None`, porque pontos percentuais de qualidade não são
  razão. Quando `ganho_eixo` é `nenhum`, `ganho_fator` é obrigatoriamente `None`.
- **`ganho_texto`** — a alegação como o paper a faz, em texto, para que qualquer
  número no gráfico seja auditável até a frase que o originou.

**Estes campos registram alegação, não verificação.** Nada aqui foi reproduzido,
e a spec do jornal (§1) obriga que todo lugar onde o número aparece diga
isso. Um gráfico de ganhos alegados apresentado como resultado medido seria a
pior coisa que este projeto poderia produzir — ele existe justamente para fugir
de hype, e alegação de abstract é a matéria-prima do hype.


---

## 4-bis. O portão de citações está desligado

Achado da auto-revisão desta spec, verificado no banco: **`signals.citations` é
`0` em todas as 1088 linhas.**

`GitHubClient.signal_with_repos` recebe `citations: int = 0` e nenhum chamador
jamais passa outro valor. Não existe fonte de citação ligada ao projeto. As
consequências estavam invisíveis porque nada quebra:

- O portão `broke_out_citations = 200` **nunca disparou**. Os 12 cortes por
  `ja_estourou` do seed foram todos por estrela.
- `atencao = log1p(stars) + log1p(citations)` é, na prática, só estrelas.
- Metade do mecanismo anti-hype — o que impede um paper canônico e muito citado
  de ocupar o radar — está inerte.

### Decidido: OpenAlex, medido antes de travar

A primeira redação desta spec propunha Semantic Scholar afirmando "gratuita, sem
chave, ~1 req/3s". **A afirmação era falsa e a medição derrubou.**

**Semantic Scholar sem chave:** `429 Too Many Requests` na primeira requisição.
Com esperas crescentes de até 52s, **2 sucessos em 6 tentativas**. O tier não
autenticado é uma piscina compartilhada saturada. Uma fonte que falha dois
terços das vezes gravaria zeros silenciosos — o defeito que esta seção existe
para consertar.

**OpenAlex, medido:**

| o que | resultado |
|---|---|
| Resolução em lote por DOI | **5 de 5 numa requisição, 0,38s** |
| Chave | nenhuma; basta `mailto:` no User-Agent (pool "polite") |
| Teto por requisição | 50 (`per-page`), logo **1 requisição/dia** para ~40 papers |
| Contagem real | LoRA 2527, FlashAttention 461, GPTQ 136 |
| Taxa de resolução | **~92%** (23/25 do acervo antigo; 3/4 dos clássicos) |

A consulta é um filtro OR sobre DOI:

```
GET https://api.openalex.org/works
    ?filter=doi:https://doi.org/10.48550/arXiv.{id}|...(até 50)
    &select=doi,cited_by_count
```

### As três armadilhas, e o que a spec obriga

**1. Não-resolvido não é zero.** "Attention Is All You Need" (1706.03762) não
resolveu: arXiv só passou a cunhar DOI automaticamente por volta de 2022, e
papers anteriores podem não ter `10.48550/arXiv.*`. Gravar `0` para quem não
resolveu recria o bug atual com outra roupa.

> `Signal.citations` passa de `int` para **`int | None`**. `None` significa
> **desconhecido**, e o portão de estouro por citação **não dispara em `None`** —
> ele só corta com número. `signals.citations` aceita `NULL`.

**2. O DOI volta em caixa baixa.** A consulta usa `arXiv.` e a resposta traz
`arxiv.`. O casamento de volta é **case-insensitive**, ou toda linha se perde
silenciosamente.

**3. A maioria vai ser zero legítimo, e tudo bem.** O acervo é de papers
recentes: dos 25 mais antigos, 8 têm citação. Zero medido é dado; zero
constante era mentira. O portão de 200 vai continuar disparando pouco, e agora
por razão verdadeira.

### Fronteira de código

`OpenAlexClient`, no mesmo padrão de injeção de transporte que `arxiv` e
`github` já seguem: recebe `fetch`, não importa `httpx`. Uma chamada por
execução, antes do laço de sinal, produzindo `dict[str, int | None]` que o
pipeline consulta. Falha da API inteira degrada para `None` em todos — nunca
para `0`.


---

## 5. Migração

### O banco

`judgments` é reconstruída, não alterada. SQLite não remove `NOT NULL` de coluna
existente sem rebuild, e `runs_on_3090 TEXT NOT NULL` está no caminho.

**As linhas antigas de `judgments` são descartadas.** Elas são substituídas
dentro da mesma hora pelo re-julgamento, carregam um campo que deixa de existir,
e mantê-las obrigaria todo o caminho de leitura a lidar com `familia` nula em
troca de nada. `papers`, `signals`, `repos` e `deliveries` **não são tocadas** —
o acervo e o histórico de sinal são o ativo caro e permanecem intactos.

Pré-condição obrigatória: **cópia de `data/radar.db` antes da migração**, e o
caminho da cópia é reportado. Sem isso a operação é irreversível.

### O re-julgamento

Um script pontual, fora de `src/`, no mesmo molde do `seed.py` que rodou hoje:
lê os 1088 papers do banco, submete um lote, grava os julgamentos novos. Não
toca em `arxiv`, não toca em `github`, não gasta rate limit.

Ele precisa do prazo estendido do lote (`timeout_seconds` explícito), pela mesma
razão que o seed precisou: `BATCH_TIMEOUT_SECONDS = 45 * 60` é orçamento de cron
diário e um lote de 1088 pode passar disso. Um lote que estoura devolve `{}` e
perde o lote pago.

Custo medido no seed: **US$ 4,36 para 1088 papers**, 64 minutos de ponta a ponta
— mas ali 60 dos 64 minutos foram GitHub, que aqui não roda. O lote em si levou
poucos minutos.

---

## 6. Orçamento

Com os dois escopos em regime diário:

| item | volume | custo |
|---|---|---|
| Papers/dia | ~40 (15 inferência + 25 agentes) | — |
| Julgamento (Batch API) | ~40/dia | ~US$ 0,16/dia, ~US$ 5/mês |
| Buscas GitHub | ~40/dia a 2,5s com `GH_TOKEN` | ~100s |
| Re-consulta | `RECHECK_LIMIT = 30`, sem token | ~75s |
| **Execução diária total** | | **< 5 minutos** |

O `GH_TOKEN` deixa de ser opcional na prática. Sem ele o intervalo sobe para 6s
e a execução diária passa de sete minutos só em GitHub.

---

## 7. Riscos, com critério de aceite

**O eixo `pratica` colapsar num valor modal.** É exatamente o que aconteceu com
`runs_on_3090` (52% em `sim_com_ressalva`), e trocar um eixo inútil por outro
eixo inútil seria o pior resultado possível desta spec.

> **Critério de aceite, medido após o re-julgamento dos 1088:** nenhum valor de
> `pratica` pode passar de **45%** da distribuição. Se passar, o eixo falhou,
> e a correção é de desenho — não se aceita o resultado e segue.

**A taxonomia não caber na literatura.** Dezenove valores escolhidos por
inspeção, não por análise de cluster.

> **Critério de aceite:** `outro` não pode passar de **10%** dos 1088. Acima
> disso, faltam famílias, e as que faltam se descobrem lendo os papers que
> caíram em `outro`.

**Alegações de ganho escassas ou mal normalizadas.** Se quase todo paper cair em
`ganho_eixo = nenhum`, o eixo de avanço do jornal fica vazio e o gráfico não se
sustenta.

> **Critério de aceite:** ao menos **35%** dos 1088 precisam ter `ganho_eixo`
> diferente de `nenhum`. Abaixo disso, ou a extração está mal instruída, ou a
> literatura não alega o que se supôs — nos dois casos o gráfico de avanço sai
> do jornal em vez de ser desenhado sobre dado ralo.

**Sobreposição entre escopos maior que o esperado.** Se muitos papers de agentes
já tiverem entrado por inferência, o volume real do segundo escopo é menor que
os 25/dia medidos — o que é um problema bom, mas precisa ser sabido.

> **Medição:** contar, na primeira execução com os dois escopos, quantos papers
> do escopo de agentes foram cortados por `ja_conhecido`.

---

## 8. Testes que travam o comportamento

Estes são os testes cuja ausência deixaria o sistema quebrado de um jeito
silencioso. Não são a suíte inteira.

1. **Um paper que casa com os dois escopos entra uma vez só**, e fica com
   `inferencia` — a ordem de execução decide.
2. **O segundo escopo não re-julga o que o primeiro gravou**: com o primeiro
   escopo já executado, a lista de papers enviada ao julgador na segunda
   execução não contém nenhum id do primeiro.
3. **`familia` fora do `Literal` é rejeitada** na construção de `Judgment`, do
   mesmo jeito que `runs_on_3090` inválido era.
4. **`compose_day` preserva as duas seções e a ordem** mesmo quando um dos
   escopos devolve radar vazio.
5. **O push do dia respeita 3 por escopo**, e um escopo com 5 candidatos entrega
   3, não 5.
6. **A migração preserva `papers`, `signals` e `repos`** e zera só `judgments`:
   contagens antes e depois.
7. **`citations = None` não dispara o portão de estouro**, e `citations = 0`
   dispara a fórmula normalmente — o teste separa desconhecido de zero.
8. **O casamento de DOI é case-insensitive** — um DOI em caixa baixa vindo da
   API encontra o paper.
9. **`ganho_eixo = nenhum` força `ganho_fator = None`** — combinação
   inconsistente é rejeitada na construção de `Judgment`.
10. **`ganho_fator` negativo ou zero é rejeitado** — fator de melhora é > 0.
11. **`scope` é obrigatório em `upsert_paper`** — sem default, para que um
   chamador novo não grave linha sem escopo silenciosamente.

---

## 9. Decisões travadas

1. **Citações vêm do OpenAlex, não do Semantic Scholar.** Medido: S2 sem chave
   acerta 2 em 6; OpenAlex resolve 50 por requisição em 0,38s sem chave.
2. **`citations` é `int | None`, e `None` não dispara portão.** Não-resolvido
   não é zero.
3. **`ScopeConfig` ganha `name`.** É o que permite gravar o escopo sem mudar a
   assinatura de `run_day`.
4. **`cs.LG` fora do escopo de agentes.** Medido: triplica o volume com RL e
   robótica. Reintroduzir exige re-medir.
5. **`tool retrieval` fora.** Medido: zero papers inéditos.
6. **Primeiro escopo a descobrir fica com o paper.** Ordem: inferência, depois
   agentes. Um paper, uma linha, um escopo.
7. **`PUSH_CAP` continua 3 e continua sendo 3 por escopo.** Não vira campo de
   configuração, não sai do `config.py`.
8. **`render_markdown` não é reaberta.** A composição de dois escopos entra por
   função nova.
9. **`runs_on_3090` é removido, não depreciado.** Sem reprodução de papers, o
   eixo de hardware não tem consumidor.
10. **As linhas antigas de `judgments` são descartadas na migração**, e só elas.
   Cópia do banco antes é pré-condição.
11. **`ganho_fator` só existe quando é razão.** Pontos percentuais de qualidade
   ficam em `ganho_texto` e não viram número plotável. Inventar um fator a
   partir de pp seria fabricar dado.
12. **Os campos de ganho registram alegação, nunca medição**, e todo consumidor
   é obrigado a rotulá-los assim.
13. **`outro` existe na taxonomia** e sua frequência é instrumento de medição, não
   ruído a ser tolerado.
14. **Os critérios de aceite de §7 são gates**, não observações. `pratica` acima
   de 45% num valor, ou `outro` acima de 10%, reprova o resultado.
