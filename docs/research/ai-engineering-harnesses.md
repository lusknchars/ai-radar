# Evaluation tools for AI Radar experiments

Research date: 2026-09-11. Scope: primary documentation and engineering reports for model quality, SaaS workflows, and coding agents. Recommendations below are experiment design proposals, not measurements of GLM-4.7-Flash. No benchmark or paid model run was performed for this note.

AI Radar should select an evaluation tool according to the claim being tested. A model answering questions, an API completing a business workflow, and an agent repairing a repository need different evidence. Keep the existing GLM-4.7-Flash MTP smoke trial as the first controlled experiment; add broader tools when the question requires them.

## What engineers are trying to improve

Anthropic's agent evaluation guidance emphasizes successful outcomes, reliability over repeated attempts, and regression detection. It distinguishes the **agent harness**, which manages model execution and tools, from the **evaluation harness**, which supplies tasks, captures traces, scores outcomes, and summarizes results. A booking confirmation in a transcript is insufficient evidence; the reservation must exist in the final environment. These are useful priorities for AI Radar's business experiments, but they are one engineering organization's guidance rather than a survey of the whole industry. [Anthropic, January 2026](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

A separate controlled study from Anthropic found that infrastructure configuration moved Terminal-Bench 2.0 scores by six percentage points between its most and least resourced setups. CPU, RAM, timeouts, and resource enforcement therefore belong in a coding-agent experiment's recorded configuration. Report this as the authors' measurement; AI Radar has not reproduced it. [Anthropic infrastructure study, February 2026](https://www.anthropic.com/engineering/infrastructure-noise)

## Tools worth adopting

| Tool | What it provides | First useful AI Radar use | Main limitation |
| --- | --- | --- | --- |
| Inspect AI | Reusable datasets, model/agent execution, scorers, logs, and sandbox integrations | A private suite of extraction, classification, and tool-call workflows | A framework does not supply the product's definition of correctness |
| EleutherAI lm-evaluation-harness | Standardized model evaluation tasks and configurable model backends | Quality regression checks after changing precision or inference settings | Benchmark quality scores do not establish latency or business value |
| Harbor with Terminal-Bench | Containerized tasks with executable verification for terminal agents | Selected coding or environment tasks after a working agent exists | Environment resources and agent settings affect results; running a full suite adds substantial work |
| SWE-bench | Repository issue repair evaluated by applying patches and running tests | A later test of coding-agent improvements | It measures issue repair, not general SaaS workflow success |

The table's recommendations and limitations are our interpretation. Verified tool capabilities and operational details follow.

### Inspect AI for business tasks

Inspect provides composable datasets, agents, tools, and scorers, plus a log viewer. It supports custom tools and external agents, so the same business task can be evaluated under different execution approaches. [Inspect overview](https://inspect.aisi.org.uk/)

Scorers can inspect output or a sandbox and can combine deterministic checks with model grading. Its scoring documentation separates execution failures from scores, which matters when reporting whether a workflow failed because of the model or its environment. [Inspect scoring](https://inspect.aisi.org.uk/scoring.html)

Sample execution supports message, token, time, and cost limits. Those make bounded pilot evaluations practical; they do not by themselves enforce a Vast.ai rental budget. [Inspect task options](https://inspect.aisi.org.uk/tasks.html)

Docker sandbox support is built in. The documentation makes a useful distinction: evaluation Python code still runs in the main process; only operations explicitly dispatched through the sandbox interface run inside it. [Inspect sandboxing](https://inspect.aisi.org.uk/sandboxing.html)

Proposed first extension: replay frozen synthetic support or catalog requests against GLM, score typed JSON and resulting database state, and record each retry. Introduce human-calibrated model grading only for outputs whose correctness cannot be expressed reliably in code.

### lm-evaluation-harness for model quality regressions

The official CLI supports Hugging Face and vLLM backends, task validation, sample logs, explicit seeds, chat templates, and selected sample indices. Its `--limit` option is explicitly described as testing-only. It also documents reasoning-output handling and warns that thinking mode is incompatible with log-likelihood tasks. [Official interface documentation](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/interface.md)

Proposed use: pin a small instruction-following or reasoning suite, preserve prompt formatting and generation settings, and compare the unchanged baseline with the candidate. Run a restricted subset to debug the adapter, then the declared evaluation split before publishing a benchmark claim. Keep serving measurements in a separate controlled load test. A quality harness result alone cannot establish faster inference.

### Harbor and Terminal-Bench for agent behavior

Harbor defines a task as an instruction, container environment, and test script. A dataset collects those tasks; an agent is a program that completes them. This separation allows the same task to be tried with different agent implementations. [Harbor core concepts](https://www.harborframework.com/docs/core-concepts)

Terminal-Bench 2.0's paper describes 89 difficult terminal tasks inspired by real workflows. This is a broader and more demanding target than the current structured-output smoke test. [Terminal-Bench 2.0 paper](https://arxiv.org/abs/2601.11868)

Harbor's current documentation includes a registered Terminal-Bench 2 command and explains that it downloads the task artifacts. Pin the dataset version and task artifacts when preparing an actual experiment; a moving registry name is insufficient provenance. [Harbor evaluation documentation](https://www.harborframework.com/docs/run-jobs/run-evals)

Proposed use: begin with a few explicitly selected, CPU-only tasks that can be checked by tests. Compare one model under two agent configurations, such as different tool descriptions or context management. Keep the rest of the execution environment fixed. Label the result as a named subset experiment, never as a full Terminal-Bench score.

### SWE-bench for repository repair

SWE-bench supplies GitHub issues and repositories for patch generation. Its Verified subset contains 500 engineer-confirmed solvable problems, and its evaluation uses Docker. [SWE-bench overview](https://www.swebench.com/SWE-bench/)

The evaluation harness applies a proposed patch and runs repository tests. It accepts specific instance IDs and worker limits, so a small pilot does not require a full benchmark. The guide warns that results are cached by run ID and instance ID; a changed patch requires a new run ID. Its outputs distinguish resolved, unresolved, incomplete, and error cases and retain per-instance logs. [SWE-bench evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/)

Proposed use: postpone until AI Radar can execute and trace a coding agent. For a first pilot, choose a few issues before observing candidate results and report all of them, including environment failures. Reusing a convenient solved subset would overstate the value of an agent change.

## Proposed sequence before broader release

1. Complete the existing GLM-4.7-Flash baseline versus MTP trial. It answers whether the execution and grading system can detect a useful change on its declared smoke workload.
2. Add representative SaaS tasks with explicit acceptance rules. Use the same task IDs for baseline and candidate and count retries in both latency and cost.
3. Use lm-evaluation-harness when a change could affect general model quality, especially quantization or checkpoint changes. Preserve the original smoke suite for fast regressions.
4. Add Inspect when custom workflows need richer tools, state verification, or transcript review. Add Harbor or SWE-bench only for claims about coding agents.
5. Reserve an untouched workload split before tuning. Publish task provenance, actual configuration, uncertainty, failed cases, and measured costs alongside gains. Separate a transferred technique from a reproduction of the original paper.

Our proposed business metric is **total measured execution cost divided by correctly completed tasks under the latency requirement**. Include failed attempts and retries in the numerator. Report the successful-task count and latency distribution separately so the ratio does not hide regressions. For rented hardware, report total rental cost as well as any per-request estimate, including startup, idle time, and experiment overhead.

Before general availability, use a small pilot with representative users and independently inspect failed and borderline outputs. Passing synthetic tests is evidence that the machinery works on those tests; it does not establish usefulness across all businesses.
