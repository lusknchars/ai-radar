# Chart library decision for AI Radar

Date: 2026-09-02

## Decision

Use **Observable Plot 0.6.17** as a progressive enhancement for the research
signal charts. Keep the existing Python-rendered SVG as the first render and
no-JavaScript fallback.

Plot and its pinned D3 7.9 runtime are vendored from their official npm
releases. The checked-in UMD assets total 488,889 bytes (about 162 KB when both
are gzip-compressed); both use the ISC license. Publication copies the fixed
assets into the generated site, so the browser does not contact a CDN and daily
runs do not need Node or a frontend build.

## Why it fits this codebase

- Plot returns SVG by default. AI Radar can preserve inspectable marks, sharp
  rendering and useful browser semantics.
- Its grammar is built from layered marks instead of pre-baked chart types.
  That maps directly to the radar's dots, baselines, facets and annotations.
- Marks support titles, links and per-item ARIA labels. A paper dot can be both
  an explorable value and a direct link to the arXiv source.
- Plot accepts tidy arrays of objects, which match the small JSON snapshots the
  Python publication layer can safely embed in each static page.
- The generated site remains readable if the library fails to load: semantic
  headings, notes and the original audited SVG stay in the document.

Official references:

- [Plot overview and layered marks](https://observablehq.com/plot/)
- [Plot rendering contract](https://observablehq.com/plot/features/plots)
- [Plot accessibility options](https://observablehq.com/plot/features/accessibility)
- [Plot package and ISC license](https://github.com/observablehq/plot/blob/main/package.json)

## Alternatives considered

### Apache ECharts 6.1

ECharts has a strong interaction toolbox, mobile support and both Canvas and
SVG renderers. It is a better choice for dashboards with zooming, brushing,
streaming or very large datasets. AI Radar has tens of papers, not thousands,
and would pay for a much broader runtime. Its ARIA component is also opt-in,
while this project needs accessibility to be part of every chart contract.

- [ECharts feature set](https://echarts.apache.org/en/feature.html)
- [SVG versus Canvas guidance](https://echarts.apache.org/handbook/en/best-practices/canvas-vs-svg/)
- [ECharts accessibility setup](https://echarts.apache.org/handbook/en/best-practices/aria/)

### Chart.js 4.5

Chart.js is approachable and mature, but it renders into Canvas. Its own
documentation states that Canvas content is not available to screen readers;
authors must supply ARIA or fallback content. AI Radar already owns an SVG
fallback, so replacing it with Canvas would move the implementation away from
the project's evidence and accessibility goals.

- [Chart.js accessibility guidance](https://www.chartjs.org/docs/latest/general/accessibility.html)

### Vega-Lite 6.4

Vega-Lite has a rigorous declarative grammar and supports ARIA descriptions in
SVG output. Browser embedding, however, brings Vega, Vega-Lite and Vega-Embed
together. That is a good trade for a general visualization platform, but more
runtime and configuration than these three editorial views need.

- [Vega-Lite embedding](https://vega.github.io/vega-lite/usage/embed.html)
- [Vega-Lite accessibility configuration](https://vega.github.io/vega-lite/docs/config.html)

## Integration boundary

The Python renderer remains the source of chart data, labels and claims. It
serializes only trusted scalar fields into inert JSON. Observable Plot owns the
enhanced browser rendering and interaction, not scoring, aggregation or data
selection.

```text
Store -> SiteData -> audited Python SVG (always present)
                  -> inert chart JSON -> Observable Plot SVG (when JS loads)
```

This boundary keeps data decisions testable in Python. A library upgrade can
change layout and interaction, but it cannot silently change which papers or
values appear.

## Rollout checks

- The library is loaded from `/ai-radar/assets/`, never a CDN.
- A failed or blocked script leaves the original SVG visible.
- Every point has a human-readable label and links to its arXiv page.
- Reduced-motion users get no chart animation.
- The existing coordinate and aggregation tests continue to guard the fallback.
- Publication tests assert that the pinned asset is copied into the site.
