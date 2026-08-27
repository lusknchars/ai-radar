# Re-consulta de sinal — Spec

**Data:** 2026-08-28
**Emenda a:** `docs/2026-08-27-radar-spec.md` §6 (Re-consulta) e §4 (orçamento)
**Status:** desenho aprovado, aguardando plano de implementação

---

## 1. Por que existe

A tabela `signals` é append-only por um motivo declarado: um paper antigo voltando a ser implementado aparece como delta entre duas linhas. Hoje esse motivo não se realiza. Nada re-consulta o sinal de papers já no banco, então nenhum paper acumula uma segunda observação, e a detecção de ressurreição — o argumento inteiro do desenho append-only — está dormente.

`stalest_papers()` e `known_ids()` existem, são testados, e não têm chamador em produção. Esta spec liga o que já foi construído.

O caso que motiva: o GPTQ é de outubro de 2022 e continuava ganhando implementações independentes em 2026. Um radar que só olha o que saiu esta semana nunca o encontraria.

---

## 2. O que "ressurreição" significa

**A primeira entrega de um paper que já era conhecido.**

O paper foi descoberto, teve o sinal gravado, e não foi entregue: ficou abaixo do piso de score, ou perdeu as três vagas para candidatos melhores. Semanas ou meses depois a re-consulta encontra o sinal maior, ele passa a caber no top 3, e entra no push **pela primeira vez** — com a redação de delta, porque o histórico tem duas ou mais observações.

**A regra de entrega única não tem exceção.** `deliveries` continua sendo consultado antes de montar o push, e um paper já entregue nunca volta.

A leitura alternativa — devolver ao push um paper já visto porque o sinal explodiu depois — foi considerada e recusada. Exigiria um limiar de crescimento e um período de carência, ambos sem como calibrar, num projeto que já carrega três limiares declarados como dívida.

Consequência aceita: se um paper for entregue cedo e explodir depois, você não é avisado de novo. Você já o viu.

---

## 3. Onde entra no pipeline

```
1. descoberta (arXiv)              papers do dia
2. filtro de já conhecidos         cuts["ja_conhecido"]
3. julgamento LLM                  só os novos
4. sinal do GitHub                 só os novos     ← prioridade de orçamento
5. RE-CONSULTA                     stalest_papers(limit=N), o que sobrar
6. evaluate()                      novos + re-consultados, mesma função
7. radar                           top 3, excluindo já entregues
8. feed                            candidatos NOVOS − radar
```

A ordem é a que a §4 do spec principal já manda: descoberta nova tem prioridade, e a re-consulta é a primeira coisa a ser cortada quando o orçamento acaba.

---

## 4. Elegibilidade

Um paper re-consultado **entra no radar** se passar o portão de atenção, ficar acima do piso de score, e nunca ter sido entregue. É pontuado pela mesma `evaluate()` que os novos — não há segunda fórmula.

Um paper re-consultado **nunca entra no feed**. O feed responde "o que saiu hoje", e um paper de 2022 não saiu hoje. Isto é uma restrição do código, não uma consequência acidental: `feed` é calculado sobre os candidatos novos, e re-consultados são acrescentados apenas ao conjunto elegível ao radar.

A redação de delta sai de graça. `signal_delta` já devolve não-nulo quando há duas ou mais observações, e `render._numbers_line` já escolhe a redação de delta quando ela existe. Nenhuma das duas funções muda.

---

## 5. Re-consulta não gasta token

Um paper re-consultado que chega ao push precisa de `technique`, `summary`, `runs_on_3090` e `rationale`. Ele já tem: foram gravados quando o paper foi descoberto. `store.latest_judgment()` existe e é testado.

**Re-usar, nunca re-julgar.** Isto não é otimização — é o que torna o teto de 30 barato. Re-julgar 30 papers por dia multiplicaria a conta do LLM por quatro para produzir texto que já está no banco.

Se um paper re-consultado não tiver julgamento gravado (banco de uma versão anterior), ele é cortado em vez de re-julgado, sob o motivo **`reconsulta_sem_julgamento`** — deliberadamente distinto do `sem_julgamento` dos novos.

Os dois motivos têm causas e consertos diferentes: nos novos significa que o LLM falhou, e a ação é olhar o log do lote; na re-consulta significa uma linha antiga sem julgamento, e a ação é decidir se vale re-julgar retroativamente. Conflar os dois num contador só produziria um número que não diz o que fazer.

