# Try the idea: Shopping by algorithm: How agentic AI deploys human heuristics as a surrogate consumer

Research-area suggestion; paper-specific feasibility is not established. No Paperraft experiment has been run.

Paper: https://arxiv.org/abs/2609.28372

## Possible product use

An agent looks good in demos, but you cannot tell which product tasks it fails.

Use the study's evaluation idea to inspect a small set of tasks with human-checked answers.

## Baseline

Your current evaluator and a manually reviewed reference set.

## First test

1. Locate the paper's implementation and check its license, model support, data needs, and hardware requirements. Stop here if you cannot obtain the required artifacts.
2. Save a small set of representative product tasks and expected outcomes. Keep evaluation tasks out of any training or tuning, and choose quality and cost limits before running.
3. Run the baseline and the proposed change on identical inputs. Keep other settings fixed and repeat paired runs to expose variation.
4. Save per-task outputs, failures, timings, and all usage costs. Review regressions before expanding the test.

## Measure

Agreement with human review, missed failures, false alarms, and evaluation cost per task.

## Decision rule

Keep the change only if it meets your preselected quality and latency limits and improves the metric you care about after setup and operating costs. Otherwise retain the baseline. This is an exploration plan, not a validated recommendation.


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
