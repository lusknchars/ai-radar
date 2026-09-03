# Public research pages

## Outcome

Every indexed paper has a permanent HTML page and a machine-readable JSON
document. The page can mature from abstract-level screening to source mapping
without changing its URL.

```text
paper + latest judgment + signal
              |
              v
        ResearchPage model <----- optional ReportDocument
              |
        +-----+-----+
        v           v
     index.html  index.json
```

The model uses three editorial states: `indexed`, `source_mapped`, and
`independently_tested`. The current pipeline emits the first two. A claim can be
`source_linked` only when it carries a PDF page and excerpt. Risks extracted by
the report remain `inferred` until the report contract can ground them directly.

## Cost

This release makes no new LLM calls. It derives research pages from the latest
stored judgment, signal, and optional report. All pages share one CSS file and
one background script, so archive growth adds only the page markup and JSON per
paper.

## Evaluation gate

Before changing the report prompt to produce structured exposure findings, run
an evaluation set of at least 20 reports across inference and agent papers.

- Source-link precision must remain 100%. Every `source_linked` item needs a PDF
  page and an excerpt accepted by the existing grounding check.
- Editorial false promotion must remain zero. A paper without a deep report
  cannot become `source_mapped`.
- Exposure coverage must remain eight of eight for every page. Missing analysis
  must render as `not_evaluated`, never as an empty card or a safe result.
- Five target readers should decide whether to reject, read, or test a paper in
  half the median time required with the abstract alone, without inventing a
  risk or experimental condition.

The gate is executable:

```text
eval/public-research-corpus.json
             +
site/papers/<arxiv-id>/index.json
             +
eval/reader-study.csv
             |
             v
scripts/evaluate_public_research.py
             |
             +--> Markdown findings
             +--> structured JSON
             +--> exit 0 only when every release condition passes
```

The fixed corpus reuses the 20 Kimi canary judgments already stored in the
repository. It has ten families, all four recommendation states, and three
tracks: inference, agents, and adjacent negative controls. The isolated
evaluation database is rebuilt without network access by
`scripts/prepare_public_research_eval.py`.
The tracked judgments live in `eval/public-research-judgments.jsonl`, separate
from the ignored migration checkpoint. A fresh clone can run
`scripts/verify_public_research_baseline.py`; CI executes the same command on
every push.

The first measured baseline has 20 valid indexed pages, 36 abstract-level
claims, and all 160 exposure slots visible. It correctly fails because no deep
reports or reader-study results exist yet. A missing result is a failed gate,
not a zero that can disappear inside an average.

Batch report generation accepts the manifest and checkpoints through the report
files themselves. Completed JSON files are skipped on rerun. `--limit 1` is the
paid canary before the remaining corpus runs.

## Next increment

Generate and review the first report from the corpus. If its page links survive
grounding, run the remaining 19 and inspect the evaluation failures. Add
structured exposure findings and risk-to-claim references only when those
results show that the current full-text report cannot supply the required
precision. Do not add keyword classification or another model call before that
measurement.
