# Equations on research pages

**Objective:** show up to three central equations of every indexed paper on
its research page as real typeset mathematics, Greek letters included, in the
site's editorial typography, in English, with no outbound formula links.

**Architecture:** a new `arxiv_html.py` module fetches and parses arXiv's
LaTeXML HTML rendering into equations that carry sanitized MathML, the source
LaTeX, the equation number, the section title, and the sentence that
introduces them. A new `equations.py` module owns the daily collection step:
parse, select with the existing K2.6 formula selector, and store. The store
gains two tables. `site_data` exposes the selected equations on each `Ponto`,
`public_research.py` publishes them in the page model and JSON, and `site.py`
renders one new section. `site_assets.py` owns the math typography.

**Stack:** Python 3.12 standard library for parsing (`html.parser`), Pydantic
for contracts, `pytest`, the existing Kimi adapter. No new Python dependency,
no client-side formula library, no remote font or CDN request. Browsers render
MathML Core natively (Chrome 109+, Safari, Firefox).

---

## Why arXiv HTML and not the TeX bundle

The existing formula pipeline in `formulas.py` extracts display equations
from the arXiv TeX source and only surfaces them inside deep reports, of which
none exist yet. arXiv's HTML rendering is available for 19 of the 20 published
papers and already contains every equation as MathML with the original LaTeX
in `alttext`, numbered and placed under its section heading. Rendering that
MathML natively gives real mathematical typography without compiling TeX,
without a JavaScript renderer, and without linking the reader away.

The deep-report flow is untouched. A later plan may route its candidates
through the same HTML parser; this plan does not.

## Data flow

```text
daily run (after judging, before publishing) and backfill script
                      |
                      v
        GET https://arxiv.org/html/<arxiv_id>      (unversioned, latest)
                      |
                      v
   parse LaTeXML: equations + MathML + LaTeX + number + section + prose
                      |
                      v
              sanitize MathML against an allowlist
                      |
                      v
    K2.6 selector: core kind, up to three equation IDs with roles
                      |
                      v
        store: equation_sources (per paper), equations (per selection)
                      |
                      v
   site_data -> Ponto.equations -> ResearchPage.equations -> section
```

## Parser contract (`arxiv_html.py`)

- `fetch_arxiv_html(arxiv_id, *, get) -> HtmlFetch` with `status` in
  `available`, `unavailable` (HTTP 404), `rejected` (body over 8 MB, or no
  LaTeXML page marker), plus `text` and `sha256` when available. Other HTTP
  errors raise, matching the PDF fetch.
- `parse_arxiv_html(text) -> list[HtmlEquation]`. Each equation carries
  `anchor` (the LaTeXML id such as `S4.E13`, with the trailing row marker
  `X`/`Xa` removed), `label` such as `(13)` or empty, `section` such as
  `4 Methodology` or the appendix title, `position` (document order),
  `latex`, `mathml`, `context_before`, `context_after`.
- Only `math` elements inside equation rows count. Inline math in prose is
  never a candidate. A row with several `math` cells (LaTeXML splits aligned
  columns) is joined in order into one equation. Continuation rows that share
  a number with their parent row merge into it, LaTeX joined with `\\`.
- The LaTeX is the `alttext` as served, minus the `\displaystyle` prefix that
  LaTeXML injects at the start of each cell. Nothing else is rewritten.
- Context comes from the neighbouring `ltx_p` paragraphs in the same
  `ltx_para` block. The plain-text form (math subtrees removed, whitespace
  collapsed) feeds the selector. A second form, `context_html`, keeps the
  paper's inline symbols as sanitized inline MathML inside escaped prose,
  and that is what the page shows, so a sentence such as "Let V_p denote"
  keeps its symbols. Caps match `formulas.py`: 900 characters each side,
  6,000 characters of LaTeX, 100 equations per paper.
- A tag longer than 24 characters is a descriptive name, not a number; the
  equation is treated as unnumbered. An id reused by a non-continuation row
  receives a numeric suffix so anchors stay unique per paper.
