"""O jornal: uma pagina HTML autocontida, gerada por funcao pura.

Sem framework, sem passo de build, sem dependencia externa -- nem no servidor
nem no cliente. A pagina e um arquivo, e funciona com JS desligado.

Recebe `SiteData` pronto e NUNCA o `Store`: a coleta mora no banco, o desenho
nao sabe de onde o dado veio.
"""
from __future__ import annotations

import re
from html import escape

from .leitura import afirmacoes
from .site_data import SiteData
from .config import load_thresholds
from .svg import (METRICAS_X, render_avanco,
                  render_pequenos_multiplos, render_scatter)

# Cor significa familia, e SO. Em nenhum grafico ela codifica outra coisa.
# As matizes agrupam por escopo -- frios para inferencia, quentes para
# agentes, neutro para o escape -- o que ajuda a leitura sem que a cor passe
# a significar escopo: dentro de cada grupo elas sao distintas e arbitrarias.
CORES_FAMILIA = {
    # inferencia: frios
    "quantizacao":                "#2563eb",
    "cache_kv":                   "#0891b2",
    "decodificacao_especulativa": "#0d9488",
    "esparsidade_e_poda":         "#4f46e5",
    "kernels_e_atencao":          "#7c3aed",
    "serving_e_batching":         "#1d4ed8",
    "arquitetura_eficiente":      "#0369a1",
    "destilacao":                 "#155e75",
    "treino_eficiente":           "#3730a3",
    # agentes: quentes
    "uso_de_ferramenta":          "#ea580c",
    "memoria_e_contexto":         "#d97706",
    "planejamento_e_decomposicao": "#dc2626",
    "orquestracao_multiagente":   "#b91c1c",
    "avaliacao_de_agente":        "#a16207",
    "recuperacao_de_falha":       "#c2410c",
    "agentes_de_codigo":          "#be123c",
    "seguranca_e_guardrails":     "#9f1239",
    "recuperacao_e_rag":          "#92400e",
    # escape: neutro, e de proposito o menos chamativo da paleta
    "outro":                      "#6b7280",
}

