# ai-radar — a paper radar that ranks by independent implementations, not by hype.

[![tests](https://github.com/lusknchars/ai-radar/actions/workflows/tests.yml/badge.svg)](https://github.com/lusknchars/ai-radar/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.12+-3572A5)
![deps](https://img.shields.io/badge/runtime_deps-4-8957e5)
![frontend](https://img.shields.io/badge/frontend-no_framework,_no_build-1f6feb)
![llm](https://img.shields.io/badge/judge-Kimi_K3_or_Claude-d4a373)
![status](https://img.shields.io/badge/status-pre--1.0-db6d28)

ai-radar collects arXiv papers on efficient inference and agent harnesses, counts how many **independent** GitHub repositories implement each one, and publishes a daily digest plus a self-contained web archive. The archive opens with 30 concise paper briefs; a paper worth more attention can be expanded into a full-text report on demand. Papers that already broke out in attention are cut on purpose — the point is to find what nobody has looked at yet.

![ai-radar](assets/banner.svg)

## Why independent implementations

Citations lag by a year. Stars measure whether a repository got posted somewhere. Neither tells you if a technique is worth your afternoon.

The bet here is that **people reimplementing a paper on their own** is an earlier and harder-to-fake signal. So the scoring is a gate, then a ratio:

```python
BROKE_OUT_STARS     = 1000
BROKE_OUT_CITATIONS = 200

if stars_total > BROKE_OUT_STARS or citations > BROKE_OUT_CITATIONS:
    return None                       # already broke out; not radar material

signal    = log1p(independent_impls) * (1 + 0.5 * log1p(velocity_14d))
attention = log1p(stars_total) + log1p(citations)
score     = signal / (1 + attention)
```

The gate exists because the ratio alone failed a real test case: with GPTQ's actual numbers (103 implementations, 3000 stars, 2500 citations), `log1p` compresses hard enough at the top that the most famous quantization paper in existence ranked **third**. A paper that already broke out is not radar material by definition — it does not get a low score, it does not get scored.

"Independent" means the repository owner is not an author. That is a declared heuristic — surname matching against the author list, plus abstract cross-reference — and every classification is published with the rule that fired it, so you can check it.

### Where the hypothesis currently fails

Measured on the 2026-08-29 seed of 1088 papers: of the 48 papers with 3+ independent implementations, **38 already have attention**.

| stars | papers |
|---|---|
| 0 | 3 |
| 1–9 | 7 |
| 10–99 | 13 |
| 100–999 | 17 |
| 1000+ | 8 |

The premise — implementation precedes attention — is **not supported by this snapshot**. Three explanations are still on the table and this data cannot separate them: the seed is a single point in time with no temporal axis; GitHub's `in:readme` search probably finds repositories of projects that already have traction; or the hypothesis is simply wrong. The daily re-check is the mechanism that will tell them apart.

This number is published on the site itself. A radar that hides evidence against its own premise is exactly the thing it exists not to be.

## How it works

```
arXiv API ──► scope filter ──► known-ID filter ──► Batch API (Claude) ──► judgment
                                                                            │
GitHub search ──► authorship heuristic ──► signal ◄── OpenAlex citations   │
                                                │                           │
                                                └──► gate → ratio → score ◄─┘
                                                              │
                                    ┌─────────────────────────┼──────────────┐
                                    ▼                         ▼              ▼
                              Telegram (3/scope)      Markdown archive   Static site
```

Two scopes run in sequence, each with its own term list, measured before being written into the spec:

| scope | categories | papers/day (measured) |
|---|---|---|
| `inferencia` | cs.LG, cs.CL, cs.DC, cs.AR, cs.PF | ~15 |
| `agentes` | cs.AI, cs.CL, cs.SE, cs.MA | ~25 |

The first scope to discover a paper keeps it. Overlap measured at **1%** — the two literatures are effectively disjoint.

Every paper gets the same structured judgment regardless of provider: a closed
taxonomy family with 19 values, an actionable verdict (`adotar`, `testar`,
`observar`, or `nao_aplica`), and any quantified gain claimed by the abstract.
The pipeline normalizes compatible gains to a multiplicative factor and labels
them **claimed by the authors, not verified** everywhere they appear. Kimi K3
and Claude both write this contract. Neither writes the ranking or editorial
conclusions.

## Two reading levels

The archive is meant to reduce reading time without pretending that an abstract
is evidence.

1. A **paper brief** is generated for every shortlisted paper from its title and
   abstract. It says what the technique replaces, what it costs, and what is
   likely to break. The archive shows the 30 highest-scoring briefs first; search
   and filters still inspect the complete archive.
2. A **deep report** is generated only after the reader asks for one. It reads
   the official arXiv PDF, extracts the mechanism, central claims, baselines,
   mathematics worth reading, failure modes, and the smallest useful test.

Every deep report separates two infrastructure questions:

| Field | Meaning |
|---|---|
| validation tier | the smallest setup that can meaningfully falsify the idea on a local workload |
| evidence tier | the hardware used by the experiment supporting the paper's claim |
| infrastructure basis | whether that classification is explicit in the paper, inferred, or unknown |

The tiers are closed and visible: API/CPU, one 24 GB GPU, one 48–80 GB GPU,
multiple GPUs, cluster, custom hardware, or unknown. “Try it on one GPU” never
means “reproduce a cluster result.”

The static site never receives an API key. “Generate report” opens a prefilled
GitHub issue; an owner-only workflow validates the arXiv ID, downloads the PDF,
uses Kimi, commits the versioned JSON and rendered page, deploys the site, and
comments with the permanent URL. Requests from other accounts are closed
without spending credits. Reopening or duplicating a request is idempotent: an
existing report is republished, not regenerated.

Every evidence claim in a deep report asks Kimi for a PDF page and a short
verbatim excerpt. The pipeline checks that the excerpt exists on that exact
extracted page before publishing a page-level link. A failed check produces an
explicit “source not located” label instead of a citation that only looks
precise. Reports also link to the paper's arXiv page and complete PDF.

### Visual system

AI Radar is laid out as a research publication rather than a monitoring
dashboard. Its editorial index takes structural cues from
[Vetto Research & Blog](https://vetto.ai/companies/research-blog.html): a clear
issue header, dated research entries, compact decks, and a direct path into the
full article. AI Radar replaces Vetto's thumbnails with an evidence fingerprint
built from independent implementations, stars, citations, and claimed gain.
Those numbers earn their space because they explain why each paper entered the
issue.

The publication palette uses `#EEEEEE` as paper, `#000000` as ink, `#DDDDDD`
for secondary structure, and raspberry `#CB2957` for source links and actions.
Family colors use grayscale for inference papers and raspberry variations for
agent papers, so charts belong to the publication instead of looking like an
embedded analytics product.

The interface keeps the SheenButton interaction from the authored Halo family
in `frontend-lab` for report actions. Deep reports take structural cues from
[ProgramBench Vetted](https://vetto.ai/companies/programbench-vetted.html): a
sticky contents rail, a compact source bar, numbered sections, and exhibits
inside a narrow reading column. AI Radar puts the infrastructure comparison
first, then links every verified claim to the supporting PDF page. The palette,
components, copy, and generated markup remain AI Radar's own.

On small screens, each index row becomes a single-column research card. Internal
values such as `cache_kv` and `single_gpu_24gb` stay stable in data and filters,
while the interface renders labels such as "cache KV" and "1 GPU, até 24 GB".

Everything is semantic HTML and plain CSS generated by Python. There is no React
bundle, client build, remote font, or component-library dependency.

## Install

Requires Python 3.12+.

```bash
git clone https://github.com/lusknchars/ai-radar
cd ai-radar
pip install -e ".[dev]"
```

Four runtime dependencies: `httpx`, `anthropic`, `pydantic`, and `pypdf`. The frontend has zero — no framework, no build step, no external asset request. Charts are SVG generated in Python so that chart geometry stays inside the tested boundary; there is a test asserting that a given paper's point lands on a given coordinate.

### Run

```bash
export RADAR_LLM_PROVIDER=kimi
export KIMI_API_KEY=...
# Keys from platform.kimi.com use https://api.moonshot.cn/v1 instead.
export RADAR_KIMI_BASE_URL=https://api.moonshot.ai/v1
export GH_TOKEN="$(gh auth token)"     # optional; 10 → 30 req/min

python -m radar.cli --dry-run          # reads real state, writes nothing durable
python -m radar.cli                    # the real thing
```

`--dry-run` copies the database to a temp directory, so a rehearsal never consumes the papers of the first real run.

To generate one deep report locally after the paper is in the migrated archive:

```bash
export RADAR_LLM_PROVIDER=kimi
python scripts/gerar_relatorio.py --arxiv-id 2608.11111
```

This is a paid call. If `reports/2608.11111.json` already exists, the command
only republishes it and spends no additional credits.

Anthropic remains available by setting `RADAR_LLM_PROVIDER=anthropic` and
`ANTHROPIC_API_KEY`. With no explicit provider, a lone Kimi key selects Kimi.
All other configurations preserve Anthropic as the default.

### LLM providers

Both adapters return `dict[str, Judgment]`, keyed by canonical arXiv ID. The
pipeline never sees an SDK response, reasoning trace, or provider-specific
error object.

| Provider | Daily judgment path | Structured output | Operational behavior |
|---|---|---|---|
| Kimi K3 | Chat Completions, one paper per request | strict JSON Schema; only final `message.content` is parsed | low reasoning effort, bounded retries, account-tier throttle |
| Kimi K2.6 | formula candidate selection only | strict JSON Schema over source candidate IDs | thinking disabled by default; cannot author source formulas or final report prose |
| Anthropic | Message Batches | Pydantic schema through `output_config.format` | results may arrive out of order and are joined by `custom_id` |

The exact provider and model are stored with every judgment. Changing models
therefore creates attributable data rather than silently rewriting the archive.
Kimi has separate international and China-platform credentials, so
`RADAR_KIMI_BASE_URL` must match the platform where the key and credits live.

### Migrate the committed archive

The committed database predates the current judgment schema. Reclassify it
with a reviewed Kimi canary before resuming the scheduled pipeline:

```bash
export RADAR_LLM_PROVIDER=kimi
export KIMI_API_KEY=...

python scripts/migrar_e_rejulgar.py --canary 20
# Review the 20 family, practice, and gain classifications printed above.
python scripts/migrar_e_rejulgar.py --execute
```

Kimi K3 has no Batch API, so the script checkpoints every completed judgment
in `data/rejudge-kimi.jsonl`. A stopped run resumes from that file without
paying for completed papers again. It does not alter `data/radar.db` until all
1,088 judgments exist. It also keeps a verified backup and restores it if the
distribution quality gate fails.

### Seed an empty archive

```bash
python scripts/seed.py inferencia      # ~1090 papers, ~US$4.40, ~1h
python scripts/seed.py agentes         # ~1425 papers, ~US$5.70, ~1h
```

Most of that hour is GitHub, not the LLM. The batch itself takes minutes.

### Secrets

| Variable | Required | Purpose |
|---|---|---|
| `RADAR_LLM_PROVIDER` | no | `kimi` or `anthropic` |
| `KIMI_API_KEY` | with Kimi | judgment and summary |
| `ANTHROPIC_API_KEY` | with Anthropic | judgment and summary |
| `RADAR_MODEL` | no | overrides the provider default model |
| `RADAR_FORMULA_MODEL` | no | formula selector; defaults to `kimi-k2.6` without changing the final report model |
| `RADAR_FORMULA_THINKING` | no | `enabled` or `disabled`; defaults to `disabled` |
| `RADAR_KIMI_BASE_URL` | no | use `https://api.moonshot.cn/v1` for keys created on the China platform |
| `RADAR_KIMI_REQUEST_INTERVAL` | no | seconds between Kimi calls; defaults to 20 for the initial tier |
| `TELEGRAM_BOT_TOKEN` | for push | daily digest |
| `TELEGRAM_CHAT_ID` | for push | digest destination |
| `GH_TOKEN` | no | raises GitHub search limit from 10 to 30 req/min |

For report generation in GitHub Actions, add `KIMI_API_KEY` as a repository
secret and optionally set `RADAR_MODEL` and `RADAR_KIMI_BASE_URL` as repository
variables. `report.yml` fixes the provider to Kimi for this paid path;
`RADAR_LLM_PROVIDER` continues to select the daily brief adapter.

No key is needed for citations: OpenAlex resolves 50 papers per request with just a `mailto:` in the User-Agent. Semantic Scholar was measured first and rejected — unauthenticated, it returned `429` on the first call and succeeded 2 times out of 6.

## Architecture

The code has a pure decision core and a thin IO edge. `cli.py` is the composition
root. It reads configuration, selects concrete adapters, and passes their
interfaces into `run_day(...)`. The pipeline does not construct HTTP clients or
read credentials.

```text
                     adapters                       pure decisions

 arXiv --------> Discovery ----+
 Kimi/Claude ---> Judgment -----+--> run_day() --> DayResult --> Markdown/Telegram
 GitHub --------> Signal -------+       |
 OpenAlex ------> citations ----+       v
                                      Store
                                        |
                                        v
                                     SiteData --> HTML / RSS / daily editions
```

The on-demand path is separate from `run_day(...)`:

```text
paper action --> owner GitHub issue --> report workflow --> official arXiv source
                                                           |             |
                                                           v             v
                                                verified technical core  K3 narrative
                                                           \             /
                                                            v           v
                                                    reports/<arxiv-id>.json
                                                             |
                                                             v
                                                 static report + republished index
```

### The main seams

| Seam | Interface | Adapters or consumers | Invariant kept behind it |
|---|---|---|---|
| discovery | `fetch_papers(scope) -> Discovery` | arXiv adapter | every rejected paper contributes a named cut |
| judgment | `judge_all(papers) -> dict[arxiv_id, Judgment]` | Kimi K3, Anthropic | provider output must satisfy the same closed schema |
| implementation signal | `fetch_signal(paper, day) -> Signal, repos` | GitHub adapter | author-owned repositories never count as independent |
| citations | `fetch_citations(ids) -> int or None` | OpenAlex adapter | unknown citations remain `None`, never a false zero |
| archive read model | `Store.site_data(day) -> SiteData` | HTML, SVG, RSS renderers | presentation code never queries SQLite |
| frontend rendering | `render_site(SiteData, ...) -> str` | publisher and archived editions | `site.py` owns semantic HTML; `site_assets.py` owns the inlined CSS and progressive enhancement |
| deep report | `generate_report(paper, full_text, judge, technical_core=..., provider=..., model=...) -> ReportDocument` | verified formula extraction and K3 narrative | K3 cannot author source formulas; evidence infra and minimum-test infra remain separate |
| publishing | `publish_site(store, root, day, reports_root=...)` | daily CLI, report workflow | rendering never starts collection or another paid judgment |

The judgment seam is now real rather than hypothetical. Kimi and Anthropic have
different request formats, rate limits, retry behavior, and batch semantics,
but callers learn one interface. The adapter owns that complexity. This keeps
provider changes local and lets the same pipeline tests exercise both paths
without network access.

`scoring.py`, `authorship.py`, `render.py`, `svg.py`, `site.py`, `site_assets.py`,
`leitura.py`, and `site_data.py` import no `httpx`, `anthropic`, or `sqlite3`. A
test enforces that rule. The frontend remains a single-file artifact at
publication time, but its source has a clear seam: renderers own semantic HTML
and the asset module owns design tokens, responsive CSS, and browser behavior.
The dither-wave background is an original, dependency-free 2D canvas effect:
it combines a standard 4x4 Bayer threshold with an independent warped sine
field. Its three wave colors match the visual settings chosen in Frontend Lab:
`#B92D5D`, `#FF8C82`, and `#FFE2D6`. It does not publish or reproduce the
private React Bits Pro source used as a visual reference. Motion stops when the
reader requests reduced motion, leaves the opening viewport, or moves the tab
into the background. Display headings use the official Electrolize Regular 400 Latin
WOFF2 build from Google Fonts. The publisher embeds it as a data URI, so the
single-file pages still make no font request. Its OFL 1.1 license is kept in
`assets/fonts/Electrolize-OFL.txt`.
PDF retrieval is isolated in `fulltext.py`; report JSON and page rendering stay
deterministic and offline-testable. Network adapters accept their transports by
injection, so the test suite runs without secrets.

### State and failure handling

`Store` owns SQLite writes and historical queries. Signals are append-only
because resurrection is a difference between observations, not a mutable field
on a paper. `data/radar.db` is committed because each GitHub Actions runner is
ephemeral. Without the committed state, every run would rejudge old papers and
deliver duplicates.

The composition root also owns failure policy:

- `--dry-run` works on a temporary database copy.
- A schema preflight stops before any network call when code and database do
  not match.
- Missing or invalid provider results become named `sem_julgamento` cuts
  instead of disappearing.
- The Kimi archive migration checkpoints each paid result before continuing.
- Report requests are owner-only, validate a modern arXiv ID, and do not expose
  the Kimi key to browser code.
- Site deployment only runs when `site/index.html` exists.

## What it deliberately does not do

**It does not reproduce papers.** No benchmark, no measurement. Every gain figure is an abstract claim, labeled as such in every place it renders.

**It does not tell you why.** The data supports "how many", never "why". The reading block on the site refuses causal and predictive language, and there is a test over the whole output that enforces it.

**It does not hedge.** Each generated statement carries a guard; a statement whose guard fails is **omitted**, not softened. A block with two solid sentences beats one with six full of "may indicate that".

**It does not use an LLM to write conclusions.** The reading block is arithmetic in a pure function. A model writing those sentences would invent correlation with perfect fluency, and be indistinguishable from correct computation to whoever reads it.

## Status

Pre-1.0, and honest about it.

- The scheduled workflow is installed on the default branch, but it cannot complete until the committed database is migrated.
- GitHub Pages uses GitHub Actions on `main`; the first artifact waits for the database migration below.
- The committed database is still on the pre-migration schema.
- The 20-paper Kimi connectivity canary completed; the full archive re-judgment remains pending.
- RSS, stable daily-edition URLs, the about page, the reading block, the editorial redesign, and the two-scope pipeline are done and tested.
- The 30-brief archive and owner-only, full-text report path are implemented but remain unproven in the default-branch Actions environment.

The test suite runs offline and completes in about one second on the current development machine.

## License

Not chosen yet. Until one is added, default copyright applies — no permission granted to use, copy, or distribute.
