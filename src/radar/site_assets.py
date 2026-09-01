"""Browser assets for AI Radar's generated, no-build frontend.

The renderer in :mod:`radar.site` owns semantic HTML. This module owns the
visual system and progressive enhancement that are inlined into each page.
"""
from __future__ import annotations

from .font_assets import ELECTROLIZE_WOFF2_BASE64

_FONT_FACE = (
    "@font-face{font-family:'Electrolize';font-style:normal;font-weight:400;"
    "font-display:swap;src:url(data:font/woff2;base64,"
    + ELECTROLIZE_WOFF2_BASE64
    + ") format('woff2');unicode-range:U+0000-00FF,U+0131,U+0152-0153,"
      "U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
      "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}"
)

BACKGROUND_SCRIPT = r"""
// Decorative ordered-dither field. This is deliberately small and local:
// a 2D canvas, a standard 4x4 Bayer threshold matrix and an independent
// sine field. It does not load assets or depend on the React Bits Pro source
// used by the private Frontend Lab reference.
(function(){
  var canvas = document.getElementById('fundo');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d', {alpha: true});
  if (!ctx) return;

  var bayer = [0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5];
  // Values mirror the visual settings chosen in Frontend Lab. The field and
  // renderer below are independent code; only the palette and tuning travel.
  var palette = [[185,45,93], [255,140,130], [255,226,214]];
  var speed = 2.3;
  var intensity = .95;
  var waveScale = 6;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var raf = 0;
  var last = 0;

  function resize(){
    var divisor = window.innerWidth < 700 ? 3.2 : 2.55;
    canvas.width = Math.max(180, Math.min(560,
      Math.round(window.innerWidth / divisor)));
    canvas.height = Math.max(140, Math.min(360,
      Math.round(window.innerHeight / divisor)));
  }

  function draw(seconds){
    var width = canvas.width;
    var height = canvas.height;
    var image = ctx.createImageData(width, height);
    var pixels = image.data;
    var aspect = width / height;
    var time = seconds * speed;
    var i = 0;

    for (var y = 0; y < height; y++){
      var ny = (y / height) * 2 - 1;
      for (var x = 0; x < width; x++){
        var nx = ((x / width) * 2 - 1) * aspect;
        var radius = Math.sqrt((nx + .28) * (nx + .28) +
          (ny - .12) * (ny - .12));
        var marble = nx * .72 + ny * .18 +
          .48 * Math.sin(ny * 1.65 + time * .11) +
          .22 * Math.sin((nx - ny) * 2.15 - time * .08);
        var primaryWave = Math.sin(marble * waveScale + time * .34);
        var foldedWave = Math.sin((radius + marble * .22) *
          (waveScale + 1.8) - time * .19);
        var field = .5 + intensity *
          (primaryWave * .34 + foldedWave * .16);
        var threshold = ((bayer[(y & 3) * 4 + (x & 3)] + .5) / 16 - .5) * .24;
        var toned = Math.max(0, Math.min(.999, field + threshold));
        var color = palette[toned < .335 ? 0 : (toned < .665 ? 1 : 2)];

        pixels[i] = color[0];
        pixels[i + 1] = color[1];
        pixels[i + 2] = color[2];
        pixels[i + 3] = 255;
        i += 4;
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  function shouldAnimate(){
    return !reduce.matches && !document.hidden &&
      window.scrollY < window.innerHeight * 1.15;
  }

  function tick(time){
    raf = 0;
    if (!shouldAnimate()) return;
    if (time - last >= 42){
      draw(time / 1000);
      last = time;
    }
    raf = window.requestAnimationFrame(tick);
  }

  function reconcile(){
    var away = window.scrollY >= window.innerHeight * 1.15;
    canvas.classList.toggle('is-away', away);
    if (!shouldAnimate()){
      if (raf) window.cancelAnimationFrame(raf);
      raf = 0;
      if (reduce.matches) draw(0);
      return;
    }
    if (!raf) raf = window.requestAnimationFrame(tick);
  }

  var resizeTimer = 0;
  window.addEventListener('resize', function(){
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function(){ resize(); draw(0); reconcile(); }, 120);
  });
  window.addEventListener('scroll', reconcile, {passive: true});
  document.addEventListener('visibilitychange', reconcile);
  if (reduce.addEventListener) reduce.addEventListener('change', reconcile);

  resize();
  draw(0);
  reconcile();
})();
"""