_JS = """
// Toda a interatividade da pagina. Os tres SVGs ja vem renderizados; o JS so
// troca qual esta visivel. Com ele desligado, o primeiro fica -- por isso o
// atributo `hidden` mora no HTML e nao num `display:none` de CSS.
// Fundo interativo: dois valores CSS atualizados no ponteiro. Nada de canvas
// nem de laco de animacao -- o navegador pinta o gradiente, e a pagina
// continua leve. Quem pediu menos movimento nao recebe o listener.
if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  var fundo = document.getElementById('fundo');
  var pendente = false;
  window.addEventListener('pointermove', function(e){
    if (pendente) return;
    pendente = true;
    requestAnimationFrame(function(){
      fundo.style.setProperty('--px', (e.clientX / window.innerWidth * 100) + '%');
      fundo.style.setProperty('--py', (e.clientY / window.innerHeight * 100) + '%');
      pendente = false;
    });
  }, {passive: true});
}

// Frases do bloco de leitura: clicar aplica o recorte que a reproduz.
document.querySelectorAll('[data-aplicar]').forEach(function(b){
  b.addEventListener('click', function(){
    var chave = b.getAttribute('data-aplicar');
    var valor = b.getAttribute('data-valor');
    if (chave === 'ordenar'){
      var alvo = document.querySelector('[data-ordenar="' + valor + '"]');
      if (alvo) alvo.click();
    } else {
      var sel = document.getElementById('f-' + chave);
      if (sel){ sel.value = valor; filtros[chave] = valor; aplicar(); }
    }
    var tabela = document.querySelector('.rolagem');
    if (tabela) tabela.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
});

// Filtro, busca e contagem. Tudo sobre `hidden` em linha: sem estado, sem
// URL, sem framework. A contagem existe porque um filtro que devolve pouco e
// indistinguivel de um filtro quebrado sem ela.
var filtros = {};
var busca = '';
var corpo = document.querySelector('tbody');
var contador = document.getElementById('contador');

function aplicar(){
  var linhas = document.querySelectorAll('.linha'), n = 0;
  linhas.forEach(function(tr){
    var passa = Object.keys(filtros).every(function(k){
      return !filtros[k] || tr.getAttribute('data-' + k) === filtros[k];
    }) && (!busca || tr.getAttribute('data-texto').indexOf(busca) !== -1);
    tr.hidden = !passa;
    if (passa) n++;
  });
  if (contador) contador.textContent = n + ' de ' + linhas.length;
}

document.querySelectorAll('[data-filtro]').forEach(function(s){
  s.addEventListener('change', function(){
    filtros[s.getAttribute('data-filtro')] = s.value;
    aplicar();
  });
});

var campo = document.querySelector('[data-busca]');
if (campo) campo.addEventListener('input', function(){
  busca = campo.value.trim().toLowerCase();
  aplicar();
});

// Ordenacao por ATRIBUTO, nunca pelo texto da celula: "\u2014" e "2.3x" nao sao
// numeros, e parsear o visivel quebraria calado nos dois.
document.querySelectorAll('[data-ordenar]').forEach(function(b){
  b.addEventListener('click', function(){
    var chave = b.getAttribute('data-ordenar');
    var asc = b.getAttribute('aria-sort') === 'desc';
    document.querySelectorAll('[data-ordenar]').forEach(function(o){
      o.removeAttribute('aria-sort');
    });
    b.setAttribute('aria-sort', asc ? 'asc' : 'desc');
    var linhas = Array.prototype.slice.call(document.querySelectorAll('.linha'));
    linhas.sort(function(x, y){
      var a = parseFloat(x.getAttribute('data-' + chave));
      var c = parseFloat(y.getAttribute('data-' + chave));
      return asc ? a - c : c - a;
    });
    linhas.forEach(function(tr){ corpo.appendChild(tr); });
  });
});

// Legenda clicavel: o cruzamento entre ver o grafico e interrogar a tabela.
document.querySelectorAll('[data-legenda]').forEach(function(b){
  b.addEventListener('click', function(){
    var f = b.getAttribute('data-legenda');
    var ligado = b.getAttribute('aria-pressed') === 'true';
    document.querySelectorAll('[data-legenda]').forEach(function(o){
      o.setAttribute('aria-pressed', 'false');
    });
    b.setAttribute('aria-pressed', String(!ligado));
    filtros.familia = ligado ? '' : f;
    var sel = document.getElementById('f-familia');
    if (sel) sel.value = filtros.familia;
    aplicar();
  });
});

document.querySelectorAll('[data-eixo]').forEach(function(b){
  b.addEventListener('click', function(){
    var alvo = b.getAttribute('data-eixo');
    document.querySelectorAll('[data-eixo]').forEach(function(o){
      o.setAttribute('aria-pressed', String(o === b));
    });
    document.querySelectorAll('.scatter').forEach(function(s){
      s.hidden = (s.getAttribute('data-eixo') !== alvo);
    });
  });
});
"""

