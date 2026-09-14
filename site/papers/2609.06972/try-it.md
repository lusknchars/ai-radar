# Try the idea: AgentDrift: A Step-Labeled Benchmark of Injection-Hijacked LLM Agent Trajectories

Paperraft interpretation of the full paper. No Paperraft experiment has been run.

Paper: https://arxiv.org/pdf/2609.06972v1

## Possible product use

Possible product use: an assistant that reads customer uploads or fetched web pages before calling your APIs.

Use the dataset to challenge your existing checks offline. Keep tools mocked so that a test cannot send messages, alter records, or expose real customer data.

## Baseline

Your current detector against a small human-reviewed set. Separate real attack success, resisted attacks, and legitimate content that looks suspicious.

## First test

1. Fetch the official dataset linked by the paper, record its version and license, and inspect the label definitions. Start with a small sample of attacked and legitimate histories that resemble your workflow.
2. Split by world identity so the same world cannot appear in training and evaluation. Keep product test examples separate from any detector tuning. Check for repeated templates and names.
3. Replay the held-out cases through your existing checks with mocked tools. Record the exact step flagged, missed successful attacks, and legitimate actions blocked.
4. Only then compare a candidate detection change on the same cases. Manually review disagreements and repeat with held-out examples from your own agent before enabling enforcement.

## Measure

Attack recall, false-positive rate on legitimate tasks, delay until detection, review burden, and detector cost. Keep denominators and attack types visible instead of reporting one overall score.

## Decision rule

Keep a change only if it catches more consequential attacks within your preselected false-alarm and latency limits. Synthetic benchmark performance alone is not evidence that a production agent is protected.

## Read the benchmark correctly

### Accuracy that comes from a shortcut

Binary accuracy counts correctly classified attacked and non-attacked histories.

Majority-class prediction: 55.8%. World-identity lookup: 86.1%. Difference: +30.3 percentage points.

Default 1,881-trajectory test split. The lookup reuses world identities seen in training.

This is leakage evidence, not a 30-point security improvement. A detector must be evaluated with identity shortcuts controlled.

Source: https://arxiv.org/pdf/2609.06972v1#page=14, Table XI; explanation on page 13.

### Attack recall is a different denominator

Recall is the share of actual attacks detected. Here the baseline catches 460 of 831.

No alternative detector measured here: Not compared. Simple feature classifier: 55.4%. Difference: No matched comparison.

Single held-out test evaluation of a six-feature logistic regression.

This is not overall accuracy. The partial-hijack subset has 8.2% recall, and benign histories have a 10.5% false-alarm rate.

Source: https://arxiv.org/pdf/2609.06972v1#page=14, Table XIII.

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