- `sanitize_mathml(fragment) -> str` rebuilds the tree and serializes it from
  scratch. Allowed elements: `math`, `mrow`, `mi`, `mn`, `mo`, `mtext`,
  `mspace`, `ms`, `msup`, `msub`, `msubsup`, `mfrac`, `msqrt`, `mroot`,
  `mover`, `munder`, `munderover`, `mtable`, `mtr`, `mtd`, `mstyle`,
  `mpadded`, `mphantom`. `semantics` is unwrapped to its first child and
  `annotation` is dropped. Any other element is replaced by its children.
  Allowed attributes: `display`, `mathvariant`, `stretchy`, `fence`,
  `separator`, `largeop`, `movablelimits`, `symmetric`, `lspace`, `rspace`,
  `minsize`, `maxsize`, `form`, `accent`, `accentunder`, `displaystyle`,
  `scriptlevel`, `linethickness`, `columnalign`, `rowalign`,
  `columnspacing`, `rowspacing`, `width`, `height`, `depth`, `voffset`.
  Values must match a token or CSS-length pattern; anything else is dropped.
  Text is escaped. A sanitized equation over 20,000 characters is discarded.
  Because the output is re-serialized, no script, link, style, or event
  attribute can pass.

## Selection contract (`equations.py`)

- `FormulaCandidate` gains two optional fields, `label` and `section`, both
  empty for TeX candidates. The selector prompt includes them. The candidate
  ID hash covers the anchor, so HTML IDs never collide with TeX IDs.
- `collect_equations(store, papers, *, fetch_html, selector, today)` runs per
  paper: fetch, parse, rank with `rank_formula_candidates`, select, verify by
  ID with `verify_formula_selection`, store. It returns a summary counter of
  outcomes and never raises for one paper; each failure is stored as a status.
- Per-paper status, stored in `equation_sources.status`: `unavailable`,
  `rejected`, `no_equations`, `not_formula`, `selected`, `selector_failed`,
  `parse_failed` (markup the parser or candidate contract rejected).
  `core_kind` stores the selector's classification when one was obtained.
- The daily CLI runs the step only when not in dry-run mode, for every paper
  without a status row (today's papers plus anything a fetch error left
  behind), capped at 40 papers per run. When the LLM provider is not Kimi,
  the step is skipped and the papers stay unfetched; the page states that.
- `scripts/backfill_equations.py` runs the same step for every paper without
  an `equation_sources` row, with `--arxiv-id`, `--limit`, and `--db`.

## Store contract

```sql
CREATE TABLE IF NOT EXISTS equation_sources (
    arxiv_id       TEXT PRIMARY KEY REFERENCES papers(arxiv_id),
    fetched_at     TEXT NOT NULL,
    status         TEXT NOT NULL,
    html_sha256    TEXT,
    core_kind      TEXT,
    selector_model TEXT,
    equation_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS equations (
    arxiv_id   TEXT NOT NULL REFERENCES papers(arxiv_id),
    anchor     TEXT NOT NULL,
    position   INTEGER NOT NULL,
    label      TEXT NOT NULL,
    section    TEXT NOT NULL,
    role       TEXT NOT NULL,
    latex      TEXT NOT NULL,
    mathml     TEXT NOT NULL,
    context    TEXT NOT NULL,
    PRIMARY KEY (arxiv_id, anchor)
);
```

Both tables are additive `CREATE TABLE IF NOT EXISTS` statements in `SCHEMA`,
so the judgment-column preflight and the migration script are unchanged.
Re-running the step for a paper replaces its rows.

## Page contract

- `Ponto` gains `equations: tuple[EquationView, ...]` and
  `equations_status: str` (`not_fetched` when no source row exists).
- `ResearchPage` gains `equations: tuple[ResearchEquation, ...]` and
  `equations_status`. `ResearchEquation` carries `anchor`, `label`,
  `section`, `role`, `latex`, `mathml`, `context`, where `context` is the
  sanitized HTML form of the introducing sentence. The page JSON includes
  them. Schema version stays 1: the fields are additive with defaults.
- A page with `equations_status == "selected"` must carry at least one
  equation; any other status must carry none.

## Rendering

A new `<section id="equations" class="research-section">` titled "Central
equations" sits after the decision block. Each equation renders as:

```html
<article class="equation">
  <p class="equation-context">The loss function can be expressed as follows:</p>
  <div class="equation-display"><math display="block">…</math></div>
  <p class="equation-eyebrow">equation (9) · §4 Methodology · loss function</p>
</article>
```

Absence stays explicit, in English, using the site's existing empty-state
style: "The technical core is an algorithm, not an equation" (or system,
evaluation protocol, concept) for `not_formula`; "arXiv has no HTML rendering
for this paper" for `unavailable` and `rejected`; "No display equations were
found in the arXiv HTML" for `no_equations`; "Equations have not been fetched
yet" for `not_fetched` and `selector_failed`. No equation links to arXiv.

A provenance line closes the section: "equations from arXiv HTML · fetched
YYYY-MM-DD".

## Typography