_CSS = r"""
:root{--fundo:#fbfaf8;--texto:#1a1a18;--fraco:#6b6b64;--linha:#e3e0d8;
--acento:#1a1a18;--caixa:#f4f2ed;--brilho:26,26,24;--foco:#8a5a2b}
@media (prefers-color-scheme: dark){:root{--fundo:#0e0e0d;--texto:#e8e5df;
--fraco:#8f8d85;--linha:#282621;--acento:#faf8f4;--caixa:#161512;
--brilho:232,229,223;--foco:#d4a373}}
*{box-sizing:border-box}
body{margin:0;background:var(--fundo);color:var(--texto);
font-family:'Iowan Old Style','Palatino Linotype',Palatino,Charter,
'Bitstream Charter',Georgia,'Times New Roman',serif;
font-size:17px;line-height:1.62;-webkit-font-smoothing:antialiased}
#fundo{position:fixed;inset:0;z-index:-1;pointer-events:none;
background:radial-gradient(680px circle at var(--px,50%) var(--py,22%),
rgba(var(--brilho),0.055),transparent 62%),
repeating-linear-gradient(90deg,transparent 0 119px,
rgba(var(--brilho),0.028) 119px 120px)}
@media (prefers-reduced-motion: reduce){#fundo{
background:repeating-linear-gradient(90deg,transparent 0 119px,
rgba(var(--brilho),0.028) 119px 120px)}}
.pular{position:absolute;left:-9999px;top:0;background:var(--texto);
color:var(--fundo);padding:10px 16px;z-index:10}
.pular:focus{left:8px;top:8px}
:focus-visible{outline:2px solid var(--foco);outline-offset:3px}
.envelope{max-width:1060px;margin:0 auto;padding:0 28px 96px}
.masthead{padding:60px 0 22px;border-bottom:3px double var(--linha)}
h1{margin:0;font-size:52px;line-height:1;letter-spacing:-0.035em;font-weight:600}
.dateline{margin-top:14px;padding-top:12px;border-top:1px solid var(--linha);
font-family:system-ui,-apple-system,sans-serif;font-size:11px;
text-transform:uppercase;letter-spacing:0.13em;color:var(--fraco);
display:flex;gap:20px;flex-wrap:wrap}
.numeros{display:flex;gap:48px;margin-top:26px;flex-wrap:wrap}
.numero b{display:block;font-family:system-ui,-apple-system,sans-serif;
font-size:30px;font-weight:600;font-variant-numeric:tabular-nums;
letter-spacing:-0.02em;line-height:1.1}
.numero span{font-family:system-ui,-apple-system,sans-serif;font-size:10px;
color:var(--fraco);text-transform:uppercase;letter-spacing:0.12em}
section{padding:46px 0;border-bottom:1px solid var(--linha)}
section:last-child{border-bottom:0}
h2{margin:0 0 6px;font-size:25px;font-weight:600;letter-spacing:-0.02em}
h3{margin:0 0 4px;font-size:19px;font-weight:600}
.sub{color:var(--fraco);font-size:15px;margin:0 0 24px;max-width:60ch;
font-style:italic}
.enquadramento{border-bottom:3px double var(--linha)}
.enquadramento p{max-width:62ch;font-size:17px}
.enquadramento p:first-child::first-letter{float:left;font-size:56px;
line-height:.82;padding:4px 10px 0 0;font-weight:600}
.enquadramento p+p{color:var(--fraco)}
.leitura p.frase,.leitura button.frase{max-width:62ch;margin:0 0 12px;
font-size:18px;line-height:1.5}
.leitura b.n{font-family:system-ui,-apple-system,sans-serif;font-weight:620;
font-variant-numeric:tabular-nums;font-size:.94em}
.leitura button.frase{display:block;text-align:left;font-family:inherit;
background:none;border:0;border-bottom:1px dotted var(--linha);padding:0 0 3px;
cursor:pointer;color:inherit}
.leitura button.frase:hover{border-bottom-color:var(--acento)}
.vazio{color:var(--fraco);padding:64px 0;text-align:center;font-style:italic}
svg{width:100%;height:auto;display:block;color:var(--fraco)}
.futuro{color:var(--fraco);font-size:14px;font-style:italic;padding:24px 0}
footer{padding:44px 0;color:var(--fraco);font-size:12px;
font-family:system-ui,-apple-system,sans-serif}
.eixos,.filtros,.legenda,table,.repos,.cortes,.nota{
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.eixos{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.eixos button{font:inherit;font-size:12px;padding:6px 13px;cursor:pointer;
border:1px solid var(--linha);background:transparent;color:var(--fraco);
border-radius:999px;min-height:32px}
.eixos button[aria-pressed="true"]{border-color:var(--acento);
color:var(--acento);font-weight:550}
.legenda{display:flex;gap:15px;flex-wrap:wrap;margin-top:20px;font-size:11px;
color:var(--fraco)}
.legenda i{display:inline-block;width:8px;height:8px;border-radius:2px;
margin-right:5px;vertical-align:middle}
.legenda button{font:inherit;font-size:11px;color:var(--fraco);background:none;
border:0;padding:3px 0;cursor:pointer}
.legenda button[aria-pressed=true]{color:var(--acento);font-weight:600}
.nota{font-size:12px;color:var(--fraco);margin-top:14px;max-width:58ch}
.filtros{display:flex;gap:22px;margin-bottom:20px;flex-wrap:wrap}
.filtros label{font-size:10px;color:var(--fraco);text-transform:uppercase;
letter-spacing:0.12em;display:block;margin-bottom:6px}
.filtros select,.filtros input[type=search]{font:inherit;font-size:13px;
padding:7px 10px;background:var(--fundo);color:var(--texto);
border:1px solid var(--linha);border-radius:4px;min-height:34px}
.filtros input[type=search]{min-width:210px}
.contagem span{font-size:13px;font-variant-numeric:tabular-nums;
color:var(--fraco);display:inline-block;padding-top:7px}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{text-align:left;font-weight:550;font-size:10px;color:var(--fraco);
text-transform:uppercase;letter-spacing:0.12em;padding:0 12px 10px 0;
border-bottom:2px solid var(--linha);position:sticky;top:0;
background:var(--fundo)}
thead button{font:inherit;font-size:10px;text-transform:uppercase;
letter-spacing:0.12em;color:var(--fraco);background:none;border:0;padding:0;
cursor:pointer;font-weight:550;min-height:24px}
thead button:hover,thead button[aria-sort]{color:var(--acento)}
thead button[aria-sort]::after{content:" \2193"}
thead button[aria-sort=asc]::after{content:" \2191"}
td{padding:10px 12px 10px 0;border-bottom:1px solid var(--linha);
vertical-align:top}
tbody tr:hover td{background:var(--caixa)}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;
color:var(--fraco)}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
border:1px solid var(--linha);color:var(--fraco);white-space:nowrap}
.tag.adotar{border-color:currentColor;color:var(--texto);font-weight:550}
.pt{display:inline-block;width:7px;height:7px;border-radius:2px;
margin-right:7px;vertical-align:middle}
a{color:inherit;text-decoration:none;border-bottom:1px solid var(--linha)}
a:hover{border-bottom-color:var(--acento)}
.rolagem{overflow-x:auto;max-height:70vh}
.destaque .meta{color:var(--fraco);font-size:12px;margin-bottom:16px;
font-family:system-ui,-apple-system,sans-serif}
.destaque p.resumo{max-width:62ch;margin:0 0 22px}
.repos{list-style:none;padding:0;margin:0;font-size:13px}
.repos li{padding:9px 0;border-bottom:1px solid var(--linha);display:flex;
gap:14px;align-items:baseline;flex-wrap:wrap}
.repos .quem{color:var(--fraco);font-size:11px}
.repos .indep{color:var(--texto);font-weight:550}
.cortes{list-style:none;padding:0;margin:0;font-size:13px;
font-variant-numeric:tabular-nums}
.cortes li{padding:8px 0;border-bottom:1px solid var(--linha);display:flex;
justify-content:space-between;max-width:420px}
.cortes b{font-weight:600}
@media (max-width: 640px){.envelope{padding:0 18px 64px}h1{font-size:36px}
.numeros{gap:28px}body{font-size:16px}}
"""

