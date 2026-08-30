# O bloco de leitura — Spec

**Data:** 2026-08-30
**Estado:** escrita, aguardando revisão
**Depende de:** `docs/2026-08-29-jornal-spec.md` (a página), `docs/2026-08-29-segundo-escopo-spec.md` (taxonomia e ganho)

---

## 1. O problema

A página hoje deixa o leitor deduzir. Ela filtra, ordena, busca e cruza — mas
não afirma nada. Diante de 1088 linhas, "deduzir" na prática significa "ter
tempo e disciplina para procurar", e a maioria das visitas não terá nenhum dos
dois.

O bloco de leitura é um punhado de frases no topo, calculadas do mesmo dado,
que dizem o que o acervo mostra. Ele existe para que a página responda algo
antes de ser interrogada.

### O que torna isso perigoso

Este acervo autoriza muito menos afirmação do que aparenta:

1. **O corpo não é a literatura, é o recorte.** Vinte e nove termos de busca no
   arXiv. Uma família "crescer" pode ser efeito de um termo que casa melhor com
   um jargão que virou moda, e não de mais trabalho sendo feito.
2. **Implementação é proxy.** É busca no GitHub por `in:readme`, com heurística
   declarada para descontar os repositórios dos autores. Repositório sem o ID do
   arXiv no README é invisível.
3. **Ganho é alegação**, extraída do resumo, nunca medida.
4. **A família é rótulo de LLM**, um por paper, sobre uma taxonomia de dezenove
   valores que eu escolhi por inspeção.
5. **O eixo do tempo está contaminado no seed.** A semeadura de 2026-08-29 rodou
   *sem piso de data*: ela trouxe o que o arXiv devolvia por termo, não o que
   foi publicado em cada mês. Contar papers por mês sobre esse recorte mede o
   ranking do arXiv, não a produção da literatura.

Uma frase como *"planejamento de agentes cresceu 40% no trimestre"* seria falsa
por pelo menos três dessas razões ao mesmo tempo, e soaria exatamente igual a
uma verdadeira.

---

## 2. A decisão que organiza tudo

**Cada afirmação tem uma guarda, e afirmação cuja guarda não passa não é
enfraquecida — é omitida.**

O bloco encolhe em vez de hedgear. Um bloco com duas frases sólidas vale mais
que um com seis frases cheias de "pode indicar que". Hedge é o que se escreve
quando não se quer decidir se a afirmação se sustenta; a guarda decide.

### Não-objetivos

**Nada de LLM.** O bloco é aritmética sobre `SiteData`, em função pura, na
mesma fronteira testada do resto do render. Um modelo escrevendo as frases
inventaria correlação com fluência perfeita, e seria indistinguível de cálculo
correto para quem lê. Esta é a decisão mais importante da spec.

**Nada de causa.** Nenhuma frase diz *porque*. O dado suporta "quantos", nunca
"por quê".

**Nada de previsão.** Nenhuma frase diz o que vai acontecer.

**Nada de superlativo sem número.** "A família mais implementada" só existe
como "a família mais implementada, com N de M".

---

## 3. As afirmações, e a guarda de cada uma

Seis tipos. Cada um define o que afirma, o que calcula, e o que precisa ser
verdade para ser emitido.

### 3.1 Concentração

> "Três famílias concentram 61% das implementações independentes do acervo:
> quantização, cache KV e uso de ferramenta."

**Calcula:** soma de `independent_impls` por família, ordenada; o menor conjunto
que passa de 50%.

**Guarda:** o acervo tem ao menos 100 papers **e** ao menos 50 implementações
independentes somadas. Abaixo disso a concentração é ruído de amostra pequena.

**Por que é defensável:** não fala de tempo, não fala de causa, e o proxy de
implementação é o mesmo para todas as famílias — o viés, se existe, é comum.

### 3.2 A fronteira

> "10 papers têm 3 ou mais implementações independentes e menos de 10 estrelas
> somadas."

**Calcula:** contagem com `independent_impls >= 3` e `stars_total < 10`.

**Guarda:** a contagem é maior que zero.

**Por que é a mais importante:** é a tese do projeto virada em número. Se esse
número for perto de zero de forma persistente, a hipótese do radar — que
reimplementação antecede atenção — está errada, e a página passa a dizer isso.

