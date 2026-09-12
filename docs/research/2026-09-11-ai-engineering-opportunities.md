# AI engineering opportunities for AI Radar

Research date: 2026-09-11. Primary-source review and proposed experiment queue.
This note contains no new GPU measurements. Priorities are our synthesis of
the sources, not a survey establishing industry consensus.

Follow-up: the [memory-layer investigation](2026-09-11-memory-layers.md) audits
Mem0's published artifacts, compares LoCoMo/LongMemEval/BEAM, and proposes a
separate GLM memory experiment with ingestion and retrieval cost accounting.

## Decision

Build the research-to-experiment workflow around **cost per correct task at a
specified latency and load**. Keep GLM-4.7-Flash with native MTP as the first
experiment. Add prefix-cache and precision comparisons after that experiment
can reliably produce raw answers, failures, timing, and reproducible settings.

The useful deliverable for a developer is a tested recipe with limits: exact
model, method, hardware, workload, cost, observed gain, and cases where it failed.
Finding a paper early is a discovery advantage. Establishing that its method
works on an affordable configuration is a separate engineering contribution.

## What current work is trying to improve

| Engineering objective | Methods worth tracking | Business-facing test |
|---|---|---|
| Shorter generation time | Native MTP, EAGLE-3, diffusion draft models, dynamic speculative length | Complete-response latency and streaming speed, with unchanged task quality |
| Lower memory and deployment cost | Weight quantization and quantized KV caches | Cheapest compatible GPU that meets quality and latency requirements |
| Less repeated computation | Prefix caching and KV-cache reuse | Cold/warm time to first token across realistic prefix hit rates |
| More useful work per GPU | Batching, scheduling, runtime improvements | Correct requests per second within latency limits at several loads |
| Lower spending across a product | Routing between small and large models | Total cost per successful task, including routing and fallback calls |
| Reliable structured workflows | Constrained output, tool validation, context management | Correct fields and final application state, retries, failures, and cost |

