"""Browser assets for Paperraft's generated, no-build frontend.

The renderer in :mod:`radar.site` owns semantic HTML. This module owns the
visual system and progressive enhancement that are inlined into each page.
"""
from __future__ import annotations

from .font_assets import (BE_VIETNAM_PRO_LIGHT_WOFF2_BASE64,
                          BE_VIETNAM_PRO_MEDIUM_WOFF2_BASE64)

BEAM_INPUT_SCRIPT = """
(() => {
  document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return;
    const field = event.target.closest('.beam-input');
    if (!field || event.target.closest('input, button, a')) return;
    const input = field.querySelector('input');
    if (input) input.focus();
  });
})();
"""

# Google Fonts "latin" subset range: covers Portuguese accents (U+00C0-00FF).
_LATIN_RANGE = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,"
    "U+2212,U+2215,U+FEFF,U+FFFD"
)


def _font_face(weight: int, woff2_base64: str) -> str:
    return (
        "@font-face{font-family:'Be Vietnam Pro';font-style:normal;"
        f"font-weight:{weight};font-display:swap;"
        f"src:url(data:font/woff2;base64,{woff2_base64}) format('woff2');"
        f"unicode-range:{_LATIN_RANGE}}}"
    )


# Two faces only: Light (300) carries reading text and display headings,
# Medium (500) carries emphasis, controls and labels. Every weight in STYLES
# resolves to one of them, so no face is synthesized.
_FONT_FACE = (
    _font_face(300, BE_VIETNAM_PRO_LIGHT_WOFF2_BASE64)
    + _font_face(500, BE_VIETNAM_PRO_MEDIUM_WOFF2_BASE64)
)

