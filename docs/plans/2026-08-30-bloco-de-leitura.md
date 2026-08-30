# O Bloco de Leitura — Plano de Implementação

> **Para trabalhadores agênticos:** SUB-SKILL OBRIGATÓRIA: use
> superpowers:subagent-driven-development (recomendado) ou
> superpowers:executing-plans para implementar tarefa a tarefa. Os passos usam
> caixas (`- [ ]`) para rastreio.

**Objetivo:** um punhado de frases no topo do jornal, calculadas do mesmo dado,
que dizem o que o acervo mostra — cada uma com uma guarda que decide se ela
existe, e com o filtro que permite ao leitor conferi-la em dois cliques.

**Arquitetura:** um módulo puro novo, `leitura.py`, com uma função por
afirmação devolvendo `Afirmacao | None`. A guarda mora dentro da função a que
pertence, para que ler a função seja ler a condição. `site.py` consome a lista e
desenha; nada aqui gera texto por LLM.

**Stack:** Python 3.12, `pytest`. Zero dependência nova.

**Spec:** `docs/2026-08-30-bloco-de-leitura-spec.md`

---

## Restrições globais

**Git exige aprovação por ação.** Nenhum `git add`, `git commit` ou `git push`
sem aprovação explícita do Lucas para aquela ação. Os passos de commit são
propostas.

**Sem trailer de co-autoria.** Mensagens em português, imperativo, sem emoji.

**A suíte tem 343 testes e nenhum pode quebrar.** Cada tarefa termina verde.

**NADA DE LLM.** O bloco é aritmética em função pura. Um modelo escrevendo as
frases inventaria correlação com fluência perfeita, indistinguível de cálculo
correto para quem lê. Se alguma tarefa parecer pedir geração de texto, o plano
está sendo mal lido.

**Guarda que não passa OMITE a frase**, nunca a enfraquece com hedge. O bloco
encolhe em vez de ficar vago.

**Nenhuma frase afirma causa nem faz previsão.** Nenhum superlativo sem número
na mesma frase. Todo número traz o denominador.

**`leitura.py` não importa `sqlite3`, `httpx` nem `anthropic`.** O teste de
pureza existente (`test_o_site_data_nao_faz_io`) passa a cobri-lo.

**Depois de qualquer mutação, restaurar E limpar `__pycache__`.** Uma mutação
que troca `5` por `1` preserva o tamanho do arquivo e o Python reusa o bytecode
velho — aconteceu em 2026-08-30 e custou um commit com a suíte vermelha.

**Ambiente:** `/Users/luskoliveira/.pyenv/versions/3.12.3/bin/python`, testes com
`PYTHONPATH=src <python> -m pytest`. Não rodar `pip install`.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Tarefas |
|---|---|---|
| `src/radar/leitura.py` | **novo** — `Afirmacao` e uma função por frase | 1-6 |
| `src/radar/site_data.py` | dois campos para a frase de movimento | 6 |
| `src/radar/store.py` | calcular esses dois campos | 6 |
| `src/radar/site.py` | desenhar o bloco e ligar os filtros | 8 |

---

## Tarefa 1: `Afirmacao` e o esqueleto

**Arquivos:** Criar `src/radar/leitura.py`. Teste: `tests/test_leitura.py`.

**Interfaces:**
- Produz: `Afirmacao(texto: str, filtro: dict | None)`,
  `afirmacoes(dados: SiteData) -> list[Afirmacao]`
- Consumido por: tarefas 2 a 8.

**A ordem é argumentativa, não estética:** escassez primeiro, fronteira depois,
concentração, cobertura, taxonomia, movimento por último. O leitor precisa saber
que a maioria não tem sinal **antes** de ler quantos estão na fronteira.

- [ ] **Passo 1: escrever o teste que falha**