# Contrato com o leitor. Escrito a mao e versionado -- nao e gerado, e nao
# muda com o dado do dia.
_ENQUADRAMENTO = (
    "<p>Este radar mede uma coisa só: quantas <strong>implementações "
    "independentes</strong> um paper atraiu no GitHub, descontando os "
    "repositórios dos próprios autores. A hipótese é que gente reimplementando "
    "por conta própria diz mais sobre uma técnica do que citação ou estrela.</p>"
    "<p>Ele <strong>não mede</strong> se a técnica funciona. Nada aqui foi "
    "reproduzido, não há benchmark, e todo número de ganho que aparecer é "
    "alegação dos autores extraída do resumo — nunca resultado verificado. "
    "Papers que já estouraram em atenção são cortados de propósito: o radar "
    "existe para achar o que ainda não foi olhado.</p>"
)


def _cabecalho(d: SiteData) -> str:
    impls = sum(p.independent_impls for p in d.pontos)
    return (
        f'<header class="masthead"><h1>ai-radar</h1>'
        f'<div class="dateline"><span>acervo em {escape(d.dia)}</span>'
        f'<span>implementação independente como sinal</span>'
        f'<span>nada aqui foi reproduzido</span></div>'
        f'<div class="numeros">'
        f'<div class="numero"><b>{len(d.pontos)}</b><span>papers</span></div>'
        f'<div class="numero"><b>{len(d.familias_presentes)}</b>'
        f"<span>famílias</span></div>"
        f'<div class="numero"><b>{impls}</b>'
        f"<span>implementações independentes</span></div>"
        f"</div></header>"
    )