### 3.3 Escassez de sinal

> "Dos 1088 papers do acervo, 936 (86%) não têm nenhuma implementação
> independente."

**Calcula:** contagem com `independent_impls == 0` sobre o total.

**Guarda:** nenhuma. Este número sai sempre.

**Por que sai sempre:** é o contexto que impede todo o resto de ser lido como
mais impressionante do que é. Um leitor que vê "10 na fronteira" sem ver "936
com zero" superestima a densidade do sinal por mais de uma ordem de grandeza.

### 3.4 Cobertura de alegação

> "233 papers (21%) declaram um ganho quantificado no resumo."

**Calcula:** `cobertura_de_ganho`, que já existe.

**Guarda:** nenhuma; sai sempre, com o rótulo de alegação obrigatório da spec
do jornal.

**Papel duplo:** é informação para o leitor e é o número que decide se a seção
de avanço é construída (piso de 35%). Publicá-lo torna essa decisão auditável
em vez de invisível.

### 3.5 O que a taxonomia não pegou

> "94 papers (8,6%) caíram em 'outro': nenhuma das dezoito famílias coube."

**Calcula:** fração de `familia == "outro"`.

**Guarda:** nenhuma; sai sempre.

**Por que é honestidade e não autocrítica:** `outro` é instrumento de medição da
própria taxonomia — está escrito assim na spec do segundo escopo, com gate de
10%. Esconder do leitor a taxa de não-encaixe seria apresentar a taxonomia como
mais ajustada do que é.

### 3.6 Movimento recente

> "Entre os papers re-consultados nos últimos 30 dias, 7 ganharam
> implementação independente."

**Calcula:** papers com duas ou mais observações em `signals` cuja última
`independent_impls` supera a anterior, dentro da janela.

**Guarda — e esta é a mais restritiva:** só é emitida se houver **ao menos 30
dias de execução diária contínua** registrados, e sobre papers com **ao menos
duas observações reais**. O seed é uma observação única e contaminada de
recorte; até a rotina diária acumular histórico, esta frase não existe.

**A afirmação que NÃO fazemos:** "família X cresceu neste trimestre". Contar
papers por mês de publicação sobre o acervo semeado mede o ranking de busca do
arXiv, não a produção da literatura. Essa frase só se torna possível quando o
acervo for majoritariamente formado por coleta diária — e a spec exige que a
condição seja verificada em dado, não presumida pelo calendário.

---

## 4. Cada afirmação é reproduzível

Toda frase emitida carrega o filtro que a reproduz na tabela abaixo.

Concretamente: a frase da fronteira vira um link que aplica ordenação por
`impls` e deixa o leitor conferir os 10. A da concentração vira três links, um
por família.

**Por que isso não é enfeite:** é o que separa o bloco de leitura de um resumo
gerado. Uma afirmação que o leitor pode conferir em dois cliques é verificável;
uma que ele precisa aceitar é autoridade. O projeto inteiro é construído contra
a segunda coisa — a seção "uma técnica, de ponta a ponta" existe pela mesma
razão, um nível abaixo.

---

## 5. Forma

No topo da página, logo abaixo do enquadramento e acima da fronteira.

Prosa, não cartões. Três a seis frases curtas em parágrafo, com os números em
destaque tipográfico. Cartões de métrica convidam a leitura por varredura, e
varredura é o modo em que número sem contexto vira impressão.

Sem emoji, sem adjetivo promocional — a mesma restrição que o julgador carrega.

**Ordem fixa**, e ela é argumentativa: escassez primeiro (3.3), fronteira depois
(3.2), concentração (3.1), cobertura e taxonomia por último (3.4, 3.5),
movimento quando existir (3.6). O leitor precisa saber que a maioria não tem
sinal **antes** de ler quantos estão na fronteira.

---

## 6. Fronteiras de código

```
src/radar/leitura.py     # novo, puro
  afirmacoes(dados: SiteData) -> list[Afirmacao]

@dataclass(frozen=True)
class Afirmacao:
    texto: str            # a frase, já formatada
    filtro: dict | None   # o filtro que a reproduz, ou None
```

`site.py` consome a lista e desenha. Não importa `sqlite3`, `httpx` nem
`anthropic` — o teste de pureza existente passa a cobrir `leitura` também.

