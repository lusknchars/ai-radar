
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
