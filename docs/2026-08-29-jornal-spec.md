# O jornal — Spec

**Data:** 2026-08-29
**Estado:** aprovado, aguardando plano
**Depende de:** `docs/2026-08-29-segundo-escopo-spec.md` (taxonomia e campos de ganho)
**Referência de forma:** `vetto.ai/companies/computer-anthology-terminal-tasks.html`

---

## 1. O que é, e o que explicitamente não é

Uma página que estabelece o acervo do ai-radar: o que a literatura de inferência
eficiente e de harness de agentes produziu, agrupado por família, ordenado pela
fronteira entre o que foi construído e o que foi olhado.

O leitor é um engenheiro de AI/ML com infra pequena que precisa decidir o que
adotar. Não é um pesquisador escolhendo o que ler.

### A honestidade que a forma exige

A página de referência evidencia avanço de modelo porque **mede**: pass rate,
28 configurações, intervalo de confiança bootstrap. Este projeto não mede nada —
não roda os papers, não tem infraestrutura para isso, e não vai ter.

O que este jornal pode evidenciar é **difusão e alegação**: quantas
implementações independentes uma técnica atraiu, e quanto o paper alega
entregar. As duas coisas são reais e nenhuma é benchmark.

> **Regra dura:** todo lugar onde `ganho_fator` aparece — eixo, tooltip,
> legenda, tabela — carrega o rótulo **"alegado pelos autores, não verificado"**.
> Um gráfico de ganhos alegados que se apresenta como resultado medido é
> exatamente o hype de que este projeto existe para fugir. Não há exceção por
> falta de espaço: se não couber o rótulo, corta-se o gráfico, não o rótulo.

### Não-objetivos

Reproduzir o layout da referência. A estrutura inspira; o conteúdo é outro.

Ser um leitor de papers. Ele não exibe abstracts inteiros nem PDFs.

Ser aplicação. Sem backend, sem banco no cliente, sem estado de usuário.

---

## 2. Tecnologia, e por quê

**Uma página HTML autocontida, sem framework, sem dependência externa, com os
gráficos gerados em SVG por Python.**

Três razões, em ordem de peso:

1. **O gráfico vira código testado.** A camada de render deste projeto é pura —
   não importa `httpx`, `anthropic` nem `sqlite3`, e por isso é a parte mais
   coberta por teste do repositório. Gerar SVG no servidor mantém o gráfico
   dentro dessa fronteira: um teste afirma que o ponto do paper X está na
   coordenada Y. Biblioteca de gráfico no cliente joga isso fora e torna o
   gráfico inauditável.
2. **A página funciona com JS desligado**, e o conteúdo é indexável.
3. **Controle visual total.** Identidade é decisão, e biblioteca de gráfico
   entrega o default dela.

A interatividade necessária é pequena e não justifica o custo acima: a troca de
eixo X são **três SVGs pré-renderizados trocados por umas quinze linhas de JS
puro**, e o filtro da tabela é `hidden` em linha. Nada disso precisa de runtime.

Se um dia a página pedir interação real — zoom, seleção, cruzamento ao vivo — a
portabilidade existe e o custo de ter esperado é zero.

### Onde mora

`site/index.html`, publicado no GitHub Pages pelo **deploy via Actions**
(`upload-pages-artifact` + `deploy-pages`), não pelo modo "branch + pasta". O
modo por pasta só aceita a raiz ou `/docs`, e `/docs` já é das specs.

O workflow diário que já existe passa a gerar a página e publicá-la na mesma
execução. Zero infra nova, zero segredo novo.

---

## 3. Estrutura da página

Ordem de cima para baixo. Cada seção declara de onde vem o dado.

### 3.1 Cabeçalho

Título, data da última execução, e três números do acervo: papers, famílias
representadas, implementações independentes somadas. Âncoras para as seções.

*Fonte:* contagens de `papers`, `judgments`, `signals`.

### 3.2 Enquadramento

Dois parágrafos fixos, escritos à mão, versionados no repositório: o que o radar
mede, e o que ele deliberadamente não mede. É o contrato com o leitor e não é
gerado.

### 3.3 A fronteira — o gráfico central

Um scatter. **Y: implementações independentes.** **X: alternável entre três
métricas** — estrelas totais, dias desde a publicação, implementações totais.
Cor por família. Um ponto por paper.

**Citações ficam de fora do eixo, mesmo depois de ligadas.** O OpenAlex passa a
preencher o campo de verdade (spec do segundo escopo, §4-bis), mas o acervo é de
papers recentes: dos 25 mais antigos, 8 têm citação e o resto tem zero legítimo.
Um eixo em que a esmagadora maioria dos pontos empilha no zero não separa nada.
Citação aparece **na tabela e na fórmula de atenção**, não como eixo. Quando o
acervo envelhecer o bastante para o eixo discriminar, ele entra.

Papers com `citations = None` — não resolvidos no OpenAlex — aparecem na tabela
como **"—", nunca como zero**.

É o análogo direto do leaderboard da referência: lá, capacidade contra recurso
gasto; aqui, **o que foi construído contra o quanto já se olhou**. A região
interessante é a mesma nos dois casos — alto em Y, baixo em X.

A curva de score (`sinal / (1 + atenção)`) é desenhada como isolinha, e o portão
de estouro (1000 estrelas, 200 citações) como região sombreada e rotulada. Quem
olha entende, sem ler documentação, por que um paper muito citado não aparece no
radar.

*Fonte:* `signals` × `judgments.familia`. Três SVGs, um por métrica de X.

### 3.4 O avanço alegado

**X: mês de publicação. Y: `ganho_fator`, escala logarítmica.** Cor por família,
forma por `ganho_eixo`. Só entram papers com `ganho_fator` não nulo.

