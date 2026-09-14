# Writing research for solo builders

The opening should help a reader recognize a product problem and decide whether
the paper deserves a small test. Keep the mechanism, comparator, and limitations
available without requiring the reader to decode benchmark names first.

## Write a selected full-paper review

1. Read the versioned PDF's methods, result tables, limitations, and accounting.
   Record its hash and the saved report hash. A benchmark table is only ready
   to explain when its metric, denominator, comparator, conditions, and source
   page are known. Check conflicting prose against the table and retain any
   unresolved conflict.
2. Open with a recognizable problem in two or three short sentences. Explain
   what changes in the system. Expand necessary terms where they first appear.
   Keep the paper title and technical evidence intact below the opening.
3. Select comparisons that change an implementation decision. Include the
   strongest relevant existing baseline, not only a no-feature control. State
   what each benchmark tests and why that matters to the proposed workload.
   Show an unfavorable slice when an average hides it.
4. Add a concrete product example, explicitly as a Paperraft proposal. State
   the integration change, prerequisites, current baseline, held-out inputs,
   measurements, stopping rule, and rollback. Choose pilot sizes as suggestions,
   never as proven minimums. Keep artifact discovery before paid compute.
5. Save the review in `content/builders/<arxiv-id>.json` using `BuilderReview`
   from `src/radar/builder_guides.py`. Check the preview and downloadable plan.
   Every displayed number must agree with an independently recorded source
   table cell. Every practical step must test the proposed mechanism.

The checked-in reviews are editorial readings of the three saved full reports,
not outputs of a new model run. The extraction prompts and report schema have
not changed. `report_digest()` pins the review to the exact saved report; a newer
report or PDF makes the publisher omit that review until it is checked again.
This avoids attaching an old interpretation to changed evidence.

## Explain gains without changing their meaning

| Quantity | Explain it as | Preserve |
| --- | --- | --- |
| Pass rate | Share of tasks that meet the stated correctness test | Task set, grader, percentage-point difference, uncertainty |
| Throughput | Output produced per second at a stated load | Runtime, hardware, concurrency; separate latency |
| Accepted draft length | Tokens accepted in a verification step | It is a diagnostic, not throughput or answer quality |
| Cost | Spending for a named unit of work | Included stages, excluded stages, failures, setup, utilization |
| Recall | Share of actual positives detected | Positive-class denominator and false-positive rate separately |
| Composite reward | The specified scoring rule | Its components, aggregation, and penalties; never call it accuracy |

`BenchmarkReading` calculates differences only between two values recorded in
the same unit and context. Percentages produce percentage-point differences.
Other metrics retain their absolute and relative changes. An absent baseline
stays absent; a zero baseline has no defined relative change. These operations
check arithmetic, not whether a comparison is scientifically justified.

For a SaaS cost decision, count all work needed to deliver successful outcomes.
A task-agent bill excludes the maintenance bill unless the paper explicitly
includes it. Faster token generation does not lower a fixed rental bill by itself.
Treat break-even estimates as conditional on measured per-request savings and
stated traffic. A result on one model does not establish compatibility with another.

## Coverage and limits

Every new paper receives a deterministic application plan selected by research
area. These plans identify possible workloads and useful measurements. They
remain labeled as area guidance and do not add source-linked claims, hardware
eligibility, or a tested status. A full-paper review replaces that plan with a
specific proposal after source review. Publication and downloads require no
additional model calls.

The reviewed opening is used on the permanent paper page. Original extracted
briefs, deep reports, rankings, and classifications remain available. The
downloadable `TRY-IT.md` includes the plan, benchmark readings when available,
and a blank result sheet. It is a planning document, not an executable experiment
or a new measurement schema. For execution, use the existing runner and contract
in [engineering-validation.md](engineering-validation.md).

## Review the change

`eval/builder-readings.json` records table cells independently of rendered copy.
Tests compare them with the editorial records, including the memory baseline
switch, the throughput regression, and the unmatched recall figure. Other tests
cover missing and zero baselines, invalid numbers, changed provenance, and
paper identity. This checks the new presentation against fixed evidence. It
does not establish that a language-model extractor improved or that readers
understand articles better. That requires a separate reader study.

Before: the opening carried a dense technical abstract; numbers were embedded
in claim strings, with no explained difference or product trial sheet.
After: selected pages lead with the product problem, keep baselines explicit,
calculate differences from table values, and separate interpretation from a
proposed test. The original evidence state is unchanged.