These directions have concrete implementations. SGLang describes cache reuse,
structured generation, batching, and serving optimizations. RouteLLM studies
model routing against a cost-quality tradeoff. vLLM documents constrained
outputs. Schema validity alone does not establish correct field values; our
recommended grader must check both.
[SGLang paper](https://arxiv.org/abs/2312.07104),
[RouteLLM paper](https://arxiv.org/abs/2406.18665),
[vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/).

Recent developments deserve their own watch queue:

- **DFlash, February 2026:** proposes parallel drafting with a lightweight block
  diffusion model. The authors provide code and report acceleration on their
  tested models. This is a candidate for a compatible target/draft pair, not
  evidence that the same gain transfers to GLM-4.7-Flash.
  [Paper](https://arxiv.org/abs/2602.06036),
  [author implementation](https://github.com/z-lab/dflash).
- **Hardware-aware dynamic speculation, July 2026:** Cohere adjusts speculative
  length to hardware and batch conditions. Its reported dense-model gain at
  high batch size is larger against fixed speculation than against ordinary
  generation. That makes the comparator essential. Its MoE results also show
  that increasing draft length need not improve speed. Evaluate ordinary,
  fixed, and dynamic decoding separately.
  [Cohere engineering report](https://cohere.com/blog/hardware-aware-dynamic-speculative-decoding).
- **Active Context Compression, January 2026:** studies retaining selected
  knowledge while pruning agent interaction history. A local adaptation would
  need tests for facts lost during compression and their effect on later
  actions. This belongs after we have a multi-step agent workload.
  [Paper](https://arxiv.org/abs/2601.07190).

Older methods remain useful controls. AWQ studies low-bit weight compression;
EAGLE-3 studies learned speculative drafting. Novelty should determine what we
monitor, while compatibility and testability determine what we run first.
[AWQ](https://arxiv.org/abs/2306.00978),
[EAGLE-3](https://arxiv.org/abs/2503.01840).

## First experiment queue

These are proposed priorities, not measured rankings. Change one factor per
comparison. Do not combine all optimizations before measuring their effects.

| Order | Candidate and comparator | Minimum useful experiment | Current readiness |
|---|---|---|---|
| 1 | GLM-4.7-Flash ordinary generation vs native MTP | Existing 40-case, three-pair synthetic test on one H200 | Prepared locally; GPU startup and execution still untested |
| 2 | Prefix caching off vs on | Same checkpoint; repeated document/system prefix plus unique-prefix control; cold and warm runs | Requires a new serving workload and streaming measurements |
| 3 | BF16 vs one supported quantized checkpoint | Same tasks and load; quality, memory, latency, then compare viable rental configurations | Requires exact checkpoint, kernel, and GPU compatibility review |
| 4 | Always use the larger model vs route/fallback | Frozen labeled SaaS cases; separate calibration and held-out test sets | Requires a second model and accounting for every call |
| 5 | Fixed vs dynamic speculation or compatible DFlash draft | Ordinary generation control; several loads and output lengths | Conditional on compatible draft/runtime; not yet qualified for GLM |
| 6 | Existing agent workflow vs context/tool changes | Small isolated tasks with verifiable application outcomes | Later agent track |

The GLM trial is a transfer test of a paper-inspired mechanism. It does not
reproduce the original speculative-decoding paper's model and environment.
See the [prepared trial](../../experiments/glm47-mtp/README.md).

Prefix caching reuses computation for shared token prefixes. Its direct benefit
is on prompt processing; it should not be advertised as a universal improvement
in generation speed. A repeated-prefix benchmark alone will overstate its value
for traffic with little reuse.
[vLLM prefix caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/).

Quantization support depends on method, hardware, model architecture, and
kernel. vLLM's compatibility table distinguishes Ampere and Hopper support,
including FP8 differences. A smaller checkpoint is not sufficient proof of
faster execution. For the first precision comparison, use the same GPU to
isolate the method; then separately test the cheaper deployment configuration.
[vLLM quantization support](https://docs.vllm.ai/en/latest/features/quantization/).

## Test tools and measurement contract

Use the existing AI Radar runner to record experiment provenance and decisions.
Use a serving benchmark for HTTP/streaming performance, a model-evaluation tool
for quality regression, and a task evaluator for business outcomes. These
measure different things. The [harness research note](ai-engineering-harnesses.md)
compares Inspect AI, lm-evaluation-harness, Harbor/Terminal-Bench, and SWE-bench.

For serving, start with `vllm bench serve`. Its CLI exposes workload/load
controls, latency metrics, goodput constraints, and saved results. Check the
actual pinned version's help before constructing an adapter; the linked latest
documentation moves independently of our vLLM 0.29.0 trial image.
[vLLM serving benchmark](https://docs.vllm.ai/en/latest/cli/bench/serve/).

MLPerf Endpoints provides a useful comparison model: throughput, per-user
interactivity, p95 time to first token, and concurrency describe the same
operating point. Its July 2026 v0.7 announcement also separates the current
release from future planned agentic coverage. Adopting these measurement ideas
does not make our experiments MLPerf-certified submissions.
[Endpoints methodology](https://mlcommons.org/benchmarks/endpoints/),
[v0.7 release](https://mlcommons.org/2026/07/mlperf-endpoints-v0-7-release/).

Recommended scorecard:

- Correctness and failure rate by task category, including malformed and
  truncated responses. Prefer deterministic checks where the task permits.
- p50/p95 complete-response latency, streaming TTFT and inter-token latency,
  output lengths, and offered load. Count failed and timed-out requests.
- Goodput defined explicitly as correct requests completed within the chosen
  latency limit per elapsed second. Do not confuse this with other projects'
  definitions of goodput.
- Full experiment bill divided by correct tasks, including failed attempts,
  startup, warmup, idle rental time, storage, and transfer. Also report the
  steady-state serving estimate separately. Zero correct tasks means no usable
  cost-per-success value.
- Model/tokenizer revisions, runtime image digest, precision, prompt template,
  seeds, GPU/CPU/RAM, dataset hash, cache state, and raw outputs.

Proposed progression: synthetic smoke test, representative held-out workload,
load sweep, small developer pilot, then a public recommendation limited to the
tested conditions. Start the load sweep at concurrency 1, 4, 8, and 16 only if
memory permits. Use enough representative cases to estimate uncertainty for the
effect being claimed. Forty synthetic cases cannot establish general quality.

The current runner has deterministic thresholds and repeated comparisons. It
does not yet implement confidence intervals, endpoint load generation, peak
memory profiling, or provider billing reconciliation. Those are requirements
for stronger claims, not capabilities already delivered by this research.
See [validation workflow](../engineering-validation.md) and
[GPU adapter](../../src/radar/glm47_trial.py).

## What AI Radar should collect

Prefer provider APIs and repository files when available. Collect evidence and
metadata first; download large weights only for candidates that pass triage.

| Source | Collect | Purpose |
|---|---|---|
| arXiv API, linked full text | Paper ID plus version, dates, claims, benchmark conditions, code links | Identify method and inspect its evidence |
| Author GitHub repositories | Release/tag, commit SHA, installation instructions, tests, model support and known limitations | Determine whether a method is executable |
| Runtime repositories | Releases and merged changes in vLLM/SGLang; support examples | Detect when a previously blocked paper becomes practical |
| Hugging Face Hub | Model/dataset cards, revision SHA, architecture, files, evaluation metadata, license fields | Resolve exact artifacts and resource requirements |
| Official benchmark repositories | Task definitions, graders, dataset revisions, run rules | Reuse test methods and identify evaluation changes |
| OpenAlex | Citation and related-work metadata | Enrich discovery; not proof of reproducibility |

arXiv documents structured Atom responses and versioned article access. GitHub
provides release endpoints. Hugging Face provides model/dataset APIs and
webhooks, subject to its rate limits. OpenAlex documents authentication and
current API access requirements. Store retrieval timestamps and handle
unavailable sources explicitly.
[arXiv API](https://info.arxiv.org/help/api/user-manual.html),
[GitHub releases API](https://docs.github.com/en/rest/releases/releases),
[Hub API](https://huggingface.co/docs/hub/en/api),
[OpenAlex authentication](https://help.openalex.org/api/authentication/).

Suggested watchlist: `vllm-project/vllm`, `sgl-project/sglang`,
`SafeAILab/EAGLE`, `z-lab/dflash`, and `lm-sys/RouteLLM`, plus the authors' linked
model repositories. A source on this list is a discovery input, not an
endorsement of all its claims. Keep paper, code, model, and dataset license
metadata distinct when preparing reusable experiment bundles.

Code inspection found two concrete collection gaps. The existing
[arXiv parser](../../src/radar/arxiv.py) normalizes away the paper version and
keeps the publication date. Experiment evidence needs the selected version and
update timestamp preserved separately. The [GitHub adapter](../../src/radar/github.py)
searches for paper IDs in README files; it does not watch runtime releases or
prove that an implementation runs. Both findings suggest focused follow-up
work, not an automatic widening of the current live collector.

For each candidate record: source links and versions; exact claimed result and
comparator; target architectures; required weights/kernels; hardware estimate;
workload fit; expected implementation effort; falsifiable success condition;
and current evidence state. An LLM may extract a draft record, but every
quantified claim needs a source location and every experiment needs a grader.

## Triage and public claims

Advance a candidate only when we can answer all five questions:

1. What measurable business problem does this method address?
2. Which source supports the mechanism and the specific claimed result?
3. Is there a runnable implementation compatible with our exact model and GPU?
4. Can we define a fair baseline, held-out cases, and an objective failure rule?
5. Can the first informative test fit a bounded rental and engineering budget?

A missing implementation or incompatible draft is a recorded blocker. A method
that produces no improvement is a useful result. Retain negative results and
failed runs so selection does not hide the cost of finding a winner.

Keep source review, mechanism checks, synthetic GPU measurements,
representative-workload measurements, and developer-pilot feedback distinct.
They justify different claims. Public artifacts should include a short result
card and reproducible configuration, not just a percentage extracted from a
paper. Existing public research-page review and reader-study gates also remain
separate from experimental success.

This research adds a prioritized backlog and source map. It does not activate
collectors, change public rankings, rent GPUs, or establish measured gains.
