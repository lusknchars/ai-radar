# Try the idea: Osprey: Target-agnostic Pre-training Makes Stronger Drafters in Speculative Decoding

Paperraft interpretation of the full paper. No Paperraft experiment has been run.

Paper: https://arxiv.org/pdf/2609.09338v1

## Possible product use

Possible product use: a self-hosted writing or coding assistant where output generation is a measured bottleneck.

Begin with an artifact check. Verify a usable drafter for your exact target and serving version. If none exists, record the adaptation work and budget before booking GPUs; a new target is an experiment of its own.

## Baseline

The same target with speculation disabled, your current drafter if present, and the candidate drafter. Keep the GPU, precision, sampling, context, and request trace fixed.

## First test

1. Inspect the official repository linked by the paper for weights, license, target support, and pinned runtime instructions. Confirm whether you can reuse pretraining and what adaptation remains. Do not infer compatibility from model size.
2. Save 50 held-out product prompts with realistic input and output lengths. Include an unusual-domain slice and define quality, response-time, and cost limits before running. This is a proposed pilot size.
3. Once the artifact and budget checks pass, replay the same trace for each condition at low load and your expected concurrency. Repeat paired runs after warm-up, then inspect outputs for regressions.
4. Record both accepted draft length and end-to-end performance. Keep preparation, adaptation, idle GPU time, and serving costs in the result sheet. Preserve a configuration that disables the drafter.

## Measure

First-token and completion latency, tokens per second, completed requests, output correctness, peak memory, and total cost per successful request. Report low-load and concurrent results separately.

## Decision rule

Keep the drafter only if it improves the workload that matters while preserving quality and meeting latency limits. Divide setup cost by measured savings per request to estimate break-even traffic; if savings are zero or negative, there is no cost break-even. A pilot on another model does not validate GLM support.

## Read the benchmark correctly

### Accepted length: a diagnostic, not app speed

Mean draft tokens accepted per verification step.

Reproduced EAGLE-3: 2.45 tokens/step. Osprey: 2.97 tokens/step. Difference: +0.52 tokens/step (+21.2%).

Llama-3.3-70B-Instruct, five domains; SGLang, batch 1.

Longer acceptance can help, but the draft model also takes time to run. Measure throughput separately.

Source: https://arxiv.org/pdf/2609.09338v1#page=7, Table 1.

### Throughput: tokens generated each second

Decoding throughput measures output rate in the tested serving configuration.

Reproduced EAGLE-3: 155.8 tokens/s. Osprey: 183.7 tokens/s. Difference: +27.9 tokens/s (+17.9%).

Same Llama comparison and serving setup.

A throughput increase is not the same percentage reduction in response time or cost. Queueing, prompt processing, and utilization also matter.

Source: https://arxiv.org/pdf/2609.09338v1#page=7, Table 1.

### A regression hidden by the average

MT-Bench is the conversational slice of the MiniMax comparison.

Public EAGLE-3: 214.4 tokens/s. Osprey: 201.6 tokens/s. Difference: -12.8 tokens/s (-6.0%).

MiniMax-M2.5, FP8, batch 1; 64 prompts in this benchmark.

Osprey is slower on this slice despite a higher overall mean. Use your own traffic mix.

Source: https://arxiv.org/pdf/2609.09338v1#page=7, Table 2.

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