- One math face. `assets/fonts/stix-two-math.woff2` is a subset of STIX Two
  Math (SIL OFL 1.1, license kept in `assets/fonts/STIXTwoMath-OFL.txt`)
  covering Latin, Greek, general punctuation, letterlike symbols, arrows,
  mathematical operators, miscellaneous technical, supplemental operators,
  combining marks, and the mathematical alphanumeric block, with the `MATH`
  layout table intact so stretchy delimiters and radicals work.
- `@font-face` for `"AI Radar Math"` lists `local("STIX Two Math")` and
  `local("STIXTwoMath-Regular")` before the vendored file, so machines that
  ship the font never download it. Browsers request the file only on pages
  that use the face, which are the pages with equations.
- `math { font-family: "AI Radar Math", "STIX Two Math", "Latin Modern Math",
  "Cambria Math", math; }`. Display equations use `font-size: 1.15em`,
  generous vertical margins, horizontal scrolling inside the block on narrow
  screens, and the site's text color. Body copy stays Be Vietnam Pro.
- `publish_site` copies every `assets/fonts/*.woff2` file into
  `site/assets/fonts/`, next to the vendored chart libraries.

## Failure states

| Condition | Stored status | Page copy |
|---|---|---|
| HTTP 404 | `unavailable` | arXiv has no HTML rendering for this paper |
| Oversized or non-LaTeXML body | `rejected` | same as unavailable |
| Parsed, zero display equations | `no_equations` | No display equations were found in the arXiv HTML |
| Selector says algorithm, system, protocol, concept, none | `not_formula` | The technical core is an algorithm, not an equation (per kind) |
| Selector error or unknown IDs | `selector_failed` | Equations have not been fetched yet |
| Parser or candidate contract rejects the markup | `parse_failed` | Equations could not be extracted from the arXiv HTML |
| Step never ran | no row | Equations have not been fetched yet |

Network errors other than 404 raise inside the fetch adapter and are caught
per paper by the collection step, which records `selector_failed` only when
the selector was reached; a fetch exception leaves no row so the backfill
retries it.

## Implementation slices

### 1. Parser and sanitizer

- [x] Trim a real LaTeXML excerpt into `tests/fixtures/arxiv_html_sample.html`
  with a numbered group, a single equation, an unnumbered one, a continuation
  row, inline math in prose, and an appendix equation.
- [x] `parse_arxiv_html` with anchors, labels, sections, joined cells, merged
  continuation rows, math-free context, `\displaystyle` prefix removal, caps.
- [x] `sanitize_mathml` allowlist, unwrapping, attribute validation, size cap.
- [x] `fetch_arxiv_html` with injected `get`, statuses, hash.

### 2. Store and selection

- [x] Two tables, `record_equations`, `equations_for`, `equation_source`,
  `papers_without_equations`.
- [x] `label` and `section` on `FormulaCandidate` and in the selector prompt.
- [x] `collect_equations` with injected fetch and selector, per-paper
  statuses, replace-on-rerun.

### 3. Page model and rendering

- [x] `Ponto.equations` and `equations_status` from `site_data`.
- [x] `ResearchEquation`, `ResearchPage.equations`, `equations_status`,
  invariant, JSON export.
- [x] Section markup, absence states, provenance line, no outbound links.

### 4. Typography and publishing

- [x] Vendored STIX Two Math subset and OFL file.
- [x] `@font-face` with local-first sources, `math` rules, display block CSS.
- [x] Publish copies fonts; tests assert the file lands and CSS references it.

### 5. Pipeline and backfill

- [x] Daily CLI step after judging, skipped on dry run and non-Kimi providers.
- [x] `scripts/backfill_equations.py` with a fake-selector test.
- [ ] Backfill the 20 published papers (runs in CI with the Kimi key, or
  `scripts/backfill_equations.py` locally), regenerate `site/`, commit.

### 6. Documentation

- [x] README: how it works, architecture, fonts paragraph.
- [x] CONTEXT.md: add "Central equation" to the language list.

## Acceptance criteria

- Every research page has an equations section with either rendered MathML
  or an explicit English absence state.
- No MathML reaches the page without passing the sanitizer; the fixture with
  a script, an `href`, and an unknown element renders none of them.
- No equation links to arXiv; the only arXiv link on the page remains the
  existing "Original paper" link.
- Pages still make no remote font, script, or CDN request. The math font is
  served from the site's own assets and only when the local font is missing.
- The daily run cannot fail because of an equation fetch or selection error.
- The test suite stays offline and under a few seconds.

## Out of scope

- Model-written explanations, glossaries, derivations, or worked examples.
- Anchor links into arXiv HTML.
- Routing deep-report candidates through the HTML parser.
- Switching the daily judge to English and re-judging the archive: a separate
  task that follows this one.