REPORT_SCRIPT = r"""
// Progressive enhancement for long reports: reading progress and the current
// section in the contents rail. The article and every anchor work without JS.
(function(){
  var progress = document.querySelector('[data-report-progress]');
  var topLink = document.querySelector('[data-report-top]');
  var links = Array.prototype.slice.call(
    document.querySelectorAll('[data-report-toc] a')
  );
  var sections = links.map(function(link){
    return document.querySelector(link.getAttribute('href'));
  }).filter(Boolean);

  function updateProgress(){
    var root = document.documentElement;
    var total = root.scrollHeight - window.innerHeight;
    var ratio = total > 0 ? Math.min(1, Math.max(0, window.scrollY / total)) : 0;
    if (progress) progress.style.transform = 'scaleX(' + ratio + ')';
    if (topLink) topLink.classList.toggle('is-visible', window.scrollY > 720);
  }

  if ('IntersectionObserver' in window && sections.length){
    var observer = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if (!entry.isIntersecting) return;
        links.forEach(function(link){
          var active = link.getAttribute('href') === '#' + entry.target.id;
          if (active) link.setAttribute('aria-current', 'true');
          else link.removeAttribute('aria-current');
        });
      });
    }, {rootMargin: '-18% 0px -70% 0px'});
    sections.forEach(function(section){ observer.observe(section); });
  }

  window.addEventListener('scroll', updateProgress, {passive: true});
  window.addEventListener('resize', updateProgress);
  updateProgress();
})();
"""

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
    var indice = document.querySelector('.research-index');
    if (indice) indice.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
});

// Filtro, busca e contagem. Tudo sobre `hidden` em linha: sem estado, sem
// URL, sem framework. A contagem existe porque um filtro que devolve pouco e
// indistinguivel de um filtro quebrado sem ela.
var filtros = {};
var busca = '';
var mostrarTodos = false;
var corpo = document.querySelector('[data-paper-list]');
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