def _secao(titulo: str, sub: str, corpo: str) -> str:
    return (f"<section><h2>{titulo}</h2><p class=\"sub\">{sub}</p>"
            f"{corpo}</section>")


def _legenda(d: SiteData) -> str:
    """So as familias PRESENTES no acervo.

    Listar as dezenove sempre encheria a legenda de cor que nao aparece em
    ponto nenhum, e a legenda existe para decodificar o grafico, nao para
    catalogar a taxonomia.
    """
    itens = "".join(
        f'<button type="button" data-legenda="{escape(f)}">'
        f'<i style="background:{CORES_FAMILIA[f]}"></i>{escape(f)}</button>'
        for f in d.familias_presentes
    )
    return f'<div class="legenda">{itens}</div>'


def _secao_fronteira(d: SiteData) -> str:
    lim = load_thresholds()
    botoes = "".join(
        f'<button type="button" data-eixo="{m}" '
        f'aria-pressed="{"true" if i == 0 else "false"}">{rotulo}</button>'
        for i, (m, rotulo) in enumerate(METRICAS_X.items())
    )
    graficos = "".join(
        render_scatter(d.pontos, m, CORES_FAMILIA)
        .replace('<svg class="scatter"',
                 f'<svg class="scatter" data-eixo="{m}"'
                 + ("" if i == 0 else " hidden"))
        for i, m in enumerate(METRICAS_X)
    )
    nota = (f'<p class="nota">Papers acima de {lim.broke_out_stars} estrelas ou '
            f"{lim.broke_out_citations} citações não são pontuados: já "
            f"estourou em atenção, e o radar existe para o que ainda não "
            f"estourou.</p>")
    return botoes and f'<div class="eixos">{botoes}</div>{graficos}{_legenda(d)}{nota}'


# Abaixo disso a secao de avanco nao e construida: grafico sobre dado ralo e
# pior que grafico ausente. Ver spec do jornal, secao 3.4.
COBERTURA_MINIMA = 0.35

ROTULO_ALEGACAO = "alegado pelos autores, não verificado"


