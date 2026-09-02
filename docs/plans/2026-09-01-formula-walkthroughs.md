# Formula walkthroughs

**Objective:** add source-grounded, step-by-step formula walkthroughs to deep
reports without manufacturing mathematics for papers whose technical core is
an algorithm, system design, or evaluation protocol.

**Architecture:** a deep `formulas.py` module exposes one interface,
`extract_formula_walkthroughs(source, selector)`. Its implementation owns
candidate extraction, model selection, source validation, failure states, and
worked-example verification. `report.py` receives validated walkthroughs;
`site.py` only renders them.

**Model routing:** deterministic code extracts and verifies source material.
Kimi K2.6 with thinking disabled selects and classifies candidates. Kimi K3 at
low reasoning effort remains responsible for final report synthesis and
ambiguous cases. A live canary must prove K2.6 satisfies the required structured
output before it becomes the default formula selector.

**Stack:** Python 3.12, Pydantic, `pytest`, existing Kimi Chat Completions
adapter. No remote browser asset and no client-side formula dependency.

---

## Why a separate model role

The current `RADAR_MODEL` controls daily judgments and complete deep reports.
Reusing it for formula selection would either pay K3 prices for a narrow
classification task or accidentally downgrade the final report.

The formula selector receives a small set of exact candidates and nearby source
text. It may select, classify, or reject a candidate. It may not write a new
source formula. This makes a cheaper model useful without giving it authority
over evidence.

As of 2026-09-01, Moonshot lists K3, K2.7 Code, and K2.6 as supported models.
K2.5, the old K2 series, and `moonshot-v1` are retired. K2.6 is the supported
general-purpose choice for the selector and can run with thinking disabled.
K3 supports strict structured output and remains the synthesis model.

References:

