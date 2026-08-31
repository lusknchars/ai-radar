"""Browser assets for AI Radar's generated, no-build frontend.

The renderer in :mod:`radar.site` owns semantic HTML. This module owns the
visual system and progressive enhancement that are inlined into each page.
"""
from __future__ import annotations

SCRIPT = """
// Toda a interatividade da pagina. Os tres SVGs ja vem renderizados; o JS so
// troca qual esta visivel. Com ele desligado, o primeiro fica -- por isso o
// atributo `hidden` mora no HTML e nao num `display:none` de CSS.
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
var mostrarTodos = false;
var corpo = document.querySelector('tbody');
var contador = document.getElementById('contador');

function aplicar(){
  var linhas = document.querySelectorAll('.linha'), n = 0;
  var recorteAtivo = busca || Object.keys(filtros).some(function(k){
    return Boolean(filtros[k]);
  });
  linhas.forEach(function(tr){
    var passa = Object.keys(filtros).every(function(k){
      return !filtros[k] || tr.getAttribute('data-' + k) === filtros[k];
    }) && (!busca || tr.getAttribute('data-texto').indexOf(busca) !== -1);
    var dentroDoRecorte = mostrarTodos || recorteAtivo ||
      tr.getAttribute('data-inicial') !== 'oculta';
    tr.hidden = !(passa && dentroDoRecorte);
    if (passa && dentroDoRecorte) n++;
  });
  if (contador) contador.textContent = n + ' de ' + linhas.length;
}

var mostrar = document.querySelector('[data-mostrar-todos]');
if (mostrar) mostrar.addEventListener('click', function(){
  mostrarTodos = true;
  mostrar.remove();
  aplicar();
});

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

STYLES = r"""
:root{--fundo:#09090b;--superficie:#0f0f12;--superficie-2:#151519;
--texto:#f4f4f6;--fraco:#94949e;--apagado:#5d5d68;
--linha:rgba(255,255,255,.09);--linha-forte:rgba(255,255,255,.16);
--acento:#62e6a3;--acento-escuro:#07150e;--foco:#86efac;
--mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
--sans:Switzer,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}
html{scroll-behavior:smooth;background:var(--fundo)}
body{margin:0;background:var(--fundo);color:var(--texto);font-family:var(--sans);
font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
#fundo{position:fixed;inset:0;z-index:-1;pointer-events:none;background:
radial-gradient(800px circle at 76% 2%,rgba(98,230,163,.09),transparent 58%),
linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),
linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);
background-size:auto,64px 64px,64px 64px;mask-image:linear-gradient(#000,transparent 72%)}
.pular{position:absolute;left:-9999px;top:0;background:var(--acento);
color:var(--acento-escuro);padding:10px 16px;z-index:20;border-radius:999px}
.pular:focus{left:12px;top:12px}
:focus-visible{outline:2px solid var(--foco);outline-offset:3px}
a{color:inherit;text-decoration:none}
.envelope{max-width:1220px;margin:0 auto;padding:0 32px 88px}
.nav{min-height:64px;display:flex;gap:22px;align-items:center;
border-bottom:1px solid var(--linha);font-family:var(--mono);font-size:10px;
text-transform:uppercase;letter-spacing:.12em}
.nav::before{content:"AI/R";display:grid;place-items:center;width:34px;height:34px;
margin-right:auto;border:1px solid var(--linha-forte);border-radius:10px;
color:var(--texto);font-weight:700;letter-spacing:-.04em}
.nav a{color:var(--apagado);transition:color 160ms ease-out}
.nav a:hover,.nav a[aria-current=page]{color:var(--texto)}
.masthead{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);
gap:64px;align-items:end;padding:88px 0 72px}
.static-masthead{padding:72px 0 48px}.static-masthead h1{max-width:22ch;
font-size:clamp(38px,6vw,68px);line-height:1;letter-spacing:-.05em}
.hero-eyebrow{margin:0 0 22px;font-family:var(--mono);font-size:10px;
text-transform:uppercase;letter-spacing:.16em;color:var(--fraco)}
.hero-eyebrow::before{content:"";display:inline-block;width:7px;height:7px;
margin-right:9px;border-radius:50%;background:var(--acento);
box-shadow:0 0 14px rgba(98,230,163,.72)}
h1{max-width:750px;margin:0;font-size:clamp(48px,7vw,88px);font-weight:400;
line-height:.94;letter-spacing:-.058em}
h1 .marca{display:block;margin-bottom:18px;font-family:var(--mono);font-size:12px;
font-weight:500;line-height:1;text-transform:uppercase;letter-spacing:.18em;
color:var(--apagado)}
h1 em{font-style:normal;color:var(--acento)}
.hero-deck{max-width:54ch;margin:28px 0 30px;color:var(--fraco);font-size:16px}
.dateline{display:none}
.numeros{display:grid;gap:1px;padding:1px;border:1px solid var(--linha);
border-radius:24px;overflow:hidden;background:var(--linha);
box-shadow:0 28px 60px -46px rgba(98,230,163,.5)}
.numero{min-height:112px;padding:22px 24px;background:linear-gradient(180deg,
rgba(255,255,255,.035),transparent 55%),var(--superficie);position:relative}
.numero::after{content:"";position:absolute;right:22px;top:25px;width:7px;
height:7px;border-radius:50%;background:var(--acento);opacity:.68}
.numero b{display:block;font-size:36px;font-weight:400;font-variant-numeric:tabular-nums;
letter-spacing:-.045em;line-height:1}
.numero span{display:block;margin-top:12px;font-family:var(--mono);font-size:9px;
color:var(--apagado);text-transform:uppercase;letter-spacing:.13em}
/* Port sem React do SheenButton autoral em ~/frontend-lab. A estrutura,
   color-mix, sweep unico, active e reduced-motion continuam iguais. */