def math_font_face(font_url: str) -> str:
    """Math face for pages with equations: the reader's local copy first."""
    return (
        '@font-face{font-family:"Paperraft Math";font-style:normal;font-weight:400;'
        'font-display:swap;src:local("STIX Two Math"),local("STIXTwoMath-Regular"),'
        f'url({font_url}) format("woff2")}}'
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

// Filter the published index locally; the header's GET form links here with q.
var filtros = {};
var busca = '';
var mostrarTodos = false;
var corpo = document.querySelector('[data-paper-list]');
var contador = document.getElementById('contador');

function normalizarBusca(texto){
  return texto.normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().trim();
}

function aplicar(){
  var linhas = document.querySelectorAll('.linha'), n = 0;
  var termos = busca.split(/\\s+/).filter(Boolean);
  var recorteAtivo = busca || Object.keys(filtros).some(function(k){
    return Boolean(filtros[k]);
  });
  linhas.forEach(function(tr){
    var passa = Object.keys(filtros).every(function(k){
      return !filtros[k] || tr.getAttribute('data-' + k) === filtros[k];
    }) && termos.every(function(termo){
      return normalizarBusca(tr.getAttribute('data-texto')).indexOf(termo) !== -1;
    });
    var dentroDoRecorte = mostrarTodos || recorteAtivo ||
      tr.getAttribute('data-inicial') !== 'oculta';
    tr.hidden = !(passa && dentroDoRecorte);
    if (passa && dentroDoRecorte) n++;
  });
  if (contador) contador.textContent = n + ' of ' + linhas.length;
  var vazio = document.querySelector('[data-search-empty]');
  if (vazio) vazio.hidden = n !== 0;
}

var limpar = document.querySelector('[data-clear-filters]');
if (limpar) limpar.addEventListener('click', function(){
  filtros = {}; busca = '';
  document.querySelectorAll('[data-filtro]').forEach(function(s){ s.value = ''; });
  document.querySelectorAll('[data-legenda]').forEach(function(b){
    b.setAttribute('aria-pressed', 'false');
  });
  if (campo) campo.value = '';
  if (buscaGlobal) buscaGlobal.value = '';
  atualizarBuscaURL('');
  aplicar();
  if (campo) campo.focus();
});

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
var buscaGlobal = document.querySelector('.paper-search input');
function atualizarBuscaURL(valor){
  var url = new URL(window.location.href);
  if (valor) url.searchParams.set('q', valor);
  else url.searchParams.delete('q');
  window.history.replaceState(null, '', url);
}
if (campo) campo.addEventListener('input', function(){
  busca = normalizarBusca(campo.value);
  if (buscaGlobal) buscaGlobal.value = campo.value;
  atualizarBuscaURL(campo.value.trim());
  aplicar();
});
var buscaInicial = new URLSearchParams(window.location.search).get('q');
if (campo && buscaInicial){
  campo.value = buscaInicial.slice(0, 200);
  if (buscaGlobal) buscaGlobal.value = campo.value;
  busca = normalizarBusca(campo.value);
  aplicar();
}

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
    mostrarTodos = true;
    aplicar();
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

CHART_SCRIPT = r"""
// Observable Plot melhora exploracao e links, mas nunca e o primeiro render.
// Se o asset local falhar, cada SVG auditado no servidor continua visivel.
(function(){
  if (!window.Plot) return;

  function readData(kind){
    var node = document.querySelector('[data-chart-data="' + kind + '"]');
    if (!node) return [];
    try { return JSON.parse(node.textContent); }
    catch (_) { return []; }
  }

  function widthFor(host){
    return Math.max(680, Math.round(host.parentElement.clientWidth || 680));
  }

  function mount(kind, plot){
    var host = document.querySelector('[data-plot-host="' + kind + '"]');
    if (!host || !plot) return;
    host.replaceChildren(plot);
    host.hidden = false;
    var fallback = host.parentElement.querySelector('.plot-fallback');
    if (fallback) fallback.hidden = true;
  }

  var labels = {
    stars_total: 'GitHub stars',
    idade_dias: 'days since publication',
    total_impls: 'total implementations'
  };

  function valueLabel(metric, value){
    if (value !== 1) return labels[metric];
    return {
      stars_total: 'GitHub star',
      idade_dias: 'day since publication',
      total_impls: 'total implementation'
    }[metric];
  }

  function renderFrontier(metric){
    var host = document.querySelector('[data-plot-host="frontier"]');
    var data = readData('frontier');
    if (!host || !data.length) return;
    mount('frontier', Plot.plot({
      className: 'observable-plot',
      width: widthFor(host), height: 470,
      marginLeft: 66, marginBottom: 56, marginRight: 24, marginTop: 22,
      style: {background: 'transparent', color: '#000',
        fontFamily: '"Be Vietnam Pro", ui-monospace, monospace', fontSize: '11px'},
      ariaLabel: 'Independent implementations versus ' + labels[metric],
      ariaDescription: 'Each point opens the original paper on arXiv.',
      x: {label: labels[metric], grid: true, nice: true},
      y: {label: 'independent implementations', grid: true, nice: true},
      color: {type: 'identity'},
      marks: [
        Plot.ruleY([0], {stroke: '#000', strokeOpacity: .24}),
        Plot.dot(data, {
          x: metric, y: 'independent_impls', fill: 'color', r: 6,
          stroke: '#eeeeee', strokeWidth: 2, href: 'url', tip: true,
          title: function(d){ return d.title + '\n' + d.family_label +
            '\n' + d[metric] + ' ' + valueLabel(metric, d[metric]) +
            '\n' + d.independent_impls + ' independent ' +
            (d.independent_impls === 1 ? 'implementation' : 'implementations'); },
          ariaLabel: function(d){ return d.title + ': ' +
            d.independent_impls + ' independent ' +
            (d.independent_impls === 1 ? 'implementation' : 'implementations') + ' and ' +
            d[metric] + ' ' + valueLabel(metric, d[metric]); }
        })
      ]
    }));
  }

  function renderFamilies(){
    var host = document.querySelector('[data-plot-host="families"]');
    var data = readData('families');
    if (!host || !data.length) return;
    var families = Array.from(new Set(data.map(function(d){
      return d.family_label;
    })));
    mount('families', Plot.plot({
      className: 'observable-plot',
      width: widthFor(host), height: Math.max(300, families.length * 125),
      marginLeft: 150, marginBottom: 46, marginTop: 18, marginRight: 24,
      style: {background: 'transparent', color: '#000',
        fontFamily: '"Be Vietnam Pro", ui-monospace, monospace', fontSize: '11px'},
      ariaLabel: 'Monthly paper volume by research area',
      x: {label: 'month', type: 'band', tickRotate: -25},
      y: {label: 'papers', grid: true, nice: true},
      fy: {label: null, domain: families},
      color: {type: 'identity'},
      marks: [
        Plot.barY(data, {
          x: 'month', y: 'count', fy: 'family_label', fill: 'color',
          inset: 2, tip: true,
          title: function(d){ return d.family_label + '\n' + d.month +
            ': ' + d.count + (d.count === 1 ? ' paper' : ' papers'); },
          ariaLabel: function(d){ return d.family_label + ', ' + d.month +
            ': ' + d.count + (d.count === 1 ? ' paper' : ' papers'); }
        }),
        Plot.ruleY([0], {stroke: '#000', strokeOpacity: .22})
      ]
    }));
  }

  function renderGain(){
    var host = document.querySelector('[data-plot-host="gain"]');
    var data = readData('gain').filter(function(d){ return d.gain > 0; });
    if (!host || !data.length) return;
    data.forEach(function(d){
      d.date = new Date(d.month + '-01T00:00:00Z');
    });
    mount('gain', Plot.plot({
      className: 'observable-plot',
      width: widthFor(host), height: 400,
      marginLeft: 66, marginBottom: 52, marginTop: 20, marginRight: 24,
      style: {background: 'transparent', color: '#000',
        fontFamily: '"Be Vietnam Pro", ui-monospace, monospace', fontSize: '11px'},
      ariaLabel: 'Reported gain over time on a logarithmic scale',
      ariaDescription: 'Values reported by the authors and not independently verified.',
      x: {label: 'publication date', grid: true},
      y: {label: 'reported factor · log scale', type: 'log', grid: true},
      color: {type: 'identity'},
      marks: [
        Plot.ruleY([1], {stroke: '#000', strokeDasharray: '5,5'}),
        Plot.dot(data, {
          x: 'date', y: 'gain', fill: 'color', r: 6,
          stroke: '#eeeeee', strokeWidth: 2, href: 'url', tip: true,
          title: function(d){ return d.title + '\n' + d.gain + 'x in ' +
            d.gain_axis + '\nreported, not independently verified'; },
          ariaLabel: function(d){ return d.title + ': ' + d.gain +
            ' times in ' + d.gain_axis + ', reported and not independently verified'; }
        })
      ]
    }));
  }

  renderFrontier('stars_total');
  renderFamilies();
  renderGain();

  document.querySelectorAll('.eixos button[data-eixo]').forEach(function(button){
    button.addEventListener('click', function(){
      renderFrontier(button.getAttribute('data-eixo'));
    });
  });

  var resizeTimer = 0;
  window.addEventListener('resize', function(){
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function(){
      var selected = document.querySelector('.eixos button[aria-pressed="true"]');
      renderFrontier(selected ? selected.getAttribute('data-eixo') : 'stars_total');
      renderFamilies();
      renderGain();
    }, 160);
  });
})();
"""

PAPER_STACK_SCRIPT = r"""
document.querySelectorAll('[data-paper-stack]').forEach(root => {
  const sheets = Array.from(root.querySelectorAll('.paper-sheet'));
  let current = 0;
  const turn = step => {
    current = (current + step + sheets.length) % sheets.length;
    sheets.forEach((sheet, index) => {
      const depth = (index - current + sheets.length) % sheets.length;
      sheet.style.setProperty('--depth', depth);
      sheet.setAttribute('aria-hidden', String(depth !== 0));
    });
    root.querySelector('[data-stack-status]').textContent = `Page ${current + 1} of ${sheets.length}`;
    const source = root.querySelector('[data-stack-source]');
    source.href = source.href.split('#')[0] + `#page=${current + 1}`;
  };
  root.querySelector('.paper-stack').addEventListener('click', () => turn(1));
  root.querySelector('[data-stack-next]').addEventListener('click', () => turn(1));
  root.querySelector('[data-stack-prev]').addEventListener('click', () => turn(-1));
  root.addEventListener('keydown', event => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault(); turn(event.key === 'ArrowRight' ? 1 : -1);
    }
  });
});
"""

STYLES = _FONT_FACE + r"""
.discovery-selections{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:40px}
.discovery-selections .section-head{grid-template-columns:minmax(0,1fr);gap:12px}
.discovery-selections>section{min-width:0;padding:32px 0}
.discovery-papers{padding-left:20px}
.discovery-papers li{padding:16px 0;border-top:1px solid #ddd}
.discovery-papers h3{font-size:18px;line-height:1.4;margin:8px 0}
.discovery-papers h3 a{text-decoration:underline;text-underline-offset:3px}
.discovery-papers p{font-size:13px}
.discovery-papers time,.discovery-papers small{font-size:11px}
@media(max-width:760px){.discovery-selections{grid-template-columns:1fr;gap:0}}
:root{--fundo:#eeeeee;--texto:#000000;--cinza:#dddddd;--acento:#cb2957;
--superficie:color-mix(in srgb,var(--fundo) 68%,var(--cinza));
--superficie-2:#dddddd;
--fraco:color-mix(in srgb,var(--texto) 72%,var(--cinza));
--apagado:color-mix(in srgb,var(--texto) 58%,var(--cinza));
--linha:rgba(0,0,0,.14);--linha-forte:rgba(0,0,0,.28);
--acento-acao:#cb2957;--acento-escuro:#000000;--foco:#cb2957;
--display:"Be Vietnam Pro",ui-sans-serif,system-ui,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
--editorial:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
--sans:"Be Vietnam Pro",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{scroll-behavior:smooth;background:var(--fundo)}
body{margin:0;background:var(--fundo);color:var(--texto);font-family:var(--sans);
font-size:15px;font-weight:300;line-height:1.6;-webkit-font-smoothing:antialiased}
strong,b{font-weight:500}
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
border-bottom:1px solid var(--linha);font-family:var(--sans);font-size:13px}
.nav a{color:var(--apagado);transition:color 160ms ease-out}
.nav a:hover,.nav a[aria-current=page]{color:var(--texto)}
@property --beam-turn{syntax:"<angle>";initial-value:0deg;inherits:false}
@keyframes beam-orbit{to{--beam-turn:1turn}}
.beam-input{position:relative;isolation:isolate;display:flex;align-items:center;gap:10px;
min-width:0;padding:6px 6px 6px 20px;border:1px solid var(--linha-forte);border-radius:999px;
background:linear-gradient(135deg,rgba(255,255,255,.78),rgba(238,238,238,.94))}
.beam-input:focus-within{border-color:var(--acento);box-shadow:0 0 0 3px rgba(203,41,87,.1)}
.beam-input input{min-width:0;width:100%;min-height:44px;padding:0;border:0;background:transparent;
color:var(--texto);font:300 16px var(--sans)}
.beam-input input::placeholder{color:var(--fraco);opacity:1}
.beam-input input:focus-visible{outline:none}
.beam-button{display:flex;flex-shrink:0;align-items:center;justify-content:center;
min-height:44px;padding:10px 22px;border:0;border-radius:999px;
background:linear-gradient(135deg,var(--acento),#a51c45);color:#fff;font:500 13px var(--sans);cursor:pointer;
transition:transform 160ms ease-out,box-shadow 160ms ease-out}
.beam-button:hover{box-shadow:0 3px 12px rgba(165,28,69,.18)}
.beam-button-secondary{background:linear-gradient(135deg,#fff,#d7d3d5);color:var(--texto)}
.beam-button .beam-arrow{width:0;height:16px;margin-left:0;opacity:0;flex:none;color:currentColor;
transform:translateX(-4px);transition:width 180ms ease-out,margin-left 180ms ease-out,opacity 180ms ease-out,transform 180ms ease-out}
.beam-button:is(:hover,:focus-visible) .beam-arrow{width:16px;margin-left:8px;opacity:1;transform:translateX(0)}
.beam-input .beam-button:active{transform:scale(.985)}.beam-button:active .beam-arrow{transform:rotate(-45deg)}
.beam-border{position:absolute;inset:-1px;z-index:2;pointer-events:none;border:1px solid transparent;
border-radius:inherit;background-image:conic-gradient(from var(--beam-turn),transparent 75%,var(--acento) 100%);
background-origin:border-box;animation:beam-orbit 5s linear infinite}
.mask-with-browser-support{-webkit-mask:linear-gradient(#fff 0 0) padding-box,linear-gradient(#fff 0 0);
mask:linear-gradient(#fff 0 0) padding-box,linear-gradient(#fff 0 0);
-webkit-mask-composite:xor;mask-composite:exclude}
@supports not ((mask-composite:exclude) or (-webkit-mask-composite:xor)){.beam-border{display:none}}
.beam-input-compact{padding:2px 16px}
.paper-search{max-width:720px;margin:24px auto 0}
.paper-search>svg{width:20px;height:20px;flex:none;color:var(--fraco)}
.search-help{max-width:720px;margin:12px auto;font-size:13px}.search-help a{text-decoration:underline}
@media(max-width:640px){.beam-input{gap:8px;padding-left:12px}.paper-search{margin-top:18px}
.beam-button{padding-inline:16px}.paper-search>svg{width:18px;height:18px}}
@media(prefers-reduced-motion:reduce){.beam-border{animation:none;--beam-turn:45deg}
.beam-button,.beam-button .beam-arrow{transition:none}.beam-input .beam-button:active,.beam-button:active .beam-arrow{transform:none}}
@media(forced-colors:active){.beam-border{display:none}.beam-input{background:Field;border-color:FieldText}
.beam-input:focus-within{outline:2px solid Highlight;outline-offset:3px}
.beam-input input{color:FieldText}.beam-button{background:ButtonFace;color:ButtonText;border:1px solid ButtonText}}
.masthead{padding:64px 0 56px}.publication-head{max-width:980px}
.publication-head .hero-copy{max-width:790px}
.static-masthead{padding:72px 0 48px}.static-masthead h1{max-width:22ch;
font-size:clamp(38px,6vw,68px);line-height:1;letter-spacing:-.05em}
.article-masthead{max-width:980px;padding-bottom:38px}.article-masthead h1{max-width:18ch;
font-size:clamp(46px,7vw,80px);line-height:.98}.article-deck{max-width:62ch;margin:22px 0 0;
color:var(--fraco);font-size:clamp(19px,2.4vw,26px);line-height:1.4;
letter-spacing:-.012em}.back-link{display:inline-flex;min-height:44px;align-items:center;
margin-bottom:20px;color:var(--fraco);font:10px var(--mono)}.back-link:hover{color:var(--acento)}
.hero-eyebrow{margin:0 0 22px;font-family:var(--mono);font-size:10px;
text-transform:uppercase;letter-spacing:.16em;color:var(--fraco)}
.hero-eyebrow::before{content:"";display:inline-block;width:7px;height:7px;
margin-right:9px;border-radius:50%;background:var(--acento);
box-shadow:0 0 14px rgba(203,41,87,.42)}
h1{max-width:900px;margin:0;font-family:var(--display);
font-size:clamp(48px,7.2vw,88px);font-weight:300;line-height:.94;letter-spacing:-.042em}
h1 .marca{display:block;margin-bottom:18px;font-family:var(--mono);font-size:12px;
font-weight:500;line-height:1;text-transform:uppercase;letter-spacing:.18em;
color:var(--apagado)}
h1 em{font-style:normal;color:var(--acento)}
.hero-deck{max-width:58ch;margin:28px 0 30px;color:var(--fraco);font-size:17px;
line-height:1.55}
.hero-actions{display:flex;align-items:center;flex-wrap:wrap;gap:12px 24px}
.hero-method{display:inline-flex;align-items:center;min-height:44px;font-size:13px;
text-decoration:underline;text-underline-offset:4px}
.hero-note{font-size:13px;color:var(--fraco);margin:20px 0 0}
.search-empty{padding:32px 0}.search-empty p{margin:0 0 10px}
.search-empty button{min-height:44px;padding:10px 16px;background:var(--texto);
color:var(--fundo);border:0;border-radius:6px;font:500 13px var(--sans);cursor:pointer}
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
color:var(--fundo);font:500 12px/1 var(--sans);
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
h2{margin:0;font-family:var(--display);font-size:34px;font-weight:300;
line-height:1.08;letter-spacing:-.025em}
h3{margin:0 0 7px;font-size:18px;font-weight:500;letter-spacing:-.02em}
.sub{max-width:62ch;margin:3px 0 0;color:var(--fraco);font-size:14px;line-height:1.5}
.enquadramento{display:grid;grid-template-columns:1fr 1fr;gap:32px;padding:28px 32px;
border:1px solid var(--linha)!important;border-radius:22px;background:var(--superficie)}
.enquadramento p{margin:0;color:var(--fraco);font-size:14px}.enquadramento strong{color:var(--texto)}
.leitura{display:flex;flex-wrap:wrap;gap:10px;padding:28px 0!important;border:0!important}
.leitura p.frase,.leitura button.frase{flex:1 1 300px;max-width:none;margin:0;
padding:17px 19px;border:1px solid var(--linha);border-radius:16px;
background:var(--superficie);color:var(--fraco);font:300 13px/1.55 var(--sans);
text-align:left}.leitura button.frase{cursor:pointer;transition:border-color 160ms,
background 160ms}.leitura button.frase:hover{border-color:var(--linha-forte);
background:var(--superficie-2)}.leitura b.n{color:var(--texto);font-weight:500;
font-variant-numeric:tabular-nums}.vazio{color:var(--fraco);padding:64px 0;text-align:center}
svg{width:100%;height:auto;display:block;color:var(--fraco)}svg[hidden]{display:none}
footer{display:flex;flex-wrap:wrap;align-items:center;gap:12px 24px;padding:48px 0;
color:var(--fraco);font-family:var(--sans);font-size:12px}
footer span{margin-right:auto}footer a{padding:8px 0;text-decoration:underline;
text-underline-offset:3px}
.eixos,.filtros,.legenda,.research-index,.repos,.cortes,.nota{font-family:var(--sans)}
.chart-suite{display:grid;gap:18px}
.chart-shared-legend{display:flex;align-items:flex-start;gap:18px;padding:14px 18px;
border:1px solid var(--linha);border-radius:14px;background:rgba(238,238,238,.58)}
.chart-shared-legend>span{flex:0 0 auto;padding-top:9px;color:var(--apagado);
font:500 9px var(--mono);text-transform:uppercase;letter-spacing:.12em}
.chart-card{overflow:hidden;border:1px solid var(--linha);border-radius:20px;
background:rgba(238,238,238,.82);backdrop-filter:blur(12px)}
.chart-card-head{display:grid;grid-template-columns:150px minmax(0,1fr);gap:24px;
align-items:start;padding:24px 26px 20px;border-bottom:1px solid var(--linha)}
.chart-card-head h3{margin:0;font-family:var(--display);font-size:25px;font-weight:300;
line-height:1.1;letter-spacing:-.025em}.chart-card-head h3+p{max-width:64ch;margin:7px 0 0;
color:var(--fraco);font-size:12px}.hero-deck,.article-deck,.sub,.chart-card-head h3+p{
font-family:var(--display)}.chart-kicker{margin:3px 0 0;color:var(--acento);
font:500 9px var(--mono);text-transform:uppercase;letter-spacing:.12em}
.chart-card-body{padding:22px 26px 24px}.chart-scroll{width:100%;overflow-x:auto;
overscroll-behavior-inline:contain;scrollbar-width:thin;scrollbar-color:var(--linha-forte) transparent}
.chart-scroll:focus-visible{outline-offset:-2px}.chart-scroll .scatter,
.chart-scroll .avanco{min-width:680px}.chart-scroll .multiplos{min-width:760px}
.chart-card svg text{font-family:var(--mono)}.chart-card circle{transition:opacity 160ms ease-out}
.chart-card circle:hover{opacity:1}.chart-card .baseline{stroke-dasharray:5 5}
.plot-enhancement{min-width:680px}.plot-enhancement figure{margin:0}
.plot-enhancement svg{overflow:visible}.plot-enhancement [aria-label=tip]{font-family:var(--sans)}
.plot-fallback[hidden]{display:none}
.eixos{display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.eixos>span{margin-right:4px;color:var(--apagado);font:500 9px var(--mono);
text-transform:uppercase;letter-spacing:.11em}
.eixos button,.legenda button{min-height:44px;padding:7px 12px;border:1px solid var(--linha);
border-radius:999px;background:transparent;color:var(--fraco);font:500 10px var(--sans);
cursor:pointer}.eixos button:hover,.legenda button:hover{border-color:var(--linha-forte);
color:var(--texto)}.eixos button[aria-pressed=true],.legenda button[aria-pressed=true]{
border-color:color-mix(in oklab,var(--acento) 50%,transparent);color:var(--acento);
background:color-mix(in oklab,var(--acento) 8%,transparent)}
.legenda{display:flex;gap:4px;flex-wrap:wrap;margin-top:0}.legenda i{display:inline-block;
width:6px;height:6px;border-radius:50%;margin-right:6px;vertical-align:middle}
.legenda button{border-color:transparent;padding:6px 9px}.nota{max-width:62ch;margin-top:16px;
color:var(--apagado);font-size:11px}.filtros{display:grid;
grid-template-columns:repeat(2,minmax(130px,180px)) minmax(220px,1fr) auto;
gap:12px;align-items:end;margin-bottom:0;padding:18px 0;border-top:1px solid var(--linha);
border-bottom:1px solid var(--linha)}
.filtros label,.filtros .count-label{display:block;margin-bottom:7px;color:var(--apagado);
font:500 9px var(--mono);text-transform:uppercase;letter-spacing:.12em}
.filtros select{width:100%;min-height:50px;padding:8px 12px;
border:1px solid var(--linha);border-radius:10px;background:var(--fundo);color:var(--texto);
font:500 12px var(--sans)}
.contagem #contador{display:block;min-height:42px;padding:11px 4px;color:var(--fraco);
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
border-radius:999px;color:var(--fraco);font-size:9px;font-weight:500;white-space:nowrap}.tag.adotar{
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
gap:8px;align-content:center}.entry-stage{color:var(--apagado);font:500 8px var(--mono);
text-align:center;text-transform:uppercase;letter-spacing:.1em}.entry-stage::before{content:"";
display:inline-block;width:5px;height:5px;margin-right:6px;border-radius:50%;
background:var(--acento)}.report-action{width:100%}.source-link{color:var(--apagado);
font:8px var(--mono);text-align:center;text-transform:uppercase;letter-spacing:.08em}
.source-link:hover{color:var(--texto)}.show-all{margin-top:18px}.pt{display:inline-block;
width:6px;height:6px;border-radius:50%;
margin-right:7px;vertical-align:middle}.destaque{padding:28px;border:1px solid var(--linha);
border-radius:20px;background:var(--superficie)}.destaque .meta{margin:9px 0 18px;
color:var(--apagado);font:10px var(--mono)}.destaque p.resumo{max-width:65ch;
margin:0 0 24px;color:var(--fraco)}.repos{list-style:none;padding:0;margin:0;font-size:12px}
.repos li{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;padding:10px 0;
border-bottom:1px solid var(--linha)}.repos .quem{color:var(--apagado);font-size:10px}
.repos .indep{color:var(--acento);font-weight:500}.cortes{list-style:none;padding:0;
margin:0;font-size:12px;font-variant-numeric:tabular-nums}.cortes li{display:flex;
justify-content:space-between;max-width:480px;padding:10px 0;border-bottom:1px solid var(--linha)}
.nav .publication-name{margin-right:auto;font:500 25px var(--editorial);letter-spacing:-.04em;color:var(--texto)}
body:has(.research-page) #fundo{opacity:.16}
.research-page .section-head h2{margin:0;font-size:27px;line-height:1.15}
.research-page .section-head{grid-template-columns:minmax(0,1fr);gap:12px;align-items:start}
.research-page .section-head .sub{font-size:13px;line-height:1.55}
.reading-guide-note{font-size:13px;color:var(--fraco);margin:0 0 24px}
.reading-prompts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}
.reading-prompt{scroll-margin-top:24px;border-top:2px solid var(--acento);padding-top:16px}
.reading-prompt h3{margin:0 0 12px;font:400 23px/1.15 var(--editorial)}
.reading-prompt p{margin:0;font-size:14px;line-height:1.7;color:var(--fraco)}
.reading-source{display:inline-flex;align-items:center;min-height:44px;margin-top:20px;
font-size:13px;text-decoration:underline;text-underline-offset:4px}
.brief-claim summary{cursor:pointer;min-height:44px;align-content:center;font:400 22px/1.3 var(--editorial)}
.brief-claim p{font-size:15px;line-height:1.7;color:var(--fraco)}
.equation-note{padding:15px 0;border-top:1px solid var(--linha);font-size:13px;color:var(--fraco)}
.equation-note summary{cursor:pointer;min-height:44px;align-content:center;color:var(--texto)}
.equation-note p{max-width:68ch;line-height:1.65}.equation-note a{display:inline-flex;align-items:center;
min-height:44px;text-decoration:underline;text-underline-offset:4px}
@media(max-width:640px){.reading-prompts{grid-template-columns:1fr;gap:24px}
.nav{flex-wrap:wrap;justify-content:flex-start;padding:14px 0}.nav .publication-name{flex-basis:100%}}
.pagina{max-width:850px}.pagina p,.pagina li{max-width:68ch}.pagina h2{margin-top:34px}
.article-page{max-width:none}
.research-page{max-width:920px}.decision-snapshot{display:grid;
grid-template-columns:minmax(0,1.08fr) minmax(300px,.92fr);overflow:hidden;margin:0 0 14px;
border:1px solid var(--linha-forte);border-radius:20px;background:rgba(238,238,238,.9);
box-shadow:0 18px 54px -46px rgba(0,0,0,.7)}.decision-copy{padding:27px 29px}
.decision-eyebrow{display:flex;align-items:center;gap:9px;margin:0 0 13px;color:var(--acento);
font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.14em}
.decision-eyebrow span{display:inline-flex;min-height:24px;align-items:center;padding:3px 8px;
border:1px solid color-mix(in oklab,var(--acento) 38%,transparent);border-radius:999px}
.decision-copy h2{max-width:18ch;margin:0;
font-size:clamp(28px,4vw,40px);line-height:1.02}.decision-copy h2+p{max-width:52ch;
margin:15px 0 18px;color:var(--fraco);font-size:14px;line-height:1.55}
.decision-copy>span{display:block;max-width:60ch;color:var(--apagado);font:9px/1.55 var(--mono)}
.decision-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;
margin:0;padding:1px;background:var(--linha)}.decision-facts div{min-height:108px;padding:18px;
background:var(--superficie)}.decision-facts dt{color:var(--apagado);font:500 8px var(--mono);
text-transform:uppercase;letter-spacing:.1em}.decision-facts dd{margin:12px 0 0;color:var(--texto);
font:300 16px/1.25 var(--display)}.research-actions{display:flex;flex-wrap:wrap;gap:10px;
align-items:center;margin:0 0 38px;padding-bottom:22px;border-bottom:1px solid var(--linha)}
.research-actions>a:not(.sheen-button){display:inline-flex;min-height:44px;align-items:center;
padding:8px 12px;border:1px solid var(--linha);border-radius:999px;color:var(--fraco);
font:500 9px var(--mono);text-transform:uppercase;letter-spacing:.07em}
.research-actions>a:not(.sheen-button):hover{border-color:var(--linha-forte);color:var(--texto)}
.research-primary-action{width:auto}.research-jumps{display:flex;align-items:center;gap:5px;
overflow-x:auto;margin:0 0 14px;padding:9px 0;border-top:1px solid var(--linha);
border-bottom:1px solid var(--linha);scrollbar-width:thin}.research-jumps span{flex:0 0 auto;
margin-right:5px;color:var(--apagado);font:500 8px var(--mono);text-transform:uppercase;
letter-spacing:.12em}.research-jumps a{display:inline-flex;flex:0 0 auto;min-height:44px;
align-items:center;padding:7px 11px;border-radius:999px;color:var(--fraco);font:500 9px var(--mono);
text-transform:uppercase;letter-spacing:.06em}.research-jumps a:hover{background:var(--superficie);
color:var(--acento)}.research-section{padding:32px 0;
border-top:1px solid var(--linha);scroll-margin-top:24px}.research-section>.section-head{
margin-bottom:24px}.research-decision,.research-signal{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:0;padding:1px;
border:1px solid var(--linha);border-radius:16px;overflow:hidden;background:var(--linha)}
.research-decision div,.research-signal div{min-height:92px;padding:18px;
background:var(--superficie)}.research-decision dt,.research-signal dt{color:var(--apagado);
font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.11em}
.research-decision dd,.research-signal dd{margin:10px 0 0;color:var(--texto);
font:300 18px/1.25 var(--display)}.research-rationale{margin:22px 0 0;padding:17px 19px;
border-left:2px solid var(--acento);background:rgba(203,41,87,.05);color:var(--fraco)}
.research-claims,.research-risks{list-style:none;margin:0;padding:0}
.research-claims>li,.research-risks>li{margin:0;padding:28px 0;
border-bottom:1px solid var(--linha);scroll-margin-top:24px}.research-claims>li:first-child,
.research-risks>li:first-child{padding-top:0}.research-item-head{display:flex;
justify-content:space-between;gap:14px;align-items:center;margin-bottom:12px}
.research-item-head>a,.research-item-head h3{margin:0;color:var(--acento);
font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.11em}
.research-item-head>a:hover{text-decoration:underline}.research-item-head span{display:inline-flex;
min-height:26px;align-items:center;padding:4px 8px;border:1px solid var(--linha);
border-radius:999px;color:var(--apagado);font:500 8px var(--mono);text-transform:uppercase;
letter-spacing:.07em}.research-item-head span[data-basis=source_linked]{
border-color:color-mix(in oklab,var(--acento) 38%,transparent);color:var(--acento)}
.research-item-head span[data-basis=not_evaluated]{border-style:dashed}
.research-claims h3{max-width:38ch;margin:0 0 16px;font-family:var(--editorial);
font-size:clamp(20px,2.6vw,28px);font-weight:400;line-height:1.18}
.research-claim-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
gap:1px;margin:0 0 16px;padding:1px;background:var(--linha)}
.research-claim-facts div{padding:12px;background:var(--superficie)}
.research-claim-facts dt{color:var(--apagado);font:500 7px var(--mono);
text-transform:uppercase;letter-spacing:.1em}.research-claim-facts dd{margin:6px 0 0;
color:var(--fraco);font-size:11px;line-height:1.45}.research-claims blockquote{
max-width:66ch;margin:16px 0 10px;padding:15px 17px;border-left:2px solid var(--acento);
background:rgba(0,0,0,.035);color:var(--fraco);font-size:13px;line-height:1.65}
.equation-stack{display:grid;grid-template-columns:minmax(0,1fr);gap:44px;max-width:100%}
.equation{min-width:0}
.equation-title{font:400 clamp(24px,3vw,34px)/1.15 var(--editorial);margin:0 0 18px;max-width:40ch}
.equation+.equation{border-top:1px solid var(--linha);padding-top:32px}
.equation-reading{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:32px;margin:22px 0}
.equation-reading p{font-size:15px;line-height:1.75;color:var(--fraco);margin:0 0 12px}
.equation-symbols{margin:0}.equation-symbols div{display:grid;grid-template-columns:90px 1fr;gap:12px;margin-bottom:12px}
.equation-symbols dt{font:20px var(--editorial);white-space:nowrap}.equation-symbols sub{font-size:12px}
.equation-symbols dd{margin:0;font-size:13px;color:var(--fraco)}
.equation a{display:inline-flex;align-items:center;min-height:44px;font-size:12px;text-decoration:underline;text-underline-offset:4px}
.equation-evidence{padding-left:18px;border-left:2px solid var(--acento);max-width:72ch}
.equation-evidence h4{font:500 14px var(--display);margin:0 0 8px}
.equation-evidence p{font-size:14px;line-height:1.7;margin:0;color:var(--fraco)}
.research-signal-note{padding:22px 0;border-top:1px solid var(--linha);color:var(--fraco);font-size:12px}
.research-signal-note span{font-weight:500}.research-signal-note p{margin:6px 0}
@media(max-width:640px){.equation-reading{grid-template-columns:1fr;gap:16px}}
.equation-context{max-width:62ch;margin:0 0 14px;color:var(--fraco);font-size:15px;line-height:1.6}
.equation-display{max-width:100%;margin:0;padding:24px 4px;overflow-x:auto;
border-block:1px solid var(--linha);background:transparent}
.equation-display math{display:block;width:max-content;min-width:100%;margin:0 auto;font-family:"Paperraft Math","STIX Two Math","Latin Modern Math","Cambria Math",math;font-size:clamp(21px,2.5vw,29px);line-height:1.5;color:var(--texto)}
.equation-display math+math{margin-top:10px}
.equation-context math{font-family:"Paperraft Math","STIX Two Math","Latin Modern Math","Cambria Math",math;font-size:1.05em}
.equation-eyebrow{margin:12px 0 0;color:var(--apagado);font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.13em}
.equations-provenance{margin:26px 0 0;color:var(--apagado);font:9px var(--mono)}
.research-inference,.research-empty{max-width:66ch;margin:12px 0;color:var(--apagado);
font-size:13px;line-height:1.65}.exposure-grid{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;padding:1px;
border:1px solid var(--linha);border-radius:18px;overflow:hidden;background:var(--linha)}
.exposure-item{min-height:118px;padding:20px;background:var(--superficie)}
.exposure-item p{margin:0;color:var(--fraco);font-size:12px;line-height:1.6}
.exposure-item{min-width:0;padding:24px}
.exposure-item .exposure-answer{font:400 21px/1.4 var(--editorial);color:var(--texto);margin-bottom:20px}
.exposure-note{margin-top:16px}.exposure-note h4{font:500 11px var(--display);margin:0 0 6px;color:var(--texto)}
.exposure-note p{font-size:13px;line-height:1.7}
.exposure-source{margin-top:20px;border-top:1px solid var(--linha);font-size:12px}
.exposure-source summary{padding:14px 0;cursor:pointer;text-decoration:underline;text-underline-offset:4px}
.exposure-source blockquote{margin:8px 0;padding-left:14px;border-left:2px solid var(--acento);font-size:13px;color:var(--fraco)}
.exposure-source a{display:inline-flex;align-items:center;min-height:44px;text-decoration:underline;text-underline-offset:4px}
.exposure-provenance{max-width:78ch;margin:0 0 24px;font-size:12px;line-height:1.7;color:var(--fraco)}
.research-risks p{margin:0;color:var(--fraco);font-size:15px;line-height:1.65}
.research-test{counter-reset:research-step;list-style:none;margin:0;padding:0}
.research-test li{counter-increment:research-step;display:grid;grid-template-columns:34px 1fr;
gap:10px;max-width:70ch;margin:0;padding:13px 0;border-bottom:1px solid var(--linha);
color:var(--fraco)}.research-test li::before{content:counter(research-step,decimal-leading-zero);
color:var(--acento);font:500 9px var(--mono)}.research-questions{padding-left:20px}
.research-questions li{margin:10px 0;color:var(--fraco)}
.research-independent-tests{list-style:none;margin:0;padding:0}
.research-independent-tests li{margin:0;padding:18px 0;border-bottom:1px solid var(--linha)}
.research-independent-tests h3{margin:0 0 8px;font-family:var(--editorial);font-weight:400}
.research-independent-tests h3 a:hover{color:var(--acento)}
.research-independent-tests p{margin:0;color:var(--fraco)}.research-provenance{
max-width:68ch;margin:44px 0 0;padding-top:18px;border-top:1px solid var(--linha);
color:var(--apagado);font:9px/1.7 var(--mono);letter-spacing:.04em}
/* Paper articles share a centered frame, with a narrower column for reading. */
body:has(.research-page){--paper-width:920px;--reading-width:720px}
body:has(.research-page) .article-masthead,
.article-page:has(>.research-page){max-width:var(--paper-width);margin-inline:auto}
.research-page .research-actions{justify-content:center}
.research-page .research-section,
.research-page>.equation-note,
.research-page>.research-signal-note,
.research-page>.research-provenance,
.research-page+.community-discussion{max-width:var(--reading-width);margin-inline:auto}
.research-page .research-section:is(#equations,#exposure,#reading-guide){max-width:none}
.research-page :is(#equations,#exposure,#reading-guide)>.section-head,
.research-page :is(.exposure-provenance,.reading-guide-note){max-width:var(--reading-width);margin-inline:auto}
.research-page .research-section>p:not(.exposure-provenance):not(.reading-guide-note),
.research-page .section-head .sub,
.research-page :is(.research-claims,.research-risks,.research-test,.research-questions,.research-independent-tests)>li{max-width:none}
.research-page+.community-discussion .section-head{grid-template-columns:minmax(0,1fr);gap:12px}
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
justify-content:space-between;gap:18px;margin:0 0 24px;padding:11px 16px;
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
font-size:clamp(25px,3vw,34px);font-weight:300;letter-spacing:-.02em}
.report-section>p,.report-section-deck{max-width:66ch;font-size:17px;line-height:1.75;
color:var(--fraco)}.report-section-deck{margin:0 0 28px}.infra-exhibit{margin:0}
.infra-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;
margin:28px 0 0;padding:1px;border:1px solid var(--linha);border-radius:18px;
overflow:hidden;background:var(--linha)}.infra-grid div{min-height:112px;padding:22px;
background:var(--superficie)}.infra-grid span{display:block;color:var(--apagado);
font:500 8px var(--mono);text-transform:uppercase;letter-spacing:.11em}
.infra-grid b{display:block;max-width:22ch;margin-top:13px;color:var(--texto);
font-family:var(--display);font-size:18px;font-weight:300;line-height:1.2}
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
color:var(--apagado)}.technical-core-summary{display:grid;grid-template-columns:190px 1fr;
gap:24px;margin:0 0 28px;padding:18px 0;border-top:1px solid var(--linha);
border-bottom:1px solid var(--linha)}.technical-core-summary span{color:var(--acento);
font:500 9px/1.5 var(--mono);text-transform:uppercase;letter-spacing:.1em}
.technical-core-summary p{max-width:55ch;margin:0;color:var(--fraco);font-size:16px;
line-height:1.65}.formula-stack{display:grid;gap:18px}.formula-card,.formula-state{
padding:24px;border:1px solid var(--linha);border-radius:16px;background:var(--superficie)}
.formula-latex{max-width:100%;margin:18px 0;padding:22px;overflow-x:auto;
border:1px solid var(--linha);background:var(--texto);color:var(--fundo);
font:18px/1.5 var(--mono);white-space:pre}.formula-meaning{max-width:60ch;margin:0 0 22px;
color:var(--fraco);font-size:16px;line-height:1.7}.formula-variables{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:0 0 20px;
padding:1px;background:var(--linha)}.formula-variables div{display:grid;
grid-template-columns:52px 1fr;gap:10px;padding:12px;background:var(--fundo)}
.formula-variables dt,.formula-variables dd{margin:0}.formula-variables dt code{
color:var(--acento);font:600 13px var(--mono)}.formula-variables dd{color:var(--fraco);
font-size:12px;line-height:1.45}.formula-variables dd span{display:block;margin-top:3px;
color:var(--apagado);font:8px var(--mono)}.formula-steps{counter-reset:formula-step;
margin:0 0 22px;padding:0;list-style:none}.formula-steps li{counter-increment:formula-step;
display:grid;grid-template-columns:26px 1fr;gap:8px;margin:0!important;padding:9px 0;
border-bottom:1px solid var(--linha)}.formula-steps li::before{content:counter(formula-step,decimal-leading-zero);
color:var(--acento);font:9px var(--mono)}.worked-example{margin:22px 0;padding:18px;
border-left:3px solid var(--acento);background:rgba(203,41,87,.06)}
.worked-example figcaption,.formula-assumptions>span,.formula-state>span{display:block;
margin-bottom:10px;color:var(--acento);font:500 8px var(--mono);text-transform:uppercase;
letter-spacing:.11em}.worked-example code,.worked-example samp{display:block;
font:11px/1.6 var(--mono)}.worked-example p{margin:8px 0;color:var(--fraco);
font-size:14px;line-height:1.6}.worked-example samp{color:var(--texto)}
.formula-assumptions{margin:20px 0}.formula-source{max-width:66ch;margin:20px 0 10px;
padding:14px 16px;border-left:2px solid var(--linha-forte);color:var(--apagado);
font-size:12px;line-height:1.6}.formula-state>p{max-width:60ch;margin:0;color:var(--fraco);
font-size:15px;line-height:1.65}.report-source{max-width:68ch;margin:48px 0 0;padding-top:18px;
border-top:1px solid var(--linha);color:var(--apagado);font:9px/1.7 var(--mono);
letter-spacing:.04em}.report-source a{color:var(--acento)}
.report-to-top{position:fixed;right:24px;bottom:24px;z-index:30;display:grid;width:44px;
height:44px;place-items:center;border:1px solid var(--linha-forte);border-radius:50%;
background:var(--fundo);color:var(--texto);opacity:0;pointer-events:none;
transform:translateY(8px);transition:opacity 180ms ease-out,transform 180ms ease-out}
.report-to-top.is-visible{opacity:1;pointer-events:auto;transform:none}
/* Action feedback shares timing across pointer and keyboard interaction. */
:where(button,.research-actions>a,.research-jumps a,.nav a,footer>a,summary){
transition:color 160ms ease-out,background-color 160ms ease-out,
border-color 160ms ease-out,box-shadow 160ms ease-out,transform 160ms ease-out}
.index-sort button{border-radius:6px;min-height:44px}
.index-sort button[aria-sort],.index-sort button:focus-visible,
.research-jumps a:focus-visible,summary:focus-visible{
background-color:rgba(203,41,87,.08);color:var(--acento)}
.filtros input,.filtros select{transition:border-color 160ms ease-out,box-shadow 160ms ease-out}
.filtros select:focus-visible{
border-color:var(--acento);box-shadow:0 0 0 3px rgba(203,41,87,.12)}
.sheen-button:focus-visible{filter:brightness(1.06)}
.sheen-button:focus-visible svg{transform:translateX(2px)}
.sheen-button:focus-visible .sheen-sweep{transform:translateX(105%)}
button:not(:disabled):active{transform:scale(.98)}
button:disabled{cursor:not-allowed;opacity:.55}
@media (hover:hover){
.index-sort button:hover,.research-jumps a:hover,summary:hover{background-color:rgba(203,41,87,.06)}
.research-actions>a:hover{transform:translateY(-2px)}
.nav a:hover,footer>a:hover{color:var(--acento)}
}
@media (prefers-reduced-motion:reduce){
button,a,summary,input,select{transition:none!important}
button:active,.research-actions>a:hover,.sheen-button svg{transform:none!important}
.sheen-sweep{display:none}
}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.sheen-button,
.sheen-button *,.paper-entry,#fundo,.report-to-top{transition-duration:1ms!important}}
@media (max-width:1050px){.index-head,.paper-entry{grid-template-columns:88px minmax(0,1fr) 190px 144px;
gap:18px}}
@media (max-width:900px){.masthead{padding:64px 0}.edition-ledger{grid-template-columns:repeat(2,1fr)}
.edition-ledger div:nth-child(2){border-right:0}.edition-ledger div:nth-child(-n+2){
border-bottom:1px solid var(--linha)}.section-head{grid-template-columns:1fr;gap:8px}.filtros{
grid-template-columns:repeat(2,1fr)}.contagem{grid-column:2}.enquadramento{grid-template-columns:1fr}
.chart-card-head{grid-template-columns:1fr;gap:7px}.chart-kicker{margin:0}
.index-head{display:none}.paper-entry{grid-template-columns:88px minmax(0,1fr) 154px;align-items:start}
.evidence-fingerprint{grid-column:2}.entry-action{grid-column:3;grid-row:1/span 2;align-self:center}
.report-layout{display:block;max-width:860px}.report-toc{display:none}
.report-toc-mobile{display:block}}
@media (max-width:640px){.envelope{padding:0 16px 64px}.nav{gap:14px;overflow-x:auto}
.masthead{padding:50px 0 44px}
h1{font-size:50px}.edition-ledger{grid-template-columns:1fr}.edition-ledger div,
.edition-ledger div+div{padding:13px 0;border-right:0;border-bottom:1px solid var(--linha)}
.edition-ledger div:last-child{border-bottom:0}main>section{padding:54px 0}.enquadramento{padding:22px}
.chart-shared-legend{display:block;padding:12px}.chart-shared-legend>span{display:block;padding:0 7px 6px}
.chart-card{border-radius:16px}.chart-card-head{padding:19px 18px 16px}.chart-card-head h3{font-size:22px}
.chart-card-body{padding:16px 18px 20px}.eixos{gap:6px}.eixos>span{flex-basis:100%}
.filtros{grid-template-columns:1fr}.contagem{grid-column:auto}.paper-entry{grid-template-columns:1fr;
gap:14px;padding:22px 2px}.paper-entry:hover{padding-left:2px}.entry-date,.entry-main,
.evidence-fingerprint,.entry-action{grid-column:1;grid-row:auto}.entry-date{display:flex;
justify-content:space-between;align-items:center}.entry-date span{margin-top:0}.entry-action{margin-top:2px}
.source-link{min-height:30px;padding-top:8px}.report-bar{align-items:flex-start;flex-direction:column;
gap:10px}.report-links{width:100%}.report-links a{flex:1;justify-content:center;text-align:center}
.report-section{padding:40px 0}.report-section-head{gap:8px}.report-section-head>span{flex-basis:24px}
.infra-grid,.evidence-facts,.formula-variables{grid-template-columns:1fr}
.technical-core-summary{grid-template-columns:1fr;gap:8px}.infra-grid div{min-height:92px}
.decision-snapshot{grid-template-columns:1fr}.decision-copy{padding:22px 20px}
.decision-facts div{min-height:92px;padding:16px}.research-actions{align-items:stretch}
.research-actions>a,.research-primary-action{width:100%;justify-content:center;text-align:center}
.research-decision,.research-signal,.exposure-grid,.research-claim-facts{grid-template-columns:1fr}
.research-decision div,.research-signal div{min-height:78px}.exposure-item{min-height:0}
.report-to-top{right:14px;bottom:14px}footer{padding:32px 0}
}
.entry-cover{float:right;width:112px;margin:0 0 16px 22px;display:block;border:1px solid var(--linha);background:white}
.entry-cover img{display:block;width:100%;height:auto}
.entry-cover:hover{border-color:var(--acento)}
.entry-main::after{content:"";display:block;clear:both}
@media(min-width:761px) and (max-width:1050px){.entry-cover{width:88px;margin-left:14px}}
.skill-download{text-decoration:none}
.nav{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);overflow:visible}
.nav .publication-name{grid-column:2;margin:0;justify-self:center;font-size:45px}
.nav-links{grid-column:3;display:flex;justify-content:flex-end;align-items:center;gap:22px}
@media(max-width:1000px){.nav{grid-template-columns:1fr;justify-items:center;gap:14px;padding:16px 0}.nav .publication-name,.nav-links{grid-column:1}.nav-links{justify-content:center;flex-wrap:wrap;gap:12px 18px}}
body:has(.research-page) .article-masthead>.back-link{display:flex;width:var(--reading-width);max-width:100%;margin-inline:auto}
body:has(.research-page) .article-masthead>.hero-eyebrow,
body:has(.research-page) .article-opening>h1{max-width:var(--reading-width);margin-inline:auto}
body:has(.research-page) .article-opening>h1{font-size:clamp(32px,4.4vw,52px);line-height:1.08}
body:has(.research-page) .article-deck{max-width:var(--reading-width);margin:32px auto 0;
font-size:clamp(18px,1.6vw,20px);line-height:1.7;letter-spacing:0}
.research-page #for-builders h3,.research-page #try-it h3{font-size:20px;font-weight:500;margin:28px 0 10px}
.builder-scenario{font-family:var(--editorial);font-size:26px;line-height:1.4}
.benchmark-reading{padding:26px 0;border-bottom:1px solid var(--linha)}
.benchmark-reading h3{font-family:var(--editorial);font-size:26px;font-weight:400;line-height:1.3;margin:0 0 14px}
.benchmark-comparison{display:grid;grid-template-columns:1fr 1fr 1.3fr;gap:20px;margin:24px 0}
.benchmark-comparison dt{font:400 11px/1.5 var(--mono);color:var(--fraco);margin-bottom:8px}
.benchmark-comparison dd{font:400 28px/1.25 var(--editorial);margin:0;overflow-wrap:anywhere}
.benchmark-comparison .benchmark-difference{font-size:22px;color:var(--acento)}
.benchmark-scope,.builder-review-date{font-size:13px;color:var(--fraco);line-height:1.65}
.builder-takeaway{padding-left:20px;border-left:2px solid #cb2957;margin-top:28px}
.research-page #try-it .sheen-button{margin-top:20px}
@media(max-width:520px){.benchmark-comparison{grid-template-columns:1fr 1fr;gap:16px}.benchmark-comparison>div:last-child{grid-column:1/-1}.builder-scenario{font-size:23px}}
.paper-lead-image{margin:32px 0 0;min-width:0}
.paper-lead-image a{display:flex;justify-content:center;padding:28px}
.paper-lead-image img{display:block;width:auto;max-width:100%;height:auto;max-height:460px;
object-fit:contain}
.paper-lead-image figcaption{margin-top:12px;color:var(--fraco);font:300 12px/1.6 var(--sans)}
.paper-lead-image figcaption span{display:block}
@media(max-width:640px){.paper-lead-image{margin-top:24px}.paper-lead-image a{padding:18px}
body:has(.research-page) .article-deck{margin-top:26px}}
.paper-preview{display:grid;grid-template-columns:1fr 1fr;gap:54px;align-items:center;padding:48px 24px 58px;margin:28px 0 48px;border-block:1px solid #d3c9cc}
.paper-preview-copy h2{font-size:28px;font-weight:400;margin:0 0 18px}
.paper-preview-copy p{font-size:14px;line-height:1.75;max-width:38ch}
.paper-preview-copy>a{font-size:12px;text-underline-offset:4px}
.paper-stack{position:relative;display:block;width:100%;max-width:300px;aspect-ratio:0.72;margin:0 auto;padding:0;border:0;background:transparent;cursor:pointer;perspective:1000px}
.paper-sheet{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:white;border:1px solid #d5ced1;border-radius:3px;box-shadow:0 10px 24px #20202418;z-index:calc(4 - var(--depth));transform:translate(calc(var(--depth) * 9px),calc(var(--depth) * -6px)) rotate(calc(var(--depth) * 3deg));transition:transform 360ms ease,opacity 360ms ease}
.paper-stack:hover .paper-sheet{transform:translate(calc(var(--depth) * 13px),calc(var(--depth) * -8px)) rotate(calc(var(--depth) * 4deg))}
.paper-stack-controls{display:flex;align-items:center;gap:16px;margin:22px 0 18px;font-size:12px}
.paper-stack-controls button{width:44px;height:44px;border:1px solid #b5aab0;border-radius:50%;background:transparent;color:#202024;cursor:pointer;font-size:18px}
.paper-stack-controls button:hover{background:#f3dde4}
.paper-stack:focus-visible,.paper-stack-controls button:focus-visible,.skill-download:focus-visible{outline:3px solid #cb2957;outline-offset:6px}
@media(max-width:600px){.paper-preview{grid-template-columns:1fr;gap:42px;padding:30px 12px 40px}.paper-preview-copy{order:2}.paper-stack{max-width:240px}.paper-preview-copy p{max-width:none}}
@media(prefers-reduced-motion:reduce){.paper-sheet{transition:none}.paper-stack:hover .paper-sheet{transform:translate(calc(var(--depth) * 9px),calc(var(--depth) * -6px)) rotate(calc(var(--depth) * 3deg))}}
"""

STYLES += r"""
.nav.has-community{grid-template-columns:1fr;justify-items:center;gap:10px;padding:16px 0 12px}
.nav.has-community .publication-name,.nav.has-community .nav-links{grid-column:1}
.nav.has-community .nav-links{justify-content:center;flex-wrap:wrap;gap:10px 22px}
.community-welcome{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:48px;margin:8px 0 60px}
.community-welcome h2{font:500 31px/1.2 var(--editorial);margin:0 0 18px}
.community-welcome p{max-width:62ch;color:var(--fraco);font-size:14px;line-height:1.8}
.community-links{display:flex;gap:14px 24px;align-items:center;flex-wrap:wrap;margin:24px 0}
.community-links a:not(.sheen-button),.community-forum-link>a{text-decoration:underline;text-underline-offset:4px;font-size:13px}
.community-forum-link{border-left:2px solid var(--acento);padding:4px 0 4px 26px;align-self:start}
.community-forum-link p{font-size:13px}
.community-directory .section-head h2,.community-discussion h2{font-size:28px;font-weight:300;margin:0}
.community-search{display:grid;gap:10px;margin:26px 0 18px}
.community-search label{font-size:13px;font-weight:500}
#community-count,.community-paper-id{font:300 12px/1.7 var(--sans);color:var(--fraco)}
.community-papers{list-style:none;padding:0;margin:18px 0 0}
.community-papers li{padding:24px 0 28px;border-top:1px solid var(--linha)}
.community-papers li>p{font:300 12px/1.7 var(--sans);color:var(--fraco);margin:0 0 8px;display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap}
.community-papers h3{font:500 24px/1.35 var(--editorial);margin:0 0 12px;max-width:65ch}
.community-papers h3 a:hover{color:var(--acento);text-decoration:underline;text-underline-offset:5px}
.community-guidelines{padding:24px 0;border-block:1px solid var(--linha)}
.community-guidelines summary{cursor:pointer;font-size:16px;min-height:44px}
.community-guidelines p{max-width:78ch;font-size:14px;color:var(--fraco);line-height:1.8}
.community-discussion{padding:50px 0}
.community-note{font-size:13px;line-height:1.8;color:var(--fraco);max-width:78ch}
.community-load{min-height:46px;padding:12px 24px;border:0;border-radius:999px;background:var(--acento);color:#fff;font:500 13px var(--sans);cursor:pointer}
.community-load:hover{background:#ac2148}.community-load:disabled{opacity:.6;cursor:wait}
.community-status{font-size:13px;color:var(--fraco)}
.giscus{margin-top:22px}.giscus-frame{width:100%;border:0}
@media(max-width:700px){.community-welcome{grid-template-columns:1fr;gap:28px}.community-forum-link{padding-left:18px}.community-papers h3{font-size:22px}.community-search{grid-template-columns:1fr}.community-search button{justify-self:start}.community-links{align-items:flex-start}.community-discussion{padding:38px 0}}
"""