Uma linha de mediana por família por trimestre, desenhada apenas onde houver ao
menos cinco papers no trimestre — abaixo disso a mediana é ruído com aparência de
tendência.

O rótulo de §1 fica no título do gráfico, não numa nota de rodapé.

*Fonte:* `judgments.ganho_fator`, `ganho_eixo`, `papers.published`.

**Se o critério de aceite da spec anterior reprovar** — menos de 35% dos papers
com ganho declarado — **esta seção não é construída.** Gráfico sobre dado ralo é
pior que gráfico ausente.

### 3.5 As famílias no tempo

Volume por família por mês, em pequenos múltiplos: dezenove mini-gráficos de
mesma escala, em grade. Pequenos múltiplos e não área empilhada, porque a
pergunta é "esta família está crescendo?" e não "qual fatia do total ela é".

*Fonte:* `judgments.familia` × `papers.published`.

### 3.6 A tabela

Uma linha por paper: título, família, prática, implementações independentes,
estrelas, ganho alegado, link para o arXiv. Ordenada por score.

Dois filtros, ambos por `hidden` em linha, sem estado e sem URL: família e
prática. O filtro de prática é o primário — é ele que responde "o que eu adoto".

*Fonte:* junção completa.

### 3.7 Uma técnica, de ponta a ponta

O paper de maior score do dia, aberto: resumo completo, os repositórios
encontrados com dono e estrelas, **qual regra de autoria classificou cada um
como independente ou não**, e o histórico de sinal se houver mais de uma
observação.

É a seção que torna o número auditável. Sem ela, "3 implementações
independentes" é fé.

*Fonte:* `repos`, `repos.is_author_reason`, `signal_history`.

### 3.8 O que ficou de fora

Os cortes do dia com contagem por motivo — `abaixo_do_piso`, `ja_estourou`,
`ja_conhecido`, `sem_julgamento` —, e quantos papers foram re-consultados.

A restrição global do projeto é que todo corte seja contado e chegue ao leitor.
A página herda essa restrição.

*Fonte:* `DayResult.cuts`.

---

## 4. Identidade visual

Decisões travadas, para que a página não saia com cara de default:

- **Uma família tipográfica só**, e ela é a **pilha de fontes do sistema** — a
  página declara zero dependência externa, e uma fonte remota seria uma. Peso
  faz a hierarquia; sem tipo display, sem segunda família decorativa.
- **Paleta contida:** um fundo, um texto, uma cor de acento, e uma escala
  categórica de dezenove passos usada **exclusivamente** nas famílias. Cor não
  significa nada além de família em lugar nenhum da página.
- **Tema claro e escuro** por `prefers-color-scheme`, com os tokens definidos em
  `:root` e redefinidos no bloco escuro. O SVG herda `currentColor` nos eixos.
- **Densidade alta, respiro entre seções.** Tabela densa, seções separadas.
- **Sem emoji.** Sem adjetivo promocional em texto gerado — a mesma restrição
  que o julgador já carrega.

---

## 5. Fronteiras de código

```
render_site(dados: SiteData) -> str     # HTML completo, string, sem IO
render_scatter(pontos, x_metrica) -> str   # SVG, string, sem IO
render_pequenos_multiplos(series) -> str   # SVG, string, sem IO
```

Todas puras. Nenhuma importa `sqlite3`, `httpx` ou `anthropic`. A coleta do
`SiteData` mora no `store` e no CLI; o desenho não sabe de onde o dado veio.

`SiteData` é um dataclass congelado montado por uma função de leitura nova em
`store.py`. O jornal **não** ganha acesso ao `Store` — recebe dado pronto, pelo
mesmo contrato que `render_markdown` já segue.

---

## 6. Testes que travam o comportamento

1. **`render_site` não importa IO.** Teste de importação, como já existe para
   `scoring`, `authorship` e `render`.
2. **Um ponto conhecido cai na coordenada esperada** no SVG do scatter — a
   projeção é aritmética e é testável.
3. **A escala logarítmica não recebe zero nem negativo**: um `ganho_fator`
   inválido não pode gerar SVG com coordenada `NaN`.
4. **A mediana por trimestre não é desenhada abaixo de cinco papers.**
5. **O rótulo "alegado pelos autores, não verificado" está presente** sempre que
   houver um `ganho_fator` na página. Este teste é o que impede a regra de §1 de
   ser perdida numa refatoração.
6. **Acervo vazio gera página válida**, com as seções dizendo que não há dado —
   não uma exceção e não um HTML quebrado.
7. **A seção de avanço some quando a cobertura de ganho fica abaixo de 35%.**
8. **Todo paper da tabela tem link de arXiv resolvível** a partir do `arxiv_id`
   canônico, sem sufixo de versão.

---

## 7. Decisões travadas

1. **SVG gerado em Python, sem biblioteca de gráfico.** O gráfico entra na
   fronteira testada do projeto; biblioteca no cliente o tiraria dela.
2. **Sem framework e sem build step.** A página é um arquivo.
3. **Citações fora dos eixos** enquanto o acervo for jovem demais para o eixo
   discriminar; na tabela e na fórmula, sim.
4. **`None` de citação é renderizado como "—", nunca como zero.**
5. **Fonte do sistema**, para que "sem dependência externa" seja literal.
6. **GitHub Pages por Actions**, não por branch e pasta — `/docs` é das specs.
7. **Uma página só.** As edições diárias continuam em markdown em `radar/`; o
   jornal é o acervo com o dia no topo.
8. **Cor significa família, e só.** Em nenhum gráfico a cor codifica outra coisa.
9. **O rótulo de alegação é inegociável** e tem teste próprio.
10. **A seção de avanço é condicional ao dado**, não obrigatória.
11. **A camada de render continua pura.** O jornal recebe `SiteData`, nunca o
   `Store`.