```python
# tests/test_leitura.py
from radar.leitura import Afirmacao, afirmacoes


def test_a_afirmacao_carrega_texto_e_filtro():
    a = Afirmacao(texto="x", filtro={"familia": "cache_kv"})
    assert a.filtro["familia"] == "cache_kv"


def test_afirmacao_sem_filtro_e_valida():
    assert Afirmacao(texto="x", filtro=None).filtro is None


def test_acervo_vazio_produz_lista_vazia(dados_vazio):
    assert afirmacoes(dados_vazio) == []


def test_a_leitura_nao_faz_io():
    import radar.leitura as m
    fonte = open(m.__file__, encoding="utf-8").read()
    for proibido in ("import sqlite3", "import httpx", "import anthropic"):
        assert proibido not in fonte
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_leitura.py -v`
Esperado: FAIL com `ModuleNotFoundError: No module named 'radar.leitura'`

- [ ] **Passo 3: implementar**

```python
# src/radar/leitura.py
"""O bloco de leitura: o que o acervo mostra, em frases calculadas.

ARITMETICA, NUNCA GERACAO. Um LLM escrevendo estas frases inventaria
correlacao com fluencia perfeita, e seria indistinguivel de calculo correto
para quem le. Esta e a decisao que organiza o modulo inteiro.

Cada afirmacao tem uma guarda, e guarda que nao passa OMITE a frase em vez de
enfraquece-la com hedge. Um bloco com duas frases solidas vale mais que um com
seis cheias de "pode indicar que".
"""
from __future__ import annotations

from dataclasses import dataclass

from .site_data import SiteData


@dataclass(frozen=True)
class Afirmacao:
    texto: str
    filtro: dict | None = None      # o filtro que reproduz a frase na tabela


def afirmacoes(dados: SiteData) -> list[Afirmacao]:
    """Ordem ARGUMENTATIVA, nao estetica.

    Escassez vem primeiro porque e o denominador de tudo: quem le "10 na
    fronteira" sem ter lido "936 com zero" superestima a densidade do sinal
    por mais de uma ordem de grandeza.
    """
    if not dados.pontos:
        return []
    candidatas = (
        _escassez(dados),
        _fronteira(dados),
        _concentracao(dados),
        _cobertura(dados),
        _taxonomia(dados),
        _movimento(dados),
    )
    return [a for a in candidatas if a is not None]
```

Com as seis funções devolvendo `None` por enquanto — as tarefas 2 a 6 as
preenchem uma a uma.

- [ ] **Passo 4: rodar a suíte**

Run: `PYTHONPATH=src <python> -m pytest -q`
Esperado: 347 passed

- [ ] **Passo 5: propor commit**

```bash
git add src/radar/leitura.py tests/test_leitura.py
git commit -m "feat: esqueleto do bloco de leitura"
```

---

## Tarefa 2: escassez de sinal

**Arquivos:** Modificar `src/radar/leitura.py`. Teste: `tests/test_leitura.py`.

**Sem guarda: esta frase sai sempre.** Ela é o contexto que impede todo o resto
de ser lido como mais impressionante do que é. Medido em 2026-08-29: 936 de
1088 papers (86%) sem nenhuma implementação independente.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_a_escassez_traz_contagem_e_denominador(acervo):
    a = _so(afirmacoes(acervo), "não têm")
    assert "3 de 5" in a.texto
    assert "60%" in a.texto


def test_a_escassez_sai_mesmo_quando_e_cem_por_cento(acervo_todo_zerado):
    """Acervo em que ninguem implementou nada ainda produz a frase: e o
    resultado mais informativo possivel sobre o estado do acervo."""
    assert _so(afirmacoes(acervo_todo_zerado), "não têm") is not None


def test_a_escassez_sai_mesmo_quando_e_zero(acervo_todo_implementado):
    a = _so(afirmacoes(acervo_todo_implementado), "não têm")
    assert "0 de" in a.texto


def test_a_escassez_vem_primeiro(acervo):
    assert "não têm" in afirmacoes(acervo)[0].texto
