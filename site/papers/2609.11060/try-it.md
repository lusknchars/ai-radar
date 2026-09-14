# Try the idea: Grounding Agent Memory: Environment-Probing Curation for Enterprise Agents

Paperraft interpretation of the full paper. No Paperraft experiment has been run.

Paper: https://arxiv.org/pdf/2609.11060v1

## Possible product use

Possible product use: a SaaS data assistant that repeatedly looks up the same customer tables, then makes mistakes after a schema change.

Add a background memory checker to a sandbox copy of that assistant. Keep customer data and memory isolated. Give the checker only the read access needed to validate a record, and keep the current memory pipeline available as a fallback.

## Baseline

Run three conditions: no memory, your current memory, and the same memory with checking. Keep the answering model, tools, retrieval, and task order fixed.

## First test

1. Prepare 30 representative database questions with verified answers. Change a table name or data convention halfway through the sandbox sequence. Define a spending limit and an acceptable failure rate before testing.
2. Run each condition from a fresh environment and empty memory. Let memory persist within a run, never between conditions. Hide future questions from the checker.
3. Repeat at least three paired runs with matching question orders. Record answering, distillation, checking, and retrieval usage separately. This pilot size is a Paperraft suggestion, not the paper's evaluation protocol.
4. Inspect wrong answers and the memory records that caused them. Save per-task results and check whether new records remain correct after the environment changes.

## Measure

Correct answers, unnecessary database calls, stale records, response latency, and total cost per successful task including failed attempts and all memory maintenance.

## Decision rule

Keep checking only if it improves your chosen quality target at an acceptable total cost. If your goal is savings, the reduction in answering cost must exceed the added checking and maintenance cost. Use paired results to inspect variation; three pilot runs are not proof of a stable production gain.

## Read the benchmark correctly

### CLBench: the headline versus no memory

Pass rate is the share of database questions answered correctly.

No memory: 39%. Memory with probing: 73%. Difference: +34 percentage points.

40 questions with a schema change halfway through; GPT-5.4; five paired runs.

This compares the whole memory system against no memory. It does not isolate the value of probing.

Source: https://arxiv.org/pdf/2609.11060v1#page=5, Table 1a.

### CLBench: the extra value of checking memory

Same pass metric, now against ordinary memory.

Ordinary memory: 70%. Memory with probing: 73%. Difference: +3 percentage points.

Same 40-question experiment. Reported 95% intervals are ±16 and ±5 percentage points.

The intervals overlap. These means alone do not establish a reliable improvement from adding the checking step.

Source: https://arxiv.org/pdf/2609.11060v1#page=5, Table 1a.

### CLBench: whose cost went down?

Task-agent spending for the 40-question run, averaged across runs.

Ordinary memory: $1.99. Memory with probing: $1.68. Difference: -0.31 USD (-15.6%).

Task-response phase only. Distillation and memory curation are excluded.

This is not total operating cost or cost per request. Any extra maintenance cost must be counted before claiming savings.

Source: https://arxiv.org/pdf/2609.11060v1#page=5, Table 1a and caption.

## Record your result

- Model and version:
- Code revision and configuration:
- Task set and split:
- Hardware or API:
- Run count and seed/order:
- Quality and latency limits chosen before testing:
- Baseline outputs and cost:
- Changed outputs and cost:
- Setup and maintenance cost:
- Regressions and uncertainty:
- Decision and rollback:

Compare total cost per successful task, including failed attempts, retries, preparation, and maintenance. A benchmark percentage is not a prediction of savings for your product.
