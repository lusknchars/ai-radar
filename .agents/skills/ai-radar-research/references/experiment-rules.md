# Experiment rules

Read for experiment design, execution, or interpretation. The runner's actual
schema and decision logic live in `src/radar/validation.py`; the operational
guide is `docs/engineering-validation.md`. This reference covers judgments a
schema cannot establish.

## Qualify the comparison

Identify the question before selecting a benchmark. Model quality, endpoint
performance, retrieval quality, and agent task completion need different
measurements. An agent harness runs the model/tool loop; an evaluation harness
supplies tasks, observes outcomes, and grades them. Pin both when comparing
agent systems.

Choose a credible baseline and isolate the proposed change. For a comparison
of complete products, list unavoidable differences and limit causal attribution.
Confirm the exact model, draft/extractor/embedder, runtime, kernels, and hardware
combination. Label untested compatibility as an estimate.

Freeze dataset IDs, versions, graders, and success criteria before looking at
candidate results. Use held-out data for confirmation after tuning. Match
context token budgets as well as sampling settings; top-k alone does not match
input size. Preserve all planned cases, including failures and timeouts.

Record the metric name, unit, denominator, aggregation, and grader. A rubric
average, pass rate, token F1, and retrieval recall answer different questions.
Missing telemetry stays unknown; a default zero or one is not a measurement.
Keep model-based judgments inspectable and calibrate them against independent
human or deterministic checks appropriate to the claim.

## Execute and account

Use current plan validation and appropriate local checks before a paid run.
Keep the execution and financial limits distinct: a process timeout does not
stop cloud billing. For a rental, concretize the selected offer, expected total
cost, deadline, export location, and provider teardown procedure. Respect
existing authorization; ask only for a missing decision needed for execution.

Keep raw outputs, source/configuration hashes, model/tokenizer revisions,
runtime image, GPU/CPU/RAM, resource limits, and cache state. Alternate or
randomize run order where needed to limit drift. Use isolated environments for
agent tasks and distinct run identities when caches might reuse old results.
At deterministic decoding, changing seeds does not create independent quality
samples.

Measure end-to-end task success and latency alongside token throughput. Include
failed attempts, startup, idle time, and storage/transfer in total experiment
cost. Separate steady-state estimates and evaluation-only judge costs. Compute
cost per correct task only when there are successful tasks. A fixed rental bill
does not shrink automatically when input token count falls.

An inconclusive or negative comparison is a valid outcome. Retain it and its
configuration. A changed threshold or tuned prompt requires a new declared
experiment and fresh held-out confirmation before a broader claim.

## Memory experiments

Use complete selected histories, ordered timestamps, and separate stores by
system, user, and run. Keep gold answers and annotation-derived summaries out
of ingestion. Freeze memory during benchmark QA unless the declared task tests
online updates. Wait for asynchronous writes to become searchable.

Separate extraction, embedding, retrieval, answering, and judging models and
costs. Compare simple raw-history retrieval against the candidate. Use gold
evidence only as an oracle diagnostic; it does not validate retrieval. Record
retrieved sources so a failed answer can be traced to extraction, retrieval,
generation, or grading.

Include updates, contradictions, abstention, cross-user separation, and deletion
when relevant to the application. An assistant's statement that it performed an
action is distinct from a verified tool outcome. Amortize memory creation over
declared query counts and report cold-start cost separately.

## Limit the conclusion

A mechanism check supports that mechanism in its checked cases. A synthetic
GPU trial supports its frozen configuration. Representative workload results
support that workload within measured uncertainty. Public adoption claims need
the applicable project review and product evidence.

Report the runner's actual decision without treating it as scientific
certification. Read current code before describing enforcement: declarations
of compatibility, hardware, or workload representativeness are not attestations.