```

- [ ] **Passo 2: rodar e confirmar que falha**

Run: `PYTHONPATH=src <python> -m pytest tests/test_leitura.py -v -k escassez`
Esperado: FAIL — `_escassez` devolve `None`.

- [ ] **Passo 3: implementar**

```python
def _escassez(d: SiteData) -> Afirmacao | None:
    """Sem guarda, de proposito: esta frase sai sempre.

    E o denominador de todas as outras. Um leitor que ve "10 na fronteira" sem
    ter visto "936 com zero" superestima a densidade do sinal por mais de uma
    ordem de grandeza.
    """
    zerados = sum(1 for p in d.pontos if p.independent_impls == 0)
    total = len(d.pontos)
    return Afirmacao(
        # `{z} de {total}` e nao `Dos {total}, {z}`: o teste de denominador
        # da Tarefa 7 procura " de " ou " das ", e a segunda forma nao casa.
        # A verificacao do plano pegou isso antes de virar codigo.
        texto=f"{zerados} de {total} papers do acervo "
              f"({zerados / total:.0%}) não têm nenhuma implementação "
              f"independente.",
        filtro=None,
    )
```

- [ ] **Passo 4 e 5:** rodar a suíte (351 passed), propor commit.

---

## Tarefa 3: a fronteira

**Arquivos:** Modificar `src/radar/leitura.py`. Teste: `tests/test_leitura.py`.

**É a tese do projeto virada em número.** Se ficar perto de zero de forma
persistente, a hipótese — que reimplementação antecede atenção — está errada, e
a página passa a dizer isso.

**Guarda:** a contagem é maior que zero.

**Limiares:** três implementações, dez estrelas. **Escolhidos, não derivados** —
estão aqui para serem discutíveis. Medido no acervo de 2026-08-29: 10 papers.

- [ ] **Passo 1: escrever os testes que falham**

```python
IMPLS_FRONTEIRA, ESTRELAS_FRONTEIRA = 3, 10


def test_a_fronteira_conta_quem_tem_impl_e_nao_tem_atencao(acervo_fronteira):
    a = _so(afirmacoes(acervo_fronteira), "fronteira")
    assert "2 papers" in a.texto


def test_a_fronteira_e_omitida_quando_ninguem_qualifica(acervo):
    """Guarda que nao passa OMITE. Zero na fronteira e informacao, mas a
    frase "0 papers tem..." e ruido; a ausencia da frase ja diz."""
    assert _so(afirmacoes(acervo), "fronteira") is None


def test_a_fronteira_exclui_quem_ja_tem_estrelas(acervo_implementado_e_famoso):
    assert _so(afirmacoes(acervo_implementado_e_famoso), "fronteira") is None


def test_a_fronteira_carrega_o_filtro_que_a_reproduz(acervo_fronteira):
    a = _so(afirmacoes(acervo_fronteira), "fronteira")
    assert a.filtro == {"ordenar": "impls"}
```

- [ ] **Passo 2 a 5:** rodar (FAIL), implementar, rodar a suíte, propor commit.

```python
IMPLS_FRONTEIRA = 3        # escolhido, nao derivado (spec, secao 8)
ESTRELAS_FRONTEIRA = 10


def _fronteira(d: SiteData) -> Afirmacao | None:
    n = sum(1 for p in d.pontos
            if p.independent_impls >= IMPLS_FRONTEIRA
            and p.stars_total < ESTRELAS_FRONTEIRA)
    if n == 0:
        return None
    return Afirmacao(
        texto=f"{n} papers estão na fronteira: {IMPLS_FRONTEIRA} ou mais "
              f"implementações independentes e menos de {ESTRELAS_FRONTEIRA} "
              f"estrelas somadas.",
        filtro={"ordenar": "impls"},
    )