def _secao_avanco(d: SiteData) -> str:
    """Devolve string vazia quando o dado nao sustenta o grafico.

    O chamador precisa omitir a SECAO INTEIRA nesse caso -- titulo e subtitulo
    incluidos -- para nao sobrar rotulo orfao nem promessa vazia.
    """
    if d.cobertura_de_ganho < COBERTURA_MINIMA:
        return ""
    com = sum(1 for p in d.pontos if p.ganho_fator is not None)
    return (render_avanco(d.pontos, CORES_FAMILIA) + _legenda(d)
            + f'<p class="nota">{com} de {len(d.pontos)} papers declaram ganho '
              f"quantificado. Escala logarítmica; a linha por família só "
              f"aparece com pelo menos cinco papers no trimestre.</p>")


def _destacar_numeros(texto: str) -> str:
    """Envolve os numeros em <b>, sobre o texto JA escapado.

    A ordem importa: escapar depois de inserir a tag comeria a propria tag.
    """
    return re.sub(r"(\d[\d.,]*%?)", r'<b class="n">\1</b>', escape(texto))


def _secao_leitura(d: SiteData) -> str:
    """Prosa, nao cartoes de metrica.

    Cartao convida a leitura por varredura, e varredura e o modo em que numero
    sem contexto vira impressao. As frases entram em paragrafo, com os numeros
    em destaque tipografico.

    Frase com filtro vira botao que aplica o recorte na tabela abaixo -- e o
    que separa esta secao de um resumo gerado. Uma afirmacao conferivel em
    dois cliques e verificavel; uma que so pode ser aceita e autoridade.
    """
    afs = afirmacoes(d)
    if not afs:
        return ""
    partes = []
    for a in afs:
        corpo = _destacar_numeros(a.texto)
        if a.filtro:
            chave, valor = next(iter(a.filtro.items()))
            partes.append(
                f'<button type="button" class="frase" '
                f'data-aplicar="{escape(chave)}" '
                f'data-valor="{escape(str(valor))}">{corpo}</button>'
            )
        else:
            partes.append(f'<p class="frase">{corpo}</p>')
    return f'<section class="leitura">{"".join(partes)}</section>'


def _secao_familias(d: SiteData) -> str:
    series: dict[str, dict[str, int]] = {}
    for p in d.pontos:
        series.setdefault(p.familia, {}).setdefault(p.publicado[:7], 0)
        series[p.familia][p.publicado[:7]] += 1
    return render_pequenos_multiplos(series, d.familias_presentes, CORES_FAMILIA)


def _opcoes(valores: list[str]) -> str:
    return '<option value="">todas</option>' + "".join(
        f'<option value="{escape(v)}">{escape(v)}</option>' for v in valores)


def _linha(p) -> str:
    cor = CORES_FAMILIA.get(p.familia, "currentColor")
    # `None` e desconhecido e vira travessao. Renderizar 0 aqui reintroduziria,
    # pela camada de apresentacao, o mesmo defeito que o pipeline consertou.
    cit = "—" if p.citations is None else str(p.citations)
    ganho = (f"{p.ganho_fator:g}x" if p.ganho_fator is not None else "—")
    # Valores de ordenacao viajam como ATRIBUTO, nao no texto visivel: a
    # celula mostra "—" e "2.3x", que nao sao numeros, e um JS que parseasse
    # o texto quebraria em silencio nos dois casos.
    #
    # Citacao desconhecida ordena como -1 e nao 0: mandar zero faria
    # "nao perguntamos" empatar com "ninguem citou", que e exatamente a
    # confusao que o pipeline inteiro existe para evitar.
    ord_cit = -1 if p.citations is None else p.citations
    ord_ganho = p.ganho_fator if p.ganho_fator is not None else -1
    texto = f"{p.titulo} {p.familia} {p.pratica} {p.arxiv_id}".lower()
    return (
        f'<tr class="linha" data-id="{escape(p.arxiv_id)}" '
        f'data-familia="{escape(p.familia)}" data-pratica="{escape(p.pratica)}" '
        f'data-texto="{escape(texto)}" '
        f'data-impls="{p.independent_impls}" data-estrelas="{p.stars_total}" '
        f'data-citacoes="{ord_cit}" data-ganho="{ord_ganho:g}" '
        f'data-score="{p.score:g}">'
        f'<td><a href="https://arxiv.org/abs/{escape(p.arxiv_id)}">'
        f"{escape(p.titulo)}</a></td>"
        f'<td><span class="pt" style="background:{cor}"></span>'
        f"{escape(p.familia)}</td>"
        f'<td><span class="tag {escape(p.pratica)}">'
        f'{escape(p.pratica.replace("_", " "))}</span></td>'
        f'<td class="num">{p.independent_impls}</td>'
        f'<td class="num">{p.stars_total}</td>'
        f'<td class="num">{cit}</td>'
        f'<td class="num">{ganho}</td>'
        f"</tr>"
    )


