# Evidence pipeline rollout

## Decision

AI Radar will improve source fidelity before adding another LLM or agent
framework. Deep reports use a PDF extraction seam with two adapters:

```text
official arXiv PDF bytes
          |
          v
   Docling when enabled ---- failure ----+
          |                              |
          v                              v
 structured page text                 pypdf
          |                              |
          +--------------+---------------+
                         v
              page-grounded K3 report
                         |
                         v
       PDF hash + text hash + parser provenance
```

`pypdf` stays the default for daily development and the small report path.
Docling runs only for requested deep reports. Exact formulas still come from
official arXiv TeX, not from either PDF parser or an LLM.

## Cost and operating limits

- The daily 20 to 30 paper briefs do not invoke Docling.
- One reader action invokes one Docling conversion and the existing K2.6 and
  K3 calls.
- Docling adds local compute and model-download time, but no metered parser
  call. GitHub Actions installs it only when `RADAR_PDF_EXTRACTOR=docling`.
- The optional dependency is pinned to Docling 2.124.0. Upgrade it only after
  running the comparison set against the proposed release.
- A Docling failure falls back to pypdf. The report records the parser and the
  exception class, so fallback cannot look like a successful deep parse.
- PDF downloads remain capped at 30 MB and 200 pages. Extracted report context
  remains capped at 240,000 characters.

## Evaluation gate

Build a 50-paper fixture set before making Docling the default. Include
multi-column papers, table-heavy evaluations, equation-heavy methods, scanned
pages, missing TeX archives, and malformed PDFs.

The promotion gate is:

| Metric | Required result |
|---|---:|
| verified evidence excerpts found on the cited PDF page | at least 98% |
| exact formulas copied from official TeX | 100% |
| reports with a recorded PDF hash, text hash, parser, and page count | 100% |
| Docling conversion success on the fixture set | at least 95% |
| p95 extraction time for one report in GitHub Actions | at most 120 seconds |
| ungrounded evidence claims published with a page link | 0 |

Run both adapters on the same fixtures and compare their outputs without
changing ranking or publication. Parser quality and K3 report quality must be
scored separately.

The comparison command runs without network or LLM calls. Each manifest item
declares the expected page count and short excerpts that must remain on their
physical PDF pages:

```json
[
  {
    "arxiv_id": "2608.11111",
    "expected_pages": 12,
    "required_excerpts": [
      {"page": 7, "text": "Latency fell by 37 percent."}
    ]
  }
]
```

Keep the corresponding file at `eval/pdfs/2608.11111.pdf`, then run:

```bash
pip install -e ".[documents]"
python scripts/evaluate_pdf_extractors.py \
  --manifest eval/extraction-manifest.json \
  --pdf-dir eval/pdfs \
  --output eval/results/parser-comparison.json
```

The command reports page-count accuracy, exact-page excerpt recall, non-empty
pages, failures, and p95 duration for each adapter. Local PDFs and generated
results are ignored by Git because the evaluation corpus still needs a source
and licensing policy.

## Next integrations

1. Migrate the committed database and prove the scheduled workflow on `main`.
2. Build the 50-paper extraction fixture set and comparison command.
3. Add keyed Semantic Scholar discovery as a shadow source. It must not affect
   ranking until relevant-paper recall improves without lowering precision.
4. Expand GitHub evidence from README matches to DOI and arXiv ID matches in
   source, notebooks, and documentation.
5. Add OpenReview reviews and decisions as separately labeled evidence.
6. Add Inspect AI for repeatable model and prompt comparisons. Add Langfuse
   only after the evaluation scores have stable names and definitions.

## Risks

- Docling makes installation and cold starts heavier. Keeping it optional and
  report-only protects the daily pipeline.
- Parser output may change between Docling releases. The exact dependency pin,
  PDF hash, text hash, and report schema make those changes observable.
- A fallback can reduce table and layout fidelity. The published provenance
  states when it happened.
- Paper text is untrusted input. The report model receives it inside explicit
  delimiters, cannot run tools, and is instructed to ignore embedded
  instructions.