```

---

## Tarefa 4: concentração

**Arquivos:** Modificar `src/radar/leitura.py`. Teste: `tests/test_leitura.py`.

**Guarda:** ao menos 100 papers **e** ao menos 50 implementações independentes
somadas. Abaixo disso, concentração é ruído de amostra pequena.

**Calcula:** o **menor conjunto** de famílias que passa de 50% das
implementações independentes.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_a_concentracao_nomeia_o_menor_conjunto_acima_de_metade(acervo_grande):
    a = _so(afirmacoes(acervo_grande), "concentram")
    assert "2 famílias" in a.texto
    assert "cache_kv" in a.texto and "quantizacao" in a.texto


def test_a_concentracao_traz_a_porcentagem(acervo_grande):
    assert "%" in _so(afirmacoes(acervo_grande), "concentram").texto


def test_a_concentracao_e_omitida_em_acervo_pequeno(acervo_99_papers):
    """99 papers com muitas implementacoes: a guarda de tamanho reprova."""
    assert _so(afirmacoes(acervo_99_papers), "concentram") is None


def test_a_concentracao_e_omitida_com_poucas_implementacoes(acervo_200_papers_49_impls):
    """As duas guardas sao conjuntivas: passar em uma nao basta."""
    assert _so(afirmacoes(acervo_200_papers_49_impls), "concentram") is None


def test_a_concentracao_carrega_um_filtro_por_familia(acervo_grande):
    a = _so(afirmacoes(acervo_grande), "concentram")
    assert a.filtro["familia"] in ("cache_kv", "quantizacao")
```

- [ ] **Passo 2 a 5:** rodar (FAIL), implementar, rodar a suíte, propor commit.

```python
MIN_PAPERS_CONCENTRACAO = 100     # escolhido, nao derivado
MIN_IMPLS_CONCENTRACAO = 50


def _concentracao(d: SiteData) -> Afirmacao | None:
    por_familia: dict[str, int] = {}
    for p in d.pontos:
        por_familia[p.familia] = por_familia.get(p.familia, 0) + p.independent_impls
    total = sum(por_familia.values())

    # Guardas CONJUNTIVAS: um acervo grande com pouco sinal, ou muito sinal
    # concentrado em poucos papers, produz concentracao que e ruido.
    if len(d.pontos) < MIN_PAPERS_CONCENTRACAO or total < MIN_IMPLS_CONCENTRACAO:
        return None

    ordenadas = sorted(por_familia.items(), key=lambda kv: -kv[1])
    acumulado, escolhidas = 0, []
    for familia, n in ordenadas:
        acumulado += n
        escolhidas.append(familia)
        if acumulado > total / 2:
            break

    nomes = ", ".join(escolhidas)
    return Afirmacao(
        texto=f"{len(escolhidas)} famílias concentram {acumulado / total:.0%} "
              f"das {total} implementações independentes do acervo: {nomes}.",
        filtro={"familia": escolhidas[0]},
    )
```

---

## Tarefa 5: cobertura de alegação e taxonomia

**Arquivos:** Modificar `src/radar/leitura.py`. Teste: `tests/test_leitura.py`.

**As duas juntas, numa tarefa só:** são a mesma forma — contagem sobre o total,
sem guarda, saindo sempre. Separá-las custaria duas rodadas de revisão para uma
decisão só.

**Nenhuma tem guarda.** A de cobertura publica o número que decide se a seção de
avanço existe, tornando essa decisão auditável em vez de invisível. A de
taxonomia publica a taxa de não-encaixe, porque esconder faria a taxonomia
parecer mais ajustada do que é.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_a_cobertura_traz_contagem_denominador_e_o_rotulo(acervo):
    a = _so(afirmacoes(acervo), "ganho quantificado")
    assert "de 5" in a.texto
    assert "alegado" in a.texto.lower()


def test_a_cobertura_sai_mesmo_com_zero(acervo_sem_ganho):
    assert _so(afirmacoes(acervo_sem_ganho), "ganho quantificado") is not None


def test_a_taxonomia_reporta_a_taxa_de_outro(acervo):
    a = _so(afirmacoes(acervo), "'outro'")
    assert "%" in a.texto


def test_a_taxonomia_sai_mesmo_sem_nenhum_outro(acervo_sem_outro):
    a = _so(afirmacoes(acervo_sem_outro), "'outro'")
    assert "0 de 5 papers" in a.texto


