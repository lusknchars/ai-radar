# Radar de Técnicas — Desenho (rascunho, não aprovado)

**Data:** 2026-08-23
**Status:** desenho revisado em 2026-08-27 apos spike de viabilidade.
O spike REFUTOU a escolha de GitHub como fonte primaria. Ver secao "Resultado do spike".

Hub pessoal de notícias sobre engenharia de IA, focado em técnicas eficazes que ainda
não estouraram. Composição deliberada com a bancada de quantização
(`~/quant-bench/`), cujo spec tem uma lista de leitura por fase.

## Decisões já tomadas

| Decisão | Escolha |
|---|---|
| Sinal primário de "vale a pena" | **Implementação** — alguém já se deu ao trabalho de construir |
| Escopo temático | **Estreito**: inferência, eficiência, sistemas, quantização, serving, kernels |
| Entrega | **Telegram** (push curto) + **markdown versionado no repo** (histórico grepável) |
| Onde roda | GitHub Actions, cron diário. Repo é banco e arquivo. Zero servidor. |

## O problema central que o desenho resolve

"Não aclamado pelo público" não é sinal por si só. arXiv cs.LG e cs.CL somam centenas
de papers por dia e a maioria do que é ignorado é ignorado pelo motivo certo. Filtrar
por baixo engajamento entrega o mesmo firehose com passos extras.

O proxy de qualidade escolhido é implementação independente: implementar custa caro,
ninguém reimplementa por hype.

## Fluxo

```
arXiv (cs.LG, cs.CL, cs.DC, cs.AR)  ─┐
GitHub (repos novos citando arXiv)  ─┤
Hugging Face (modelos/datasets)     ─┼─→  item canônico (arXiv ID)
OpenReview (submissões + reviews)   ─┤        │
Hacker News / Semantic Scholar      ─┘        ▼
        (só como DENOMINADOR)            sinal + julgamento
                                              │
                                    ┌─────────┴─────────┐
                              Telegram (3 itens)   repo/radar/*.md
```

GitHub é fonte **primária**, não enriquecimento do arXiv. É o que permite pegar paper
antigo ressuscitando — alguém reimplementando um paper de 2023 hoje é evidência de que
a técnica sobreviveu ao ciclo de hype, sinal frequentemente melhor que lançamento novo.

## O sinal

Por item: `implementations` (repos distintos), `independent` (donos diferentes dos
autores do paper), `velocity` (novos repos em 14 dias), `attention` (estrelas + HN +
citações).

Score é **razão, não soma**: `f(independent, velocity) / f(attention)`.

Implementação independente no numerador porque custa caro. Atenção no denominador
porque é exatamente o que você já veria sem o hub. `independent` pesa mais que
`implementations` — é o que evita o falso positivo mais comum, os próprios autores
publicando três repos.

## Estado

SQLite versionado no repo, com histórico de score por item. Compra duas coisas: não
repetir, e reportar **delta em vez de valor absoluto**. "Saiu de 2 para 9
implementações em três semanas" carrega mais informação que "tem 9 implementações", e
é impossível de detectar sem memória.

## Entrega

**Teto rígido de 3 itens no Telegram.** Não é orientação, é limite. Se o pipeline achar
40 candidatos, manda 3 e o resto vai pro arquivo. Esse teto é o único mecanismo que
impede a coisa de virar pasta não lida — o modo de falha real deste tipo de projeto não
é técnico.

Cada item no push: uma linha do que é, o número que justifica, e o veredito
**roda na 3090** (`sim` / `sim com ressalva` / `não, e por quê`). Ampere sem FP8,
24GB, PCIe 4.0. Essa classificação só faz sentido por causa do escopo estreito, e é o
que liga o radar direto ao quant-bench.

O markdown no repo leva tudo: todos os candidatos, números crus, e o que foi cortado.
Nada de truncar em silêncio.

## Resultado do spike (2026-08-27)

Executado antes de escrever qualquer pipeline. Tres achados.

**CONFIRMADO — o sinal de implementacao e obtenivel e barato.**
`GET /search/repositories?q="2210.17323"+in:readme` devolve 104 repositorios para o
paper do GPTQ. A distincao autor/independente e visivel direto no resultado:
`IST-DASLab/gptq` e o repo dos proprios autores, enquanto `fpgaminer/GPTQ-triton`,
`davisyoshida/jax-gptq` e `hjchen-thu/codebear` sao reimplementacoes independentes.
E exatamente o numerador que o score precisa.

**REFUTADO — GitHub como fonte primaria de descoberta.**
A busca por palavra-chave em README e ruidosa demais. `"arxiv.org/abs" in:readme
quantization created:>2026-06-01` devolve 590 repos, e ordenados por estrela vem
`RedKnot`, `muscriptor`, `Agents-A1`, `TaoMate` — repos gerais de IA que apenas
mencionam quantizacao de passagem. Ordenar por estrela ainda traz o oposto do que
queremos, que e baixa atencao. O GitHub nao discrimina escopo; ele so confirma
implementacao de um paper que voce ja identificou.

**CONFIRMADO — arXiv API serve para descoberta, com uma pegadinha.**
Funciona apenas em HTTPS e com User-Agent explicito; em HTTP devolve 301 com corpo
vazio, e como raise_for_status() nao levanta em 3xx e o httpx nao segue redirect por
padrao, o chamador recebe zero byte e nenhum erro. `cat:cs.LG AND abs:quantization` da 4565 resultados, com os mais
recentes do dia anterior. Filtragem por categoria mais termo no abstract e precisa o
suficiente para o escopo estreito.

### Arquitetura corrigida

Inverte-se o fluxo: **arXiv descobre, GitHub pontua.**

1. arXiv API traz os papers do dia nas categorias e termos do escopo (preciso)
2. Para cada candidato, uma busca no GitHub conta implementacoes e checa independencia
3. O SQLite guarda todo paper ja visto e re-consulta a contagem periodicamente

O ponto 3 preserva o sinal de ressurreicao sem precisar de descoberta pelo GitHub:
paper antigo voltando a ser implementado aparece como **delta numa entrada que ja
existe no banco**, nao como descoberta nova. Mesmo sinal, mecanismo mais limpo.

### Orcamento de rate limit

GitHub search sem autenticacao: 10 req/min, com reset por minuto. Com token: 30/min.
Trinta candidatos por dia a uma busca cada = 3 minutos de relogio sem token, 1 minuto
com token. Irrelevante para um cron diario. arXiv nao impoe limite rigido, mas pede
intervalo de ~3s entre chamadas.

## Pendencias de aprovacao

1. Teto de 3 itens no push — numero chutado, pode ser sobrescrito.
2. ~~GitHub como fonte primaria~~ — RESOLVIDO pelo spike: arXiv descobre, GitHub pontua.

## Não decidido ainda

Qual LLM faz o julgamento e o resumo, e o custo diário disso. Volume esperado é baixo
(escopo estreito), então deve ser barato, mas não foi dimensionado.
