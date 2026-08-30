# ai-radar — a paper radar that ranks by independent implementations, not by hype.

![tests](https://img.shields.io/badge/tests-401_passing-3fb950)
![python](https://img.shields.io/badge/python-3.12+-3572A5)
![deps](https://img.shields.io/badge/runtime_deps-3-8957e5)
![frontend](https://img.shields.io/badge/frontend-no_framework,_no_build-1f6feb)
![llm](https://img.shields.io/badge/judge-claude--opus--5-d4a373)
![status](https://img.shields.io/badge/status-pre--1.0-db6d28)

ai-radar collects arXiv papers on efficient inference and agent harnesses, counts how many **independent** GitHub repositories implement each one, and publishes a daily digest plus a self-contained web archive. Papers that already broke out in attention are cut on purpose — the point is to find what nobody has looked at yet.

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

Every paper gets a structured judgment from Claude: a closed taxonomy family (19 values), an actionable verdict (`adotar` / `testar` / `observar` / `nao_aplica`), and any quantified gain the abstract claims — normalized to a multiplicative factor, and labeled **claimed by the authors, not verified**, everywhere it appears.

## Install

Requires Python 3.12+.

```bash
git clone https://github.com/lusknchars/ai-radar
cd ai-radar
pip install -e ".[dev]"
```

Three runtime dependencies: `httpx`, `anthropic`, `pydantic`. The frontend has zero — no framework, no build step, no external request. Charts are SVG generated in Python so that chart geometry stays inside the tested boundary; there is a test asserting that a given paper's point lands on a given coordinate.

### Run

```bash
export ANTHROPIC_API_KEY=...
export GH_TOKEN="$(gh auth token)"     # optional; 10 → 30 req/min

python -m radar.cli --dry-run          # reads real state, writes nothing durable
python -m radar.cli                    # the real thing
```

`--dry-run` copies the database to a temp directory, so a rehearsal never consumes the papers of the first real run.

### Seed an empty archive

```bash
python scripts/seed.py inferencia      # ~1090 papers, ~US$4.40, ~1h
python scripts/seed.py agentes         # ~1425 papers, ~US$5.70, ~1h
```

Most of that hour is GitHub, not the LLM. The batch itself takes minutes.

### Secrets

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | judgment and summary |
| `TELEGRAM_BOT_TOKEN` | for push | daily digest |
| `TELEGRAM_CHAT_ID` | for push | digest destination |
| `GH_TOKEN` | no | raises GitHub search limit from 10 to 30 req/min |

No key is needed for citations: OpenAlex resolves 50 papers per request with just a `mailto:` in the User-Agent. Semantic Scholar was measured first and rejected — unauthenticated, it returned `429` on the first call and succeeded 2 times out of 6.

## Architecture

Pure core, thin IO edge. `scoring.py`, `authorship.py`, `render.py`, `svg.py`, `site.py`, `leitura.py` and `site_data.py` import no `httpx`, no `anthropic`, no `sqlite3` — there is a test that enforces it. Every external service takes its transport by injection, so the whole suite runs offline in under a second.

| module | responsibility |
|---|---|
| `arxiv` · `github` · `openalex` · `judge` | the four network adapters |
| `scoring` · `authorship` | the pure decisions |
| `pipeline` | composes a day, counts every cut |
| `store` | SQLite, append-only signal history |
| `render` · `site` · `svg` · `leitura` | markdown, HTML, charts, the reading block |

The repository **is** the production database. `data/radar.db` is committed because the GitHub Actions runner is ephemeral: without it, every run wakes up with an empty database, re-judges every paper daily, and delivers the same paper to Telegram forever.

## What it deliberately does not do

**It does not reproduce papers.** No benchmark, no measurement. Every gain figure is an abstract claim, labeled as such in every place it renders.

**It does not tell you why.** The data supports "how many", never "why". The reading block on the site refuses causal and predictive language, and there is a test over the whole output that enforces it.

**It does not hedge.** Each generated statement carries a guard; a statement whose guard fails is **omitted**, not softened. A block with two solid sentences beats one with six full of "may indicate that".

**It does not use an LLM to write conclusions.** The reading block is arithmetic in a pure function. A model writing those sentences would invent correlation with perfect fluency, and be indistinguishable from correct computation to whoever reads it.

## Status

Pre-1.0, and honest about it.

- The daily cron is dormant: `main` carries no workflow file yet.
- The committed database is still on the pre-migration schema.
- Two blocked tasks: a live schema smoke test and the re-judgment of the seeded archive.
- The reading block, the RSS feed, the editorial redesign, and the two-scope pipeline are done and tested.

401 tests, all offline, all under a second.

## License

Not chosen yet. Until one is added, default copyright applies — no permission granted to use, copy, or distribute.
