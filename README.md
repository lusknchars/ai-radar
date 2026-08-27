# ai-radar

## Operação

Roda diariamente às 09:00 UTC via GitHub Actions. Para rodar à mão sem enviar push:

    python -m radar.cli --dry-run

O dry-run escreve o markdown do dia, mas não envia o push e **não deixa nada
gravado no banco de verdade** — ele lê o estado real e escreve numa cópia
descartável. O ensaio não consome os papers da primeira execução real.

### Segredos necessários

| Segredo | Obrigatório | Para quê |
|---|---|---|
| `ANTHROPIC_API_KEY` | sim | julgamento e resumo |
| `TELEGRAM_BOT_TOKEN` | sim | push diário |
| `TELEGRAM_CHAT_ID` | sim | destino do push |
| `GH_TOKEN` | não | eleva o rate limit de busca de 10 para 30 req/min |

Sem `GH_TOKEN` o pipeline respeita os 10 req/min esperando 6 s entre buscas; com
ele, 2,5 s. O intervalo sai da presença do segredo, não de um valor fixo.

**Segredos de Actions não viajam com o repositório.** Se o repo for movido,
renomeado ou recriado, todos precisam ser repostos — e a falha aparece em
runtime, não no push.

### Calibração pendente

`RADAR_BROKE_OUT_STARS` (1000), `RADAR_BROKE_OUT_CITATIONS` (200) e
`RADAR_SCORE_FLOOR` (0.0) são chutes. As duas primeiras semanas rodam com o piso
em zero, e a seção de cortes de cada digest registra o que foi barrado por qual
limiar. Calibrar depois de observar a distribuição real.

O piso é o último valor **rejeitado**: um score igual ao piso é cortado. Com o
piso em zero isso barra exatamente o paper com zero implementações
independentes — que é o paper sem nenhum sinal, num produto cuja tese é que
implementação independente é o sinal.