STYLES = _FONT_FACE + r"""
:root{--fundo:#eeeeee;--texto:#000000;--cinza:#dddddd;--acento:#cb2957;
--superficie:color-mix(in srgb,var(--fundo) 68%,var(--cinza));
--superficie-2:#dddddd;
--fraco:color-mix(in srgb,var(--texto) 72%,var(--cinza));
--apagado:color-mix(in srgb,var(--texto) 58%,var(--cinza));
--linha:rgba(0,0,0,.14);--linha-forte:rgba(0,0,0,.28);
--acento-acao:#cb2957;--acento-escuro:#000000;--foco:#cb2957;
--display:Electrolize,"Arial Narrow",ui-sans-serif,system-ui,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
--editorial:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
--sans:Switzer,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}
html{scroll-behavior:smooth;background:var(--fundo)}
body{margin:0;background:var(--fundo);color:var(--texto);font-family:var(--sans);
font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
#fundo{position:fixed;inset:0;z-index:0;width:100%;height:100vh;pointer-events:none;
opacity:.3;image-rendering:pixelated;mix-blend-mode:multiply;
-webkit-mask-image:linear-gradient(#000 0%,#000 42%,transparent 92%);
mask-image:linear-gradient(#000 0%,#000 42%,transparent 92%);
transition:opacity 220ms ease-out}
#fundo.is-away{opacity:0}
.pular{position:absolute;left:-9999px;top:0;background:var(--acento);
color:var(--acento-escuro);padding:10px 16px;z-index:20;border-radius:999px}
.pular:focus{left:12px;top:12px}
:focus-visible{outline:2px solid var(--foco);outline-offset:3px}
a{color:inherit;text-decoration:none}
.envelope{position:relative;z-index:1;max-width:1220px;margin:0 auto;padding:0 32px 88px}
.nav{min-height:64px;display:flex;justify-content:flex-end;gap:22px;align-items:center;
border-bottom:1px solid var(--linha);font-family:var(--mono);font-size:10px;
text-transform:uppercase;letter-spacing:.12em}
.nav a{color:var(--apagado);transition:color 160ms ease-out}
.nav a:hover,.nav a[aria-current=page]{color:var(--texto)}
.masthead{padding:96px 0 72px}.publication-head{max-width:980px}
.publication-head .hero-copy{max-width:790px}
.static-masthead{padding:72px 0 48px}.static-masthead h1{max-width:22ch;
font-size:clamp(38px,6vw,68px);line-height:1;letter-spacing:-.05em}
.article-masthead{max-width:980px;padding-bottom:38px}.article-masthead h1{max-width:18ch;
font-size:clamp(46px,7vw,80px);line-height:.98}.article-deck{max-width:62ch;margin:22px 0 0;
color:var(--fraco);font-family:var(--editorial);font-size:clamp(19px,2.4vw,26px);
font-style:italic;line-height:1.4}.back-link{display:inline-flex;min-height:44px;align-items:center;
margin-bottom:20px;color:var(--fraco);font:10px var(--mono)}.back-link:hover{color:var(--acento)}
.hero-eyebrow{margin:0 0 22px;font-family:var(--mono);font-size:10px;
text-transform:uppercase;letter-spacing:.16em;color:var(--fraco)}
.hero-eyebrow::before{content:"";display:inline-block;width:7px;height:7px;
margin-right:9px;border-radius:50%;background:var(--acento);
box-shadow:0 0 14px rgba(203,41,87,.42)}
h1{max-width:900px;margin:0;font-family:var(--display);
font-size:clamp(48px,7.2vw,88px);font-weight:400;line-height:.94;letter-spacing:-.042em}
h1 .marca{display:block;margin-bottom:18px;font-family:var(--mono);font-size:12px;
font-weight:500;line-height:1;text-transform:uppercase;letter-spacing:.18em;
color:var(--apagado)}
h1 em{font-style:normal;color:var(--acento)}
.hero-deck{max-width:58ch;margin:28px 0 30px;color:var(--fraco);font-size:17px}
.dateline{display:none}
.edition-ledger{display:grid;grid-template-columns:1.1fr .65fr .65fr 1.5fr;
gap:0;margin:64px 0 0;padding:0;border-top:1px solid var(--linha);
border-bottom:1px solid var(--linha)}
.edition-ledger div{padding:15px 24px 15px 0;border-right:1px solid var(--linha)}
.edition-ledger div+div{padding-left:24px}.edition-ledger div:last-child{border-right:0}
.edition-ledger dt{color:var(--apagado);font:500 8px var(--mono);text-transform:uppercase;
letter-spacing:.13em}.edition-ledger dd{margin:5px 0 0;color:var(--texto);font:12px var(--mono);
font-variant-numeric:tabular-nums}
/* Port sem React do SheenButton autoral em ~/frontend-lab. A estrutura,
   color-mix, sweep unico, active e reduced-motion continuam iguais. */
.sheen-button{--acc:var(--acento-acao);position:relative;isolation:isolate;display:inline-flex;
align-items:center;justify-content:center;gap:9px;min-height:44px;overflow:hidden;
padding:10px 17px;border:0;border-radius:999px;background:var(--acc);
background:linear-gradient(176deg,color-mix(in oklab,var(--acc) 84%,var(--fundo)) 0%,
var(--acc) 46%,color-mix(in oklab,var(--acc) 74%,var(--texto)) 100%);
color:var(--fundo);font:600 12px/1 var(--sans);
box-shadow:inset 0 1px 0 rgba(238,238,238,.38),
0 10px 30px -12px color-mix(in oklab,var(--acc) 85%,transparent);
cursor:pointer;transition:transform 300ms ease-out,filter 300ms ease-out}
.sheen-button:hover{filter:brightness(1.06)}.sheen-button:active{transform:scale(.96)}
.sheen-button svg{position:relative;width:15px;height:15px;transition:transform 300ms ease-out}
.sheen-button:hover svg{transform:translateX(2px)}
.sheen-button .sheen-label{position:relative;white-space:nowrap}
.sheen-sweep{position:absolute;inset:0;z-index:-1;transform:translateX(-105%);
background:linear-gradient(90deg,transparent,rgba(0,0,0,.2),transparent);
transition:transform 700ms ease-out}.sheen-button:hover .sheen-sweep{transform:translateX(105%)}
.sheen-button.secondary{border:1px solid var(--linha-forte);background:rgba(0,0,0,.035);
color:var(--texto);box-shadow:none}.sheen-button.secondary .sheen-sweep{
background:linear-gradient(90deg,transparent,rgba(203,41,87,.18),transparent)}
main>section{padding:76px 0;border-top:1px solid var(--linha)}
.section-head{display:grid;grid-template-columns:minmax(220px,.7fr) minmax(300px,1fr);
gap:36px;align-items:start;margin-bottom:34px}
h2{margin:0;font-family:var(--display);font-size:34px;font-weight:400;
line-height:1.08;letter-spacing:-.025em}
h3{margin:0 0 7px;font-size:18px;font-weight:520;letter-spacing:-.02em}
.sub{max-width:62ch;margin:3px 0 0;color:var(--fraco);font-size:14px}
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
.eixos,.filtros,.legenda,.research-index,.repos,.cortes,.nota{font-family:var(--sans)}
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
gap:12px;align-items:end;margin-bottom:0;padding:18px 0;border-top:1px solid var(--linha);
border-bottom:1px solid var(--linha)}
.filtros label{display:block;margin-bottom:7px;color:var(--apagado);
font:500 9px var(--mono);text-transform:uppercase;letter-spacing:.12em}
.filtros select,.filtros input[type=search]{width:100%;min-height:42px;padding:8px 12px;
border:1px solid var(--linha);border-radius:10px;background:var(--fundo);color:var(--texto);
font:400 12px var(--sans)}.filtros input[type=search]::placeholder{color:var(--apagado)}
.contagem span{display:block;min-height:42px;padding:11px 4px;color:var(--fraco);
font:400 11px var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.index-sort{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:12px 0;
border-bottom:1px solid var(--linha);font:500 9px var(--mono);color:var(--apagado);
text-transform:uppercase;letter-spacing:.09em}.index-sort>span{margin-right:5px}
.index-sort button{min-height:34px;padding:6px 9px;border:0;background:transparent;
color:var(--fraco);font:inherit;text-transform:inherit;letter-spacing:inherit;cursor:pointer}
.index-sort button:hover,.index-sort button[aria-sort]{color:var(--acento)}
.index-sort button[aria-sort]::after{content:" \2193"}.index-sort button[aria-sort=asc]::after{
content:" \2191"}.research-index{border-top:1px solid var(--linha)}
.index-head,.paper-entry{display:grid;grid-template-columns:100px minmax(0,1fr) 238px 154px;
gap:clamp(16px,2.6vw,36px);align-items:center}.index-head{padding:12px 6px;
border-bottom:1px solid var(--linha)}.index-head span{color:var(--apagado);
font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.13em}
.index-head span::before{content:"\2022  ";color:var(--acento)}.paper-entry{padding:24px 6px;
border-bottom:1px solid var(--linha);transition:padding-left 300ms ease-out,
background 300ms ease-out}.paper-entry:hover{padding-left:15px;
background:linear-gradient(90deg,rgba(203,41,87,.055),transparent 68%)}
.entry-date time,.entry-date span{display:block}.entry-date time{color:var(--fraco);
font:11px var(--mono);text-transform:uppercase}.entry-date span{margin-top:5px;color:var(--apagado);
font:8px var(--mono)}.entry-main{min-width:0}.entry-taxonomy{display:flex;align-items:center;
gap:9px;margin-bottom:8px;color:var(--fraco);font:9px var(--mono);text-transform:uppercase;
letter-spacing:.05em}.entry-main h3{font-family:var(--editorial);font-size:clamp(19px,2vw,25px);
font-weight:400;line-height:1.08}.entry-main h3 a:hover{color:var(--acento)}
.tag{display:inline-flex;min-height:26px;align-items:center;padding:3px 9px;border:1px solid var(--linha);
border-radius:999px;color:var(--fraco);font-size:9px;white-space:nowrap}.tag.adotar{
border-color:color-mix(in oklab,var(--acento) 35%,transparent);color:var(--acento);
background:color-mix(in oklab,var(--acento) 7%,transparent)}
.paper-brief{display:block;max-width:68ch;margin:8px 0 0;color:var(--fraco);
font-size:12px;line-height:1.55}.evidence-fingerprint{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;padding:1px;border:1px solid var(--linha);
background:var(--linha)}.fingerprint-label{grid-column:1/-1;padding:6px 8px!important;
background:var(--superficie);color:var(--apagado)!important;font:500 7px var(--mono)!important;
text-transform:uppercase;letter-spacing:.12em}.evidence-fingerprint div{padding:8px;
background:var(--superficie)}.evidence-fingerprint b,.evidence-fingerprint span{display:block}
.evidence-fingerprint b{color:var(--texto);font:500 12px var(--mono);
font-variant-numeric:tabular-nums}.evidence-fingerprint div span{color:var(--apagado);
font:7px var(--mono);text-transform:uppercase;letter-spacing:.07em}.entry-action{display:grid;
gap:10px;align-content:center}.report-action{width:100%}.source-link{color:var(--apagado);
font:8px var(--mono);text-align:center;text-transform:uppercase;letter-spacing:.08em}
.source-link:hover{color:var(--texto)}.show-all{margin-top:18px}.pt{display:inline-block;
width:6px;height:6px;border-radius:50%;
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
.article-page{max-width:none}
.edicoes{list-style:none;padding:0;margin:24px 0}.edicoes li{padding:14px 0;
border-bottom:1px solid var(--linha);font-family:var(--mono);font-size:12px}
.report-progress{position:fixed;inset:0 0 auto;z-index:40;height:2px;pointer-events:none}
.report-progress span{display:block;width:100%;height:100%;background:var(--acento);
transform:scaleX(0);transform-origin:left center;will-change:transform}
.report-layout{display:grid;grid-template-columns:184px minmax(0,860px);
gap:clamp(28px,4vw,56px);align-items:start;max-width:1120px}
.report-toc{position:sticky;top:88px;align-self:start;margin:18px 0 72px}
.report-toc>p{margin:0 0 12px 15px;color:var(--apagado);font:500 9px var(--mono);
text-transform:uppercase;letter-spacing:.14em}.report-toc nav{display:flex;flex-direction:column;
border-left:1px solid var(--linha)}.report-toc a{margin-left:-1px;padding:8px 0 8px 15px;
border-left:2px solid transparent;color:var(--apagado);font-size:12px;line-height:1.35;
transition:color 180ms ease-out,border-color 180ms ease-out}
.report-toc a:hover,.report-toc a[aria-current=true]{color:var(--texto);
border-left-color:var(--acento)}.report{min-width:0;max-width:860px}
.report-bar{position:sticky;top:0;z-index:12;display:flex;align-items:center;
justify-content:space-between;gap:18px;margin:0 0 24px;padding:11px 0;
border-top:1px solid var(--linha);border-bottom:1px solid var(--linha);
background:rgba(238,238,238,.97)}.report-provenance{display:grid;gap:2px;min-width:0}
.report-provenance span,.report-provenance b{overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}.report-provenance span{color:var(--texto);font-size:11px}
.report-provenance b{color:var(--apagado);font:500 8px var(--mono);
text-transform:uppercase;letter-spacing:.08em}.report-links{display:flex;flex-wrap:wrap;gap:8px}
.report-links a,.evidence-link{display:inline-flex;min-height:44px;align-items:center;
padding:8px 11px;border:1px solid var(--linha);border-radius:10px;color:var(--acento);
font:600 9px var(--mono)}.report-links a:hover,.evidence-link:hover{
border-color:var(--acento);background:rgba(203,41,87,.08)}
.report-toc-mobile{display:none;margin:0 0 26px;border-top:1px solid var(--linha);
border-bottom:1px solid var(--linha)}.report-toc-mobile summary{min-height:44px;padding:11px 2px;
cursor:pointer;color:var(--apagado);font:500 9px var(--mono);text-transform:uppercase;
letter-spacing:.14em}.report-toc-mobile nav{display:grid;padding:0 0 12px 14px;
border-left:1px solid var(--linha)}.report-toc-mobile a{min-height:36px;padding:8px 12px;
border-left:2px solid transparent;color:var(--apagado);font-size:12px}
.report-toc-mobile a[aria-current=true]{border-left-color:var(--acento);color:var(--texto)}
.report-section{scroll-margin-top:92px;padding:52px 0;border-top:1px solid var(--linha)}
.report-section:first-of-type{border-top:0}.report-section-head{display:flex;gap:16px;
align-items:flex-start;margin-bottom:20px}.report-section-head>span{flex:0 0 28px;
padding-top:6px;color:var(--acento);font:500 9px var(--mono);letter-spacing:.1em}
.report-section-head p{margin:0 0 5px;color:var(--apagado);font:500 8px var(--mono);
text-transform:uppercase;letter-spacing:.13em}.report-section-head h2{margin:0;
font-size:clamp(25px,3vw,34px);font-weight:400;letter-spacing:-.02em}
.report-section>p,.report-section-deck{max-width:66ch;font-size:17px;line-height:1.75;
color:var(--fraco)}.report-section-deck{margin:0 0 28px}.infra-exhibit{margin:0}
.infra-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;
margin:28px 0 0;padding:1px;border:1px solid var(--linha);border-radius:18px;
overflow:hidden;background:var(--linha)}.infra-grid div{min-height:112px;padding:22px;
background:var(--superficie)}.infra-grid span{display:block;color:var(--apagado);
font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.11em}
.infra-grid b{display:block;max-width:22ch;margin-top:13px;color:var(--texto);
font-family:var(--display);font-size:18px;font-weight:400;line-height:1.2}
.infra-exhibit figcaption{padding:12px 2px 0;color:var(--apagado);font-size:11px;
line-height:1.55}.infra-exhibit figcaption span,.exhibit-number{display:block;margin-bottom:4px;
color:var(--acento);font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.12em}
.setup-note{display:flex!important;gap:12px;align-items:baseline;margin-top:22px!important;
padding-top:14px;border-top:1px solid var(--linha);font-size:13px!important}
.setup-note span{color:var(--apagado);font:500 8px var(--mono);text-transform:uppercase;
letter-spacing:.12em}.report li{margin:10px 0;color:var(--fraco);line-height:1.65}
.evidence{list-style:none;padding:0;margin:0}.evidence-exhibit{margin:0!important;
padding:28px 0;border-bottom:1px solid var(--linha)}.evidence-exhibit:first-child{padding-top:4px}
.evidence-exhibit h3{max-width:34ch;margin:0 0 17px;font-family:var(--editorial);
font-size:clamp(19px,2.4vw,25px);font-weight:400;line-height:1.15}
.evidence-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;
margin:0 0 17px;padding:1px;background:var(--linha)}.evidence-facts div{padding:12px;
background:var(--superficie)}.evidence-facts dt{color:var(--apagado);font:500 7px var(--mono);
text-transform:uppercase;letter-spacing:.1em}.evidence-facts dd{margin:6px 0 0;color:var(--fraco);
font-size:11px;line-height:1.45}.evidence blockquote{max-width:66ch;margin:16px 0 10px;
padding:15px 17px;border-left:2px solid var(--acento);background:rgba(0,0,0,.035);
color:var(--fraco);font-size:13px;line-height:1.65}.evidence .evidence-link{font-size:9px}
.evidence .evidence-missing{display:block;margin-top:14px;color:var(--apagado);
font:9px var(--mono);text-transform:uppercase;letter-spacing:.08em}.empty-evidence{
color:var(--apagado)}.report-source{max-width:68ch;margin:48px 0 0;padding-top:18px;
border-top:1px solid var(--linha);color:var(--apagado);font:9px/1.7 var(--mono);
letter-spacing:.04em}.report-source a{color:var(--acento)}
.report-to-top{position:fixed;right:24px;bottom:24px;z-index:30;display:grid;width:44px;
height:44px;place-items:center;border:1px solid var(--linha-forte);border-radius:50%;
background:var(--fundo);color:var(--texto);opacity:0;pointer-events:none;
transform:translateY(8px);transition:opacity 180ms ease-out,transform 180ms ease-out}
.report-to-top.is-visible{opacity:1;pointer-events:auto;transform:none}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.sheen-button,
.sheen-button *,.paper-entry,#fundo,.report-to-top{transition-duration:1ms!important}}
@media (max-width:1050px){.index-head,.paper-entry{grid-template-columns:88px minmax(0,1fr) 190px 144px;
gap:18px}}
@media (max-width:900px){.masthead{padding:64px 0}.edition-ledger{grid-template-columns:repeat(2,1fr)}
.edition-ledger div:nth-child(2){border-right:0}.edition-ledger div:nth-child(-n+2){
border-bottom:1px solid var(--linha)}.section-head{grid-template-columns:1fr;gap:8px}.filtros{
grid-template-columns:repeat(2,1fr)}.contagem{grid-column:2}.enquadramento{grid-template-columns:1fr}
.index-head{display:none}.paper-entry{grid-template-columns:88px minmax(0,1fr) 154px;align-items:start}
.evidence-fingerprint{grid-column:2}.entry-action{grid-column:3;grid-row:1/span 2;align-self:center}
.report-layout{display:block;max-width:860px}.report-toc{display:none}
.report-toc-mobile{display:block}}
@media (max-width:640px){.envelope{padding:0 16px 64px}.nav{gap:14px;overflow-x:auto}
.masthead{padding:50px 0 44px}
h1{font-size:50px}.edition-ledger{grid-template-columns:1fr}.edition-ledger div,
.edition-ledger div+div{padding:13px 0;border-right:0;border-bottom:1px solid var(--linha)}
.edition-ledger div:last-child{border-bottom:0}main>section{padding:54px 0}.enquadramento{padding:22px}
.filtros{grid-template-columns:1fr}.contagem{grid-column:auto}.paper-entry{grid-template-columns:1fr;
gap:14px;padding:22px 2px}.paper-entry:hover{padding-left:2px}.entry-date,.entry-main,
.evidence-fingerprint,.entry-action{grid-column:1;grid-row:auto}.entry-date{display:flex;
justify-content:space-between;align-items:center}.entry-date span{margin-top:0}.entry-action{margin-top:2px}
.source-link{min-height:30px;padding-top:8px}.report-bar{align-items:flex-start;flex-direction:column;
gap:10px}.report-links{width:100%}.report-links a{flex:1;justify-content:center;text-align:center}
.report-section{padding:40px 0}.report-section-head{gap:8px}.report-section-head>span{flex-basis:24px}
.infra-grid,.evidence-facts{grid-template-columns:1fr}.infra-grid div{min-height:92px}
.report-to-top{right:14px;bottom:14px}
}
"""