def test_a_taxonomia_traz_denominador_proprio_e_nao_por_acidente(acervo):
    """A redacao anterior passava no teste de denominador da Tarefa 7 pelo
    " das " de "nenhuma das dezoito familias" -- coincidencia, nao contrato.

    Este teste olha a contagem, nao a frase inteira: se alguem reescrever o
    final da frase, o denominador continua exigido.
    """
    a = _so(afirmacoes(acervo), "'outro'")
    import re
    assert re.search(r"\d+ de \d+ papers", a.texto)
```

- [ ] **Passo 2 a 5:** rodar (FAIL), implementar, rodar a suíte, propor commit.

```python
def _cobertura(d: SiteData) -> Afirmacao | None:
    com = sum(1 for p in d.pontos if p.ganho_fator is not None)
    return Afirmacao(
        texto=f"{com} de {len(d.pontos)} papers ({d.cobertura_de_ganho:.0%}) "
              f"declaram um ganho quantificado no resumo — alegado pelos "
              f"autores, não verificado.",
        filtro={"ordenar": "ganho"},
    )


def _taxonomia(d: SiteData) -> Afirmacao | None:
    """A taxa de `outro` e instrumento de medicao da propria taxonomia.

    Esconde-la do leitor apresentaria a classificacao como mais ajustada do
    que ela e. Ver spec do segundo escopo: `outro` existe para isso, com
    gate de 10%.
    """
    n = sum(1 for p in d.pontos if p.familia == "outro")
    return Afirmacao(
        # O denominador aqui e explicito de proposito. A redacao anterior --
        # "{n} papers ({pct}) cairam em 'outro'" -- passava no teste da
        # Tarefa 7 por ACIDENTE: o " das " de "nenhuma das dezoito familias"
        # satisfazia a busca sem que houvesse denominador de verdade.
        texto=f"{n} de {len(d.pontos)} papers ({n / len(d.pontos):.0%}) "
              f"caíram em 'outro': nenhuma das dezoito famílias coube.",
        filtro={"familia": "outro"} if n else None,
    )
```

---

## Tarefa 6: movimento recente

**Arquivos:** Modificar `src/radar/site_data.py`, `src/radar/store.py`,
`src/radar/leitura.py`. Testes: `tests/test_site_data.py`, `tests/test_leitura.py`.

**Interfaces:**
- `SiteData` ganha `dias_de_coleta: int = 0` e `papers_que_moveram: int = 0`.
- `Store.site_data` os calcula.

**Esta é a guarda mais restritiva do plano, e a razão dela é a mais importante
de entender.** O seed de 2026-08-29 rodou **sem piso de data**: ele trouxe o que
o arXiv devolvia por termo, não o que foi publicado em cada mês. Contar papers
por mês sobre esse recorte mede o ranking de busca do arXiv, não a produção da
literatura.

**Guarda:** ao menos 30 dias distintos de coleta registrados em `signals`, e a
contagem de movimento só considera papers com **duas ou mais observações
reais**.

**A frase que este plano NÃO implementa:** "família X cresceu neste trimestre".
Ela exige que o acervo seja majoritariamente de coleta diária, e a condição
precisa ser verificada em dado — nunca presumida pelo calendário.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_o_movimento_e_omitido_sem_historico_suficiente(acervo_grande):
    """Uma observacao por paper: nao ha o que comparar."""
    assert _so(afirmacoes(acervo_grande), "ganharam implementação") is None


def test_o_movimento_e_omitido_com_menos_de_trinta_dias(acervo_29_dias):
    assert _so(afirmacoes(acervo_29_dias), "ganharam implementação") is None


def test_o_movimento_aparece_com_historico(acervo_com_historico):
    a = _so(afirmacoes(acervo_com_historico), "ganharam implementação")
    assert "2 papers" in a.texto


def test_o_store_conta_dias_distintos_de_coleta(store, paper_rejulgado):
    assert store.site_data(date(2026, 8, 30)).dias_de_coleta == 2


def test_o_store_conta_so_quem_subiu(store, paper_que_subiu, paper_que_caiu):
    assert store.site_data(date(2026, 8, 30)).papers_que_moveram == 1
```

- [ ] **Passo 2 a 5:** rodar (FAIL), implementar, rodar a suíte, propor commit.

