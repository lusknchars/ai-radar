# ai-radar

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