.sheen-button{--acc:var(--acento);position:relative;isolation:isolate;display:inline-flex;
align-items:center;justify-content:center;gap:9px;min-height:44px;overflow:hidden;
padding:10px 17px;border:0;border-radius:999px;background:var(--acc);
background:linear-gradient(176deg,color-mix(in oklab,var(--acc) 84%,white) 0%,
var(--acc) 46%,color-mix(in oklab,var(--acc) 74%,black) 100%);
color:color-mix(in oklab,var(--acc) 16%,#05070a);font:500 12px/1 var(--sans);
box-shadow:inset 0 1px 0 rgba(255,255,255,.38),
0 10px 30px -12px color-mix(in oklab,var(--acc) 85%,transparent);
cursor:pointer;transition:transform 300ms ease-out,filter 300ms ease-out}
.sheen-button:hover{filter:brightness(1.06)}.sheen-button:active{transform:scale(.96)}
.sheen-button svg{position:relative;width:15px;height:15px;transition:transform 300ms ease-out}
.sheen-button:hover svg{transform:translateX(2px)}
.sheen-button .sheen-label{position:relative;white-space:nowrap}
.sheen-sweep{position:absolute;inset:0;z-index:-1;transform:translateX(-105%);
background:linear-gradient(90deg,transparent,rgba(0,0,0,.2),transparent);
transition:transform 700ms ease-out}.sheen-button:hover .sheen-sweep{transform:translateX(105%)}
.sheen-button.secondary{border:1px solid var(--linha-forte);background:rgba(255,255,255,.055);
color:var(--texto);box-shadow:none}.sheen-button.secondary .sheen-sweep{
background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent)}
main>section{padding:72px 0;border-top:1px solid var(--linha)}
h2{margin:0;font-size:30px;font-weight:450;line-height:1.15;letter-spacing:-.035em}
h3{margin:0 0 7px;font-size:18px;font-weight:520;letter-spacing:-.02em}
.sub{max-width:62ch;margin:10px 0 30px;color:var(--fraco);font-size:14px}
.enquadramento{display:grid;grid-template-columns:1fr 1fr;gap:32px;padding:28px 32px;
border:1px solid var(--linha)!important;border-radius:22px;background:var(--superficie)}
.enquadramento p{margin:0;color:var(--fraco);font-size:14px}.enquadramento strong{color:var(--texto)}
.leitura{display:flex;flex-wrap:wrap;gap:10px;padding:28px 0!important;border:0!important}
.leitura p.frase,.leitura button.frase{flex:1 1 300px;max-width:none;margin:0;
padding:17px 19px;border:1px solid var(--linha);border-radius:16px;
background:var(--superficie);color:var(--fraco);font:400 13px/1.55 var(--sans);
text-align:left}.leitura button.frase{cursor:pointer;transition:border-color 160ms,
background 160ms}.leitura button.frase:hover{border-color:var(--linha-forte);
background:var(--superficie-2)}.leitura b.n{color:var(--texto);font-weight:600;
font-variant-numeric:tabular-nums}.vazio{color:var(--fraco);padding:64px 0;text-align:center}
svg{width:100%;height:auto;display:block;color:var(--fraco)}
footer{padding:48px 0;color:var(--apagado);font-family:var(--mono);font-size:9px;
text-transform:uppercase;letter-spacing:.1em}
.eixos,.filtros,.legenda,table,.repos,.cortes,.nota{font-family:var(--sans)}
.eixos{display:flex;gap:8px;margin-bottom:22px;flex-wrap:wrap}
.eixos button,.legenda button{min-height:36px;padding:7px 12px;border:1px solid var(--linha);
border-radius:999px;background:transparent;color:var(--fraco);font:500 10px var(--sans);
cursor:pointer}.eixos button:hover,.legenda button:hover{border-color:var(--linha-forte);
color:var(--texto)}.eixos button[aria-pressed=true],.legenda button[aria-pressed=true]{
border-color:color-mix(in oklab,var(--acento) 50%,transparent);color:var(--acento);
background:color-mix(in oklab,var(--acento) 8%,transparent)}
.legenda{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.legenda i{display:inline-block;
width:6px;height:6px;border-radius:50%;margin-right:6px;vertical-align:middle}
.legenda button{border-color:transparent;padding:6px 9px}.nota{max-width:62ch;margin-top:16px;
color:var(--apagado);font-size:11px}.filtros{display:grid;
grid-template-columns:repeat(2,minmax(130px,180px)) minmax(220px,1fr) auto;
gap:12px;align-items:end;margin-bottom:16px;padding:16px;border:1px solid var(--linha);
border-radius:18px;background:var(--superficie)}
.filtros label{display:block;margin-bottom:7px;color:var(--apagado);
font:500 9px var(--mono);text-transform:uppercase;letter-spacing:.12em}
.filtros select,.filtros input[type=search]{width:100%;min-height:42px;padding:8px 12px;
border:1px solid var(--linha);border-radius:10px;background:var(--fundo);color:var(--texto);
font:400 12px var(--sans)}.filtros input[type=search]::placeholder{color:var(--apagado)}
.contagem span{display:block;min-height:42px;padding:11px 4px;color:var(--fraco);
font:400 11px var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.rolagem{overflow:auto;max-height:76vh;border:1px solid var(--linha);border-radius:20px;
background:var(--superficie)}table{width:100%;border-collapse:collapse;font-size:12px}
thead th{position:sticky;top:0;z-index:2;padding:13px 12px;border-bottom:1px solid var(--linha);
background:rgba(15,15,18,.94);backdrop-filter:blur(12px);color:var(--apagado);
font:500 8px var(--mono);text-align:left;text-transform:uppercase;letter-spacing:.1em}
thead button{min-height:28px;padding:0;border:0;background:none;color:inherit;
font:inherit;text-transform:inherit;letter-spacing:inherit;cursor:pointer}
thead button:hover,thead button[aria-sort]{color:var(--acento)}
thead button[aria-sort]::after{content:" \2193"}thead button[aria-sort=asc]::after{content:" \2191"}
td{padding:18px 12px;border-bottom:1px solid var(--linha);vertical-align:top}
tbody tr:last-child td{border-bottom:0}tbody tr{transition:background 160ms ease-out}
tbody tr:hover{background:rgba(255,255,255,.025)}td:first-child{min-width:320px}
td:first-child>a{font-size:13px;font-weight:520;line-height:1.35;color:var(--texto)}
td:first-child>a:hover{color:var(--acento)}td.num{text-align:right;color:var(--fraco);
font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.tag{display:inline-flex;min-height:26px;align-items:center;padding:3px 9px;border:1px solid var(--linha);
border-radius:999px;color:var(--fraco);font-size:9px;white-space:nowrap}.tag.adotar{
border-color:color-mix(in oklab,var(--acento) 35%,transparent);color:var(--acento);
background:color-mix(in oklab,var(--acento) 7%,transparent)}
.paper-brief{display:block;max-width:60ch;margin-top:7px;color:var(--fraco);
font-size:11px;line-height:1.55}.acao{min-width:132px}.report-action{width:100%}
.show-all{margin-top:18px}.pt{display:inline-block;width:6px;height:6px;border-radius:50%;
margin-right:7px;vertical-align:middle}.destaque{padding:28px;border:1px solid var(--linha);
border-radius:20px;background:var(--superficie)}.destaque .meta{margin:9px 0 18px;
color:var(--apagado);font:10px var(--mono)}.destaque p.resumo{max-width:65ch;
margin:0 0 24px;color:var(--fraco)}.repos{list-style:none;padding:0;margin:0;font-size:12px}
.repos li{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;padding:10px 0;
border-bottom:1px solid var(--linha)}.repos .quem{color:var(--apagado);font-size:10px}
.repos .indep{color:var(--acento);font-weight:550}.cortes{list-style:none;padding:0;
margin:0;font-size:12px;font-variant-numeric:tabular-nums}.cortes li{display:flex;
justify-content:space-between;max-width:480px;padding:10px 0;border-bottom:1px solid var(--linha)}
.pagina{max-width:850px}.pagina p,.pagina li{max-width:68ch}.pagina h2{margin-top:34px}
.edicoes{list-style:none;padding:0;margin:24px 0}.edicoes li{padding:14px 0;
border-bottom:1px solid var(--linha);font-family:var(--mono);font-size:12px}
.report{max-width:820px}.report-kicker,.report-source{font-family:var(--mono);
font-size:9px;color:var(--apagado);letter-spacing:.1em;text-transform:uppercase}
.report-kicker{margin-top:18px}.report h2{margin:0 0 8px;font-size:18px;
font-weight:520;letter-spacing:-.02em}.report-lead{max-width:60ch;
font-size:18px;line-height:1.55;color:var(--fraco)}.infra-grid{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:34px 0;padding:1px;
border:1px solid var(--linha);border-radius:20px;overflow:hidden;background:var(--linha)}
.infra-grid div{min-height:100px;padding:20px;background:var(--superficie)}
.infra-grid span{display:block;color:var(--apagado);font:500 8px var(--mono);
text-transform:uppercase;letter-spacing:.11em}.infra-grid b{display:block;margin-top:10px;
font-size:14px;font-weight:520}.report section{padding:34px 0;border-top:1px solid var(--linha)}
.report li{margin:9px 0;color:var(--fraco)}.evidence{list-style:none;padding:0}
.evidence li{padding:16px 0;border-bottom:1px solid var(--linha)}
.evidence strong,.evidence span{display:block}.evidence strong{color:var(--texto)}
.evidence span{color:var(--fraco);font-size:13px}.report-source{margin-top:38px;
line-height:1.7;text-transform:none;letter-spacing:0}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.sheen-button,
.sheen-button *{transition-duration:1ms!important}}
@media (max-width:900px){.masthead{grid-template-columns:1fr;gap:42px;padding:64px 0}
.numeros{grid-template-columns:repeat(3,1fr)}.numero{min-height:96px}.filtros{
grid-template-columns:repeat(2,1fr)}.contagem{grid-column:2}.enquadramento{grid-template-columns:1fr}}
@media (max-width:640px){.envelope{padding:0 16px 64px}.nav{gap:14px;overflow-x:auto}
.nav::before{position:sticky;left:0;background:var(--fundo)}.masthead{padding:50px 0 44px}
h1{font-size:48px}.numeros{grid-template-columns:1fr}.numero{min-height:86px}
main>section{padding:54px 0}.enquadramento{padding:22px}.filtros{grid-template-columns:1fr}
.contagem{grid-column:auto}.rolagem{overflow:visible;max-height:none;border:0;background:transparent}
table,tbody,tr,td{display:block;width:100%}thead{display:none}tbody{display:grid;gap:12px}
.linha{padding:20px;border:1px solid var(--linha);border-radius:18px;background:var(--superficie)}
td{display:flex;justify-content:space-between;gap:18px;padding:7px 0;border:0;text-align:right}
td::before{content:attr(data-label);color:var(--apagado);font:500 8px var(--mono);
text-transform:uppercase;letter-spacing:.1em}td:first-child{display:block;min-width:0;text-align:left;
padding:0 0 16px}td:first-child::before{display:none}td.num{text-align:right}.acao{display:block;
padding-top:16px}.acao::before{display:none}.report-action{width:100%}.infra-grid{grid-template-columns:1fr}
}
"""