def _secao_tabela(d: SiteData) -> str:
    """Filtro por pratica e por familia, sem estado e sem URL.

    O de PRATICA e o primario: e ele que responde "o que eu adoto", que e a
    pergunta pela qual o leitor abriu a pagina. O de familia serve para
    navegar a literatura, nao para decidir.
    """
    praticas = sorted({p.pratica for p in d.pontos})
    linhas = "".join(_linha(p) for p in
                     sorted(d.pontos, key=lambda p: -p.score))
    return (
        '<div class="filtros">'
        f'<div><label for="f-pratica">o que fazer</label>'
        f'<select id="f-pratica" data-filtro="pratica">{_opcoes(praticas)}'
        f"</select></div>"
        f'<div><label for="f-familia">família</label>'
        f'<select id="f-familia" data-filtro="familia">'
        f"{_opcoes(d.familias_presentes)}</select></div>"
        '<div><label for="f-busca">buscar</label>'
        '<input id="f-busca" type="search" data-busca '
        'placeholder="quantization, agent, cache..."></div>'
        f'<div class="contagem"><label>mostrando</label>'
        f'<span id="contador">{len(d.pontos)} de {len(d.pontos)}</span></div>'
        "</div>"
        '<div class="rolagem"><table><thead><tr>'
        '<th><button type="button" data-ordenar="score">técnica</button></th>'
        "<th>família</th><th>prática</th>"
        '<th class="num"><button type="button" data-ordenar="impls">impls</button></th>'
        '<th class="num"><button type="button" data-ordenar="estrelas">estrelas</button></th>'
        '<th class="num"><button type="button" data-ordenar="citacoes">citações</button></th>'
        '<th class="num"><button type="button" data-ordenar="ganho">ganho</button></th>'
        f"</tr></thead><tbody>{linhas}</tbody></table></div>"
    )


def _secao_destaque(d: SiteData) -> str:
    """O paper de maior score, aberto.

    Existe para tornar o numero auditavel: sem ver os repositorios e a regra
    que classificou cada um, "3 implementacoes independentes" e fe. E a
    heuristica de autoria e heuristica -- ela precisa poder ser conferida.
    """
    p = d.destaque
    if p is None:
        return '<p class="vazio">Nada no acervo ainda.</p>'

    if d.repos_do_destaque:
        itens = []
        for r in d.repos_do_destaque:
            if r["is_author"]:
                quem = f'autor — {escape(r["is_author_reason"] or "regra não registrada")}'
                classe = "quem"
            else:
                quem, classe = "independente", "indep"
            itens.append(
                f'<li><a href="https://github.com/{escape(r["full_name"])}">'
                f'{escape(r["full_name"])}</a>'
                f'<span class="num">{r["stars"]} estrelas</span>'
                f'<span class="{classe}">{quem}</span></li>'
            )
        repos = f'<ul class="repos">{"".join(itens)}</ul>'
    else:
        repos = ('<p class="nota">Nenhum repositório registrado para este '
                 "paper.</p>")

    ganho = ""
    if p.ganho_fator is not None:
        ganho = (f' · ganho {p.ganho_fator:g}x em {escape(p.ganho_eixo)} '
                 f"({ROTULO_ALEGACAO})")
    return (
        f'<div class="destaque"><h3>'
        f'<a href="https://arxiv.org/abs/{escape(p.arxiv_id)}">'
        f"{escape(p.titulo)}</a></h3>"
        f'<div class="meta">{escape(p.familia)} · '
        f'{escape(p.pratica.replace("_", " "))} · '
        f"{p.independent_impls} de {p.total_impls} implementações "
        f"independentes{ganho}</div>"
        f'<p class="resumo">{escape(p.resumo)}</p>{repos}</div>'
    )