- [Moonshot model list](https://platform.kimi.ai/docs/models)
- [Kimi K2.6 request modes](https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart)
- [Kimi K3 structured output](https://platform.kimi.ai/docs/guide/kimi-k3-quickstart)
- [Moonshot batch pricing](https://platform.kimi.ai/docs/pricing/batch)

## Data flow

```text
PDF pages + optional arXiv TeX source
                  |
                  v
       deterministic candidate extraction
                  |
                  v
     K2.6 non-thinking candidate selection
                  |
                  v
       exact-source and page validation
                  |
                  v
       deterministic worked calculation
                  |
                  v
          K3 report synthesis
                  |
                  v
        static formula walkthrough card
```

## Domain contract

The report schema advances to version 3 and replaces the loose
`math_to_understand: list[str]` field with a technical core that can explicitly
represent absence.

```python
FormulaStatus = Literal[
    "exact", "concept_only", "not_applicable", "extraction_failed",
]

FormulaRole = Literal[
    "baseline", "proposed_method", "loss", "metric", "complexity",
]

class FormulaWalkthrough(BaseModel):
    status: FormulaStatus
    role: FormulaRole | None
    latex: str
    source_page: int | None
    source_excerpt: str
    plain_language: str
    variables: list[FormulaVariable]
    derivation_steps: list[str]
    worked_example: WorkedExample | None
    assumptions: list[str]
```

Invariants:

- `exact` requires non-empty LaTeX, a page, and a verified source excerpt.
- Other statuses require empty LaTeX and no page citation.
- A source formula must exist verbatim in the TeX source or have a verified PDF
  representation. Kimi cannot author it.
- A worked example is always labeled as an AI Radar calculation.
- Numeric example results are recomputed by a restricted arithmetic evaluator.
- Unsupported expressions receive an explanation but no numeric result.
- Existing schema-version-2 reports continue to load and render.

## Model configuration

Add role-specific configuration instead of overloading `RADAR_MODEL`:

| Variable | Default | Responsibility |
|---|---|---|
| `RADAR_MODEL` | `kimi-k3` for Kimi | daily judgment and final report |
| `RADAR_FORMULA_MODEL` | `kimi-k2.6` | formula candidate selection |
| `RADAR_FORMULA_THINKING` | `disabled` | bounded extraction behavior |

Every saved report records the provider and model used for formula selection.
If the K2.6 structured-output canary fails, the report path falls back to K3 at
low reasoning effort and records that fallback.

## Implementation slices

### 1. Contract and explicit absence

- [x] Add formula domain types in `formulas.py`.
- [x] Enforce cross-field invariants with Pydantic validators.
- [x] Add schema-version-2 compatibility at the report-loading seam.
- [x] Replace the fixed mathematics list with a technical-core result.
- [x] Test exact, concept-only, not-applicable, and extraction-failed states.

### 2. Role-specific model routing

- [x] Add `load_formula_model()` and `load_formula_thinking()`.
- [x] Build K2.6 requests without K3-only `reasoning_effort`.
- [x] Keep the existing K3 request shape unchanged.
- [ ] Record token usage, selector model, retry count, and fallback reason.
- [ ] Add a paid, opt-in live canary that never runs in the normal test suite.

### 3. Source acquisition and candidates

- [ ] Evolve full-text acquisition into a `PaperSource` value containing PDF
  pages and optional TeX files.
- [ ] Download the arXiv source with byte and file-count limits.
- [ ] Reject path traversal and never compile or execute TeX.
- [ ] Extract equation environments with section and paragraph context.
- [ ] Preserve exact source strings and stable candidate identifiers.
- [ ] Fall back to explicit `extraction_failed` when PDF text damages notation.

### 4. Selection and grounding

- [ ] Give K2.6 candidate identifiers, context, and contribution type.
- [ ] Require strict structured output containing only selected identifiers.
- [ ] Verify every identifier and exact LaTeX string after the model call.
- [ ] Locate the supporting PDF page and excerpt.
- [ ] Reject the whole candidate rather than repair unsupported output.

### 5. Worked examples

- [ ] Define a restricted arithmetic expression format.
- [ ] Parse with `ast` and allow only numeric literals and approved operators.
- [ ] Reject names, calls, attributes, indexing, and arbitrary Python.
- [ ] Recompute substitutions and final values deterministically.
- [ ] Label operation counts separately from measured speedups.

### 6. Article rendering

- [x] Rename the section to "Da equação ao teste".
- [x] Render formula, plain-language meaning, symbol glossary, derivation,
  worked example, assumptions, and source link.
- [x] Render technical-core alternatives for algorithms, systems, and protocols.
- [ ] Generate safe MathML at publication time with a raw-LaTeX fallback.
- [x] Add mobile overflow for formula text without a CDN.
- [ ] Add a copy action for raw formula text.

### 7. Evaluation and rollout

- [ ] Build a 20-paper fixture set covering theory, systems, agents, benchmarks,
  missing TeX, damaged PDF equations, and papers with no central formula.
- [ ] Measure candidate retrieval separately from explanation quality.
- [ ] Require every displayed formula to match the source exactly.
- [ ] Require every page link and excerpt to pass local grounding.
- [ ] Require every numeric example to match the deterministic evaluator.
- [ ] Run five paid K2.6 canaries before enabling the default.
- [ ] Shadow K2.6 against K3 on the fixture set and record disagreement.

## Cost envelope

Candidate selection should send 2,000 to 6,000 input tokens and produce at most
1,500 output tokens per requested report. Thirty formula reports therefore use
roughly 60,000 to 180,000 selector input tokens and at most 45,000 output
tokens. The pipeline uses Moonshot's token-estimation endpoint before paid
canaries and records actual usage after each call.

Batch processing is reserved for backfills. Moonshot documents BatchJob at 60%
of standard inference price, but adding asynchronous batch state to the normal
single-report path would cost more complexity than it saves.

## Acceptance criteria

- No displayed source formula can be absent from the acquired paper source.
- A paper without a central formula states that plainly.
- A reader can distinguish a paper claim, AI Radar deduction, and illustrative
  input without reading the method page.
- K2.6 cannot change report evidence or final prose.
- K3 fallback is explicit and attributable.
- No formula path exposes a credential, executes TeX, evaluates arbitrary code,
  or loads a remote browser asset.