---

## 6. Orçamento

`RECHECK_LIMIT`, default **30**, sobrescrevível por `RADAR_RECHECK_LIMIT`.

A re-consulta roda depois dos novos e usa `stalest_papers(limit=RECHECK_LIMIT)` — os vistos há mais tempo primeiro, que é a ordenação que a função já implementa e testa. Cada re-consulta é uma busca no GitHub, sujeita ao mesmo intervalo entre chamadas.

Uma falha de sinal num paper re-consultado não derruba o dia. Vale a mesma guarda dos novos: conta como `sinal_indisponivel` e o dia segue.

**Todo paper re-consultado tem `touch_checked` atualizado, inclusive quando o sinal falha.** Sem isso a rotação não avança: `stalest_papers` devolveria os mesmos trinta papers todo dia, para sempre, e os demais nunca seriam re-checados. Marcar mesmo na falha é deliberado — um paper cuja busca falhou hoje vai para o fim da fila e volta na próxima volta, em vez de travar a rotação tentando o mesmo paper indefinidamente.

### A limitação, declarada

O período de rotação cresce com o banco. Com 30 por dia e 3000 papers guardados, cada paper volta a cada 100 dias — tarde demais para pegar uma ressurreição enquanto ela importa.

Isto é aceito conscientemente. Nos primeiros meses o banco é pequeno e 30 por dia cobre tudo. Quando incomodar, o upgrade é cadência decrescente: paper recente re-checado com frequência, paper antigo raramente mas nunca zero. Não se constrói agora porque exigiria uma política de cadência com três parâmetros que não há como calibrar antes de ver dados.

---

## 7. O que aparece no markdown

Seção nova, `## Re-consulta`, com duas informações: quantos papers foram re-checados, e a lista **apenas dos que se moveram**.

```markdown
## Re-consulta

30 papers re-consultados. 2 com movimento:

- 2210.17323 — 2 → 9 impls independentes em 21 dias — score 0.11 → 0.40
- 2305.14314 — 1 → 4 impls independentes em 60 dias — score 0.08 → 0.22
```

Silêncio para os 28 que não mudaram. Listar papers cujo sinal está igual é ruído, e o teto de legibilidade do digest é a restrição de produto mais forte deste projeto.

Quando nada se moveu, a seção diz isso explicitamente — `30 papers re-consultados, nenhum com movimento` — pela mesma razão que a seção de Cortes é obrigatória mesmo vazia: silêncio ambíguo faz parecer que o trabalho não foi feito.

---

## 8. Testes que travam o comportamento

- Paper re-consultado que passa o piso entra no radar, com a redação de delta.
- Paper re-consultado **nunca** aparece no feed, mesmo quando não entra no radar.
- Paper já entregue não volta ao push, mesmo com sinal maior. A §6 intacta.
- Re-consulta reusa o julgamento gravado e **não** chama `judge_all`.
- Paper re-consultado sem julgamento gravado vira corte `reconsulta_sem_julgamento`, distinto
  do `sem_julgamento` dos novos.
- `touch_checked` é atualizado em todo paper re-consultado, **inclusive** quando o sinal falha,
  para que a rotação avance em vez de repetir os mesmos trinta indefinidamente.
- Falha de sinal num re-consultado conta como `sinal_indisponivel` e o dia segue.
- O teto `RECHECK_LIMIT` é respeitado, e a re-consulta roda depois dos novos.
- A seção `## Re-consulta` aparece mesmo quando nada se moveu.

---

## 9. Decisões travadas

| Decisão | Escolha | Motivo |
|---|---|---|
| Significado de ressurreição | primeira entrega de paper já conhecido | preserva a regra de entrega única; sem limiar novo |
| Re-consultado no feed | **não** | feed responde "o que saiu hoje" |
| Julgamento | reusar o gravado, nunca re-julgar | mantém o teto de 30 barato |
| Sem julgamento gravado | corte `sem_julgamento` | o custo não escapa em silêncio |
| Limite | teto fixo de 30/dia, mais antigo primeiro | usa `stalest_papers` que já existe e é testado |
| Rotação lenta com banco grande | aceita e declarada | backoff é o upgrade, com dados |
| Pontuação | a mesma `evaluate()` | uma fórmula só, sem caminho paralelo |