def _secao_cortes(d: SiteData) -> str:
    """Todo corte contado chega ao leitor -- restricao global do projeto.

    A secao aparece mesmo vazia: um dia sem cortes e informacao, e some-la
    faria parecer que a contabilidade nao foi feita.
    """
    if d.cortes:
        itens = "".join(
            f"<li><span>{escape(motivo.replace('_', ' '))}</span>"
            f"<b>{n}</b></li>"
            for motivo, n in sorted(d.cortes.items(), key=lambda kv: -kv[1])
        )
        lista = f'<ul class="cortes">{itens}</ul>'
    else:
        lista = '<p class="nota">Nenhum corte hoje.</p>'
    return (lista + f'<p class="nota">{d.rechecked_total} papers antigos '
                    f"foram re-consultados nesta execução.</p>")


def _pendente(qual: str) -> str:
    """Marcador das secoes que as tarefas 5 a 8 preenchem.

    A tarefa 4 entrega a pagina inteira com as secoes vazias de proposito:
    ajustar identidade visual com elas vazias custa uma fracao de ajustar
    depois de preenchidas.
    """
    return f'<p class="futuro">{qual}</p>'


def render_site(dados: SiteData) -> str:
    if not dados.pontos:
        corpo = '<p class="vazio">Nenhum paper no acervo ainda.</p>'
    else:
        corpo = "".join((
            _secao("A fronteira",
                   "Implementações independentes contra o quanto o paper já "
                   "foi olhado. A região interessante é o alto à esquerda: "
                   "muita gente construindo, pouca gente olhando.",
                   _secao_fronteira(dados)),
            (_secao("O avanço alegado",
                    "Ganho declarado no resumo, por família, ao longo do tempo "
                    f"— {ROTULO_ALEGACAO}.",
                    avanco) if (avanco := _secao_avanco(dados)) else ""),
            _secao("As famílias no tempo",
                   "Volume por família, mês a mês, em escala compartilhada.",
                   _secao_familias(dados)),
            _secao("O acervo",
                   "Tudo que passou pelo radar, filtrável pelo que você faz "
                   "com a técnica.",
                   _secao_tabela(dados)),
            _secao("Uma técnica, de ponta a ponta",
                   "O paper de maior score, aberto: os repositórios "
                   "encontrados e a regra que classificou cada um.",
                   _secao_destaque(dados)),
            _secao("O que ficou de fora",
                   "Todo corte é contado e chega ao leitor.",
                   _secao_cortes(dados)),
        ))

    return (
        "<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>ai-radar — {escape(dados.dia)}</title>"
        f"<style>{_CSS}</style></head><body>"
        '<div id="fundo" aria-hidden="true"></div>'
        '<a class="pular" href="#conteudo">pular para o conteúdo</a>'
        '<div class="envelope">'
        f"{_cabecalho(dados)}"
        f'<main id="conteudo">'
        f'<section class="enquadramento">{_ENQUADRAMENTO}</section>'
        f"{_secao_leitura(dados)}"
        f"{corpo}"
        "</main>"
        "<footer>Gerado pelo próprio pipeline. Sem framework, sem build, "
        "sem requisição externa.</footer>"
        f"</div><script>{_JS}</script></body></html>"
    )