```python
MIN_DIAS_PARA_MOVIMENTO = 30       # escolhido, nao derivado


def _movimento(d: SiteData) -> Afirmacao | None:
    """A guarda mais restritiva do modulo.

    O seed rodou SEM PISO DE DATA: ele trouxe o que o arXiv devolvia por termo,
    nao o que foi publicado em cada mes. Qualquer afirmacao temporal sobre esse
    recorte mede o ranking de busca do arXiv, nao a literatura. Ate a rotina
    diaria acumular historico proprio, esta frase nao existe.
    """
    if d.dias_de_coleta < MIN_DIAS_PARA_MOVIMENTO:
        return None
    if d.papers_que_moveram == 0:
        return None
    return Afirmacao(
        texto=f"{d.papers_que_moveram} papers ganharam implementação "
              f"independente desde a observação anterior.",
        filtro={"ordenar": "impls"},
    )
```

---

## Tarefa 7: as guardas de linguagem

**Arquivos:** Modificar `tests/test_leitura.py`. Sem código novo em `src`.

**Esta tarefa é só teste, e é deliberado.** As proibições da spec — sem causa,
sem previsão, sem superlativo solto — não são propriedades de uma função; são
propriedades do **conjunto** das frases. O lugar de travá-las é sobre a saída
inteira, e o valor está em pegar a violação que alguém introduzir daqui a seis
meses ao acrescentar a sétima afirmação.

- [ ] **Passo 1: escrever os testes**

```python
CAUSAIS = ("porque", "devido", "graças a", "por causa", "resulta de",
           "leva a", "provoca")
PREVISAO = ("vai ", "deve ", "tende a", "provavelmente", "espera-se")


def test_nenhuma_afirmacao_usa_verbo_causal(acervo_completo):
    for a in afirmacoes(acervo_completo):
        baixa = a.texto.lower()
        for proibido in CAUSAIS:
            assert proibido not in baixa, f"{proibido!r} em {a.texto!r}"


def test_nenhuma_afirmacao_preve(acervo_completo):
    for a in afirmacoes(acervo_completo):
        baixa = a.texto.lower()
        for proibido in PREVISAO:
            assert proibido not in baixa, f"{proibido!r} em {a.texto!r}"


def test_nenhum_superlativo_sem_numero(acervo_completo):
    """"A familia mais implementada" so existe como "... com N de M"."""
    import re
    for a in afirmacoes(acervo_completo):
        if re.search(r"\bmais\b|\bmaior\b|\bmenor\b", a.texto.lower()):
            assert re.search(r"\d", a.texto), a.texto


def test_toda_afirmacao_com_numero_traz_denominador(acervo_completo):
    """Percentual sem denominador e a forma mais facil de enganar sem mentir."""
    for a in afirmacoes(acervo_completo):
        if "%" in a.texto:
            assert " de " in a.texto or " das " in a.texto, a.texto


def test_todo_filtro_emitido_e_aplicavel(acervo_completo):
    """As chaves batem com os `data-*` que a tabela usa, e o valor existe."""
    validas = {"familia", "pratica", "ordenar"}
    ordenaveis = {"impls", "estrelas", "citacoes", "ganho", "score"}
    familias = {p.familia for p in acervo_completo.pontos}
    for a in afirmacoes(acervo_completo):
        if a.filtro is None:
            continue
        for chave, valor in a.filtro.items():
            assert chave in validas, chave
            if chave == "ordenar":
                assert valor in ordenaveis, valor
            if chave == "familia":
                assert valor in familias, valor
```

- [ ] **Passo 2: rodar**

Esperado: todos passam com o código das tarefas 2 a 6. **Se algum falhar, a
frase é que está errada**, não o teste — corrija o texto em `leitura.py`.

- [ ] **Passo 3: propor commit**

---

## Tarefa 8: desenhar o bloco na página

**Arquivos:** Modificar `src/radar/site.py`. Teste: `tests/test_site.py`.