Uma função por afirmação, cada uma devolvendo `Afirmacao | None`. A guarda mora
dentro da função que a afirmação pertence, não numa camada de filtro depois —
assim ler a função é ler a condição.

---

## 7. Testes que travam o comportamento

1. **Guarda que não passa devolve `None`**, e a frase não aparece na página —
   um teste por afirmação com guarda.
2. **Acervo pequeno não produz concentração**: 99 papers, nenhuma frase de
   concentração.
3. **Movimento não é emitido sem histórico**: acervo com uma observação por
   paper, nenhuma frase de movimento, mesmo com muitos papers.
4. **Escassez sai mesmo quando é 100%**: acervo em que ninguém tem
   implementação ainda produz a frase.
5. **Nenhuma afirmação contém verbo causal** — lista de proibidos (`porque`,
   `devido`, `graças a`, `por causa`) verificada sobre a saída.
6. **Nenhuma afirmação contém superlativo sem número**: `mais` só aparece
   acompanhado de dígito na mesma frase.
7. **Todo filtro emitido é aplicável**: as chaves batem com os `data-*` que a
   tabela usa, e o valor existe no acervo.
8. **Acervo vazio produz lista vazia**, e a página não desenha a seção.
9. **`leitura` não faz IO**, pelo teste de pureza existente.

---

## 8. Riscos declarados

**A fronteira é fina, e isso é um achado sobre a própria tese do projeto.**
Medido no acervo de 2026-08-29: dos 1088 papers, **936 (86%) não têm nenhuma
implementação independente**, e apenas **10** estão na fronteira (três ou mais
implementações com menos de dez estrelas).

O número que mais incomoda é outro. Entre os 48 papers com três ou mais
implementações independentes, a distribuição de estrelas é:

| estrelas | papers |
|---|---|
| 0 | 3 |
| 1–9 | 7 |
| 10–99 | 13 |
| 100–999 | 17 |
| 1000+ | 8 |

Ou seja: **38 dos 48 papers mais implementados já têm atenção**. A hipótese do
radar — que reimplementação independente antecede atenção, e por isso serve de
sinal precoce — não é sustentada por este recorte. O padrão dominante é o
inverso: implementação acompanha atenção.

Isso não invalida o projeto, e há três explicações concorrentes que este dado
não separa. A primeira é que o seed é um retrato único, sem eixo temporal: ele
não consegue dizer o que veio antes do quê. A segunda é que a busca do GitHub
por `in:readme` acha melhor os repositórios de projetos que já têm tração. A
terceira é que a hipótese está simplesmente errada.

**A spec exige que a página publique esses números mesmo assim.** Um radar que
esconde a evidência contra a própria premissa é exatamente a coisa que ele
existe para não ser. E a frase da fronteira em `0` seria o resultado mais
informativo que este projeto pode produzir sobre si mesmo.

**Os limiares de 3.1 e 3.2 são escolhidos, não derivados.** Cem papers,
cinquenta implementações, três implementações, dez estrelas. Estão declarados
aqui para que sejam discutíveis; não há análise por trás deles, e fingir que há
seria pior que admiti-lo.

**O bloco pode dar sensação de conclusão onde há só contagem.** É por isso que
nenhuma frase fala de causa e todas trazem o denominador.

---

## 9. Decisões travadas

1. **Sem LLM.** O bloco é aritmética em função pura. Um modelo escrevendo as
   frases inventaria correlação com fluência perfeita.
2. **Guarda que não passa omite a frase**, nunca a enfraquece com hedge.
3. **Nenhuma frase afirma causa ou faz previsão.**
4. **Todo número traz o denominador.**
5. **Escassez de sinal sai sempre**, e vem primeiro: é o contexto que impede o
   resto de ser superestimado.
6. **Crescimento por mês de publicação não é afirmado** sobre acervo semeado — a
   condição é verificada em dado, não presumida pelo calendário.
7. **Toda afirmação carrega o filtro que a reproduz.** Verificável em dois
   cliques, não aceita por autoridade.
8. **Prosa, não cartões de métrica.**
9. **Os limiares são escolhidos e declarados como tal.**
10. **A evidência contra a premissa do projeto é publicada como qualquer outra.**
    Medido em 2026-08-29: 38 dos 48 papers mais implementados já têm atenção.
    Esconder isso faria da página propaganda da própria tese.
