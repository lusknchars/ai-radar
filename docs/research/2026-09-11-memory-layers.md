# Memory layers: benchmark audit and first experiment

Research date: 2026-09-11. No memory service was installed, no account was
created, and no model or paid benchmark was run. The artifact audit below reads
published JSON and recounts existing judgments; it does not independently
judge the answers.

## Recommendation

Add persistent memory as a candidate within AI Radar's agent track. Start with
simple retrieval and Mem0 OSS on the same frozen conversations and answerer.
Compare a managed service later as a separately identified product. Keep the
prepared GLM-4.7-Flash MTP trial unchanged; memory needs a different workload
and comparison design.

A memory layer stores selected information across conversations, retrieves
relevant records, and puts them into the answering model's input. Mem0 exposes
add and search APIs for this workflow. Its current platform algorithm extracts
facts in an add-only pass, links entities, and combines retrieval signals.
Changes to facts retain temporal context. Asynchronous ingestion returns an
event ID, so an experiment must wait for ingestion completion before retrieval.
[Mem0 platform migration and API behavior](https://docs.mem0.ai/migration/platform-v2-to-v3).

This can reduce repeated input processing, but it adds extraction, embedding,
storage, and retrieval work. It changes what the model sees, so it can also
change correctness. The test should establish whether the complete system
delivers cheaper useful answers for a particular workload.

## What the screenshot means

The screenshot matches Mem0's published managed-platform results. Its main
README explicitly states that the platform includes proprietary optimizations
absent from the open-source SDK. Installing Mem0 OSS does not reproduce that
system. The published setup uses one retrieval call and a top-200 budget.
[Mem0 repository](https://github.com/mem0ai/mem0#new-memory-algorithm-april-2026).

| Label | Screenshot | Interpretation in the benchmark README |
|---|---:|---|
| LongMemEval | 94.4 | 472 of 500 answers marked correct |
| LoCoMo | 92.5 | 1,425 of 1,540 answers marked correct |
| BEAM 1M | 64.1 | Mean rubric score 0.641, scaled to 100 |
| BEAM 10M | 48.6 | Mean rubric score 0.486, scaled to 100 |

The BEAM table separately reports pass rates of 70.1% and 50.5%. These are
different metrics. The vendor evaluator marks a question as passing when its
mean nugget score is at least 0.5. Keep the metric name, scale, threshold,
denominator, and retrieval cutoff attached to every number.
[Pinned benchmark README](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/README.md),
[BEAM evaluator](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/beam/run.py).

### The available artifacts do not match every headline

At benchmark repository revision
`4b61c5d31b9c668a12b4f5e78064248a02c82d2b`, we fetched the four top-200 result
files, retained their SHA-256 hashes, and recounted per-question judgments.

| Published result file | Recount | Relationship to screenshot |
|---|---|---|
| `longmemeval_results.json` | 467 / 500, 93.4% | Does not establish 94.4 |
| `locomo_results.json` | 1,410 / 1,540, 91.558% | Does not establish 92.5 |
| `beam_1m_results.json` | 491 / 700 pass; reported mean 0.6408656 | Mean rounds to 64.1 on the screenshot scale |
| `beam_10m_results.json` | 101 / 200 pass; reported mean 0.4860235 | Mean rounds to 48.6 on the screenshot scale |

The first two files are timestamped April 6, 2026; the BEAM files are dated
March 26 and March 31. The discrepancy could reflect different runs or stale
artifacts. It is an unresolved evidence link, not proof that the headline is
false. The inspected LongMemEval file contains zero-valued latency fields;
those cannot substantiate a latency claim.
[LongMemEval artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/longmemeval_results.json),
[LoCoMo artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/locomo_results.json),
[BEAM 1M artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/beam_1m_results.json),
[BEAM 10M artifact](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/results/platform/beam_10m_results.json).

The result metadata identifies GPT-5 answering/judging roles. These are not
measurements of GLM-4.7-Flash. See the machine-readable
[artifact audit](2026-09-11-mem0-artifact-audit.json) for selected metadata,
source URLs, checksums, and recounted totals.

The vendor LoCoMo runner defaults to categories 1 through 4 and excludes
category 5. We must preserve that denominator and explicitly test abstention
elsewhere. A named benchmark does not guarantee the same dataset selection or
grader as its original paper.
[Pinned LoCoMo runner](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/locomo/run.py).

## Benchmark selection

The [original benchmark review](2026-09-11-memory-benchmarks.md) records dataset
sizes, scoring, and limitations. Proposed progression:

1. Two complete LoCoMo histories with 40 questions selected before seeing
   results. This checks the ingestion/retrieval/evaluation machinery. Label it
   a subset trial, not a LoCoMo leaderboard score.
2. A frozen LongMemEval-S subset for knowledge updates, temporal reasoning,
   cross-session questions, and abstention. Ingest each selected history fully.
3. BEAM at a smaller history scale, then 1M if earlier results justify the work.
   Postpone 10M until ingestion cost and reliability are understood.

The 1M and 10M labels describe history scale. They do not require inserting the
whole history into a single model request. Memory can ingest chunks and answer
from retrieval, while full-context baselines may be infeasible.

## Candidate systems

| Candidate | Why test it | Comparison boundary |
|---|---|---|
| Rolling recent history | Cheap baseline available to most developers | Cannot recover facts outside its window |
| Chunk retrieval using BM25 or embeddings | Measures whether simple retrieval is sufficient | Same text/token budget as memory candidate |
| Mem0 OSS | Inspectable fact extraction and memory retrieval | Pin extractor, embedder, code, and store configuration |
| Mem0 Platform | Direct candidate for a managed memory API | Record service version/date and total charges; distinguish it from OSS |
| Graphiti, then optionally Zep | Temporal relationships and facts that change | OSS framework and managed Zep are different systems |
| Letta | Agent-controlled persistent memory and context selection | Changes the agent runtime as well as memory, so evaluate separately |

Graphiti offers temporal graphs and hybrid retrieval; Zep operates a managed
system with additional proprietary components. Letta's current Agent SDK uses
persistent memory repositories, with system memory in context and other files
read on demand. These are architectural candidates, not an established ranking.
[Graphiti versus Zep](https://help.getzep.com/zep-vs-graphiti),
[Letta Agent SDK memory](https://docs.letta.com/agent-sdk/memory).

## GLM experiment design

Hold GLM-4.7-Flash, generation settings, and the answer prompt fixed. Disable MTP
for this comparison to isolate memory. Give retrieval-based arms the same
context token ceiling; a fixed number of retrieved records is insufficient
because record lengths vary. Include a full-history arm only where it fits,
and report coverage. Never silently truncate it and label it full context.

The existing MTP experiment has a 4,096-token limit. It cannot simply be reused
for full LoCoMo or LongMemEval histories. Qualify a new context allocation on the
chosen GPU, or keep a short generation context and compare retrieval methods.
The same H200 can serve the answering model; memory storage and orchestration
can run on CPU. Extraction and embedding compute still need explicit provision.
Hardware feasibility remains unmeasured.

The vendor benchmark client supports a custom OpenAI-compatible base URL, which
is a potential connection to a vLLM-hosted GLM. Verify the selected runners wire
through all relevant settings before execution. Separate extractor, embedder,
answerer, and judge configuration; replacing only the answerer does not make the
whole pipeline local.
[Benchmark LLM client](https://github.com/mem0ai/memory-benchmarks/blob/4b61c5d31b9c668a12b4f5e78064248a02c82d2b/benchmarks/common/llm_client.py).

Proposed controlled procedure:

- Use separate stores per system, run, and user. Ingest historical messages in
  order, preserving timestamps, speaker roles, and evidence IDs.
- Keep questions and gold answers outside memory ingestion. Freeze the memory
  snapshot before evaluation; generated test answers must not help later tests.
- Wait for writes to finish and retain failed ingestion records. Measure time
  from accepted write to searchable memory, not only API acknowledgement.
- Record retrieved evidence and the final answer separately. Use gold-evidence
  answering as a diagnostic arm for retrieval failures, not a deployable method.
- Use deterministic graders for synthetic structured cases. For benchmark QA,
  pin the official grader and add blinded human checks of a sample, including
  contradictions and false abstentions. Do not treat the answerer's self-score
  as independent verification.
- Add business cases for a changed customer preference, an outdated address,
  conflicting records, an unknown fact, cross-user separation, deletion, and an
  assistant claiming an action that the application did not complete. Store
  verified tool outcomes distinctly from assistant assertions.

## Measure whether memory pays for itself

Report both total evaluation spending and expected production cost. Judge calls
are evaluation overhead unless the product itself uses a judge. Amortize a
history's ingestion cost across its actual number of queries, not an assumed
large number chosen to make the result look favorable.

For fixed history and comparable correctness, a useful planning equation is:

```text
memory_cost(Q) = ingestion + storage_period + Q * query_cost_with_memory
baseline_cost(Q) = Q * query_cost_without_memory
break_even_Q = (ingestion + storage_period)
              / (query_cost_without_memory - query_cost_with_memory)
```

The denominator must be positive; otherwise there is no break-even under this
model. Query cost includes retrieval, reranking, generation, and expected
retries. A growing history requires incremental writes and updated storage
costs. Compare against a realistically cached baseline. For GPU rentals, fewer
tokens may improve capacity without reducing the bill for a fixed rental period.

Measure answer quality, stale-fact errors, abstention, retrieved input tokens,
p50/p95 end-to-end latency, ingestion cost, retrieval cost, and cost per correct
answer. Report cold-start ingestion separately from repeated use. Managed
pricing depends on the selected plan and operations, so no dollar savings are
claimed here.

Before wider release, publish a reproducible result card stating the exact
system, benchmark subset, model roles, token budget, cost assumptions, measured
outcomes, and failures. A memory technique earns a recommendation only for the
workloads where its total cost and correctness support one.