**Prosa, não cartões de métrica.** Cartão convida à leitura por varredura, e
varredura é o modo em que número sem contexto vira impressão. As frases entram
em parágrafo, com os números em destaque tipográfico.

**Posição:** logo abaixo do enquadramento, acima da fronteira.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_o_bloco_aparece_acima_do_grafico(dados):
    html = render_site(dados)
    assert html.index('class="leitura"') < html.index('class="scatter"')


def test_o_bloco_traz_as_frases_como_prosa_e_nao_cartoes(dados):
    html = render_site(dados)
    assert '<p class="frase"' in html
    assert 'class="cartao"' not in html


def test_a_frase_com_filtro_vira_link_aplicavel(dados):
    html = render_site(dados)
    assert 'data-aplicar=' in html


def test_frase_sem_filtro_nao_vira_link(dados):
    """A de escassez nao tem filtro: ela e o denominador, nao um recorte."""
    import re
    html = render_site(dados)
    escassez = re.search(r'<p class="frase"[^>]*>[^<]*não têm[^<]*</p>', html)
    assert escassez and "data-aplicar" not in escassez.group(0)


def test_acervo_vazio_nao_desenha_o_bloco(dados_vazio):
    assert 'class="leitura"' not in render_site(dados_vazio)
```

- [ ] **Passo 2 a 4:** rodar (FAIL), implementar `_secao_leitura`, ligar o
      `data-aplicar` ao JS de filtro que já existe, rodar a suíte.

- [ ] **Passo 5: olhar a página**

```bash
PYTHONPATH=src <python> -c "..." && open /tmp/jornal.html
```

Confira que as frases lêem como prosa, que os números saltam, e que clicar numa
frase aplica o filtro e move o contador.

- [ ] **Passo 6: propor commit**

---

## Auto-revisão do plano

**Cobertura da spec.** §2 (sem LLM, guarda omite) → restrições globais e Tarefa
1. §3.1 → Tarefa 4. §3.2 → Tarefa 3. §3.3 → Tarefa 2. §3.4 e §3.5 → Tarefa 5.
§3.6 → Tarefa 6. §4 (reproduzível) → Tarefas 3 a 6 emitem filtro, Tarefa 7 o
valida, Tarefa 8 o liga. §5 (forma, ordem) → Tarefas 1 e 8. §6 (fronteiras) →
Tarefa 1. §7 (testes) → todos: 1 nas Tarefas 3, 4 e 6; 2 na 4; 3 na 6; 4 na 2;
5, 6 e 7 na 7; 8 na 1; 9 na 1.

**Consistência de tipos.** `Afirmacao` nasce na Tarefa 1 e é o único retorno das
seis funções. `SiteData` ganha dois campos com default `0` na Tarefa 6 — assim
nenhum teste existente quebra, e quem os preenche é o `store`, explicitamente.

**Uma escolha que vale registrar.** A Tarefa 7 é só teste. Ela poderia ser
diluída nas anteriores, e ficaria pior: as proibições de linguagem são
propriedades do conjunto das frases, não de cada função, e o valor delas é pegar
a violação que a sétima afirmação vai introduzir daqui a seis meses.

**Verificado por execução, não por leitura.** O código das seis afirmações foi
extraído e rodado contra um acervo sintético calcado nos números reais do seed
antes deste plano ser commitado. A verificação pegou duas coisas: a frase de
escassez violava a própria regra de denominador da Tarefa 7 ("Dos 1088
papers..." não casa com `" de "`), e a de taxonomia passava por ACIDENTE, pelo
`" das "` de "nenhuma das dezoito famílias". As duas redações foram corrigidas
e um teste próprio foi acrescentado para a segunda.

**O que este plano deliberadamente não faz.** Nenhuma afirmação sobre
crescimento por mês de publicação. O acervo semeado não sustenta isso, e a spec
exige que a condição seja verificada em dado, não presumida pelo calendário.

## Ordem de execução

1 → 8. As Tarefas 2 a 6 são independentes entre si e podem ser paralelizadas
depois da 1; a 7 precisa de todas elas, e a 8 precisa da 7.
