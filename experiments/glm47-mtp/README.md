# GLM-4.7-Flash: first GPU experiment

Status: prepared and checked locally. No model inference or GPU benchmark has run.

This trial tests whether AI Radar can turn a paper-inspired technique into a
repeatable, falsifiable experiment. It compares the same GLM checkpoint with
native multi-token prediction, MTP, disabled and enabled. A passing result is
evidence about this configuration and these tasks, not validation of an entire
paper or a production recommendation.

## Fixed experiment

| Item | Setting |
|---|---|
| Model | `zai-org/GLM-4.7-Flash` |
| Model/tokenizer revision | `7dd20894a642a0aa287e9827cb1a1f7f91386b67` |
| Runtime | vLLM 0.29.0, container manifest pinned in Dockerfile |
| GPU | One H200; adapter requires exactly one visible GPU and records its UUID |
| Precision | BF16 in both arms |
| Baseline | Ordinary generation |
| Candidate | Native MTP, one speculative token |
| Other settings | Concurrency 1, context limit 4096, output limit 1024, temperature 0 |
| Thinking / prefix cache | Disabled in both arms |
| Data | 40 generated cases in four categories; SHA-256 frozen in plan.json |
| Repeats | Three pairs, alternating which arm starts first |
| Performance gate | At least 10% lower p95 complete-response latency in every pair |
| Quality gate | At least 90% correct; no baseline-correct case may become incorrect |
| Successful decision | `ready_for_workload_validation` |

At temperature zero the seeds are repeat identifiers, not independent samples
of model quality. Repeat timing runs measure variability in execution.

The categories are sorting into JSON, catalog extraction, invoice arithmetic,
and longer structured transformations. All answers have deterministic graders.
Malformed JSON, wrong values or types, extra content, and truncated responses
fail. These are synthetic engineering cases, not a representative SaaS dataset.
Inspect output lengths in the artifact: small tasks may give MTP little room
to help. A negative result is valid and should not trigger easier thresholds.

## Paper and implementation relationship

The methodological reference is
[Fast Inference from Transformers via Speculative Decoding](https://arxiv.org/abs/2211.17192).
`source-review.json` is a focused editorial review for this experiment, with PDF
and extracted-text hashes and a checked excerpt on page 1. It is not a new
automatically generated public report. The PDF version used is v2.

The deployment reference is the
[official GLM-4.7-Flash model card](https://huggingface.co/zai-org/GLM-4.7-Flash/blob/7dd20894a642a0aa287e9827cb1a1f7f91386b67/README.md),
which documents native MTP. This uses a trained MTP component, whereas the
reference paper describes a separate approximation model. Therefore the trial
does not reproduce that paper's T5X results or establish distributional
equivalence for vLLM. The local probability-correction check is also separate.

The source review's 48–80 GB minimum validation tier is an inference, not a
tested allocation. This experiment deliberately targets an H200 for headroom.
The model card's example uses tensor parallelism across four devices; our TP1,
short-context configuration still needs a GPU startup check.

## Local checks

From the repository root:

```bash
.venv/bin/python -m radar.validation check experiments/glm47-mtp/plan.json
.venv/bin/python -m pytest tests/test_glm47_trial.py tests/test_validation.py -q
```

The plan proposes a $20 ceiling: at most $5/hour for three hours plus a $5
storage/transfer allowance. The adapter's $3.98/hour input comes from the user's
H200 screenshot. Update it to the selected offer's actual rate before freezing
the final trial bundle. The proposal is not rental authorization, a live quote,
or an enforced cloud spending limit.

## Run after selecting the GPU offer

Use the pinned vLLM image from the Dockerfile as the Vast instance image, copy
the repo source and experiment directory into that instance, then run:

```bash
export PYTHONPATH="$PWD/src"
python -m radar.validation check experiments/glm47-mtp/plan.json
python -m radar.validation run experiments/glm47-mtp/plan.json \
  --out eval/results/glm47-mtp/run-001.json
```

The GPU image supplies vLLM, PyTorch, and Pydantic. Keep the exact version; an
incompatible build must fail rather than silently disable MTP. Check that no
other job is sharing the selected GPU. Record `git diff` and the untracked trial
files with the exported bundle, since the image manifest does not pin our
working-tree code.

For a GPU host where Docker is available, the equivalent packaged form is:

```bash
docker build -f experiments/glm47-mtp/Dockerfile -t radar-glm47-mtp .
mkdir -p eval/results/glm47-mtp
docker run --rm --gpus 'device=0' --ipc=host \
  -v radar-model-cache:/models \
  -v "$PWD/eval/results:/workspace/eval/results" \
  radar-glm47-mtp run experiments/glm47-mtp/plan.json \
  --out eval/results/glm47-mtp/run-001.json
```

This Docker command is for an existing Docker-capable GPU host; it does not
require nested Docker inside a Vast container. Download the checkpoint once
and retain the model cache across arms. Budget disk space for roughly 62 GB of
weights plus container/cache overhead. Actual loading has not been tested here.

The adapter creates a fresh engine per arm and repeat, with two warmup requests.
Model loading and warmups are excluded from request latency, but included in
the separate adapter-time compute estimate. Each arm has a 20-minute process
timeout. A timeout stops the local job, not the rented instance.

## Evidence to export

- `run-001.json`: plan, source/data hashes, all paired observations, and gate decision.
- Per-arm JSON files: generated answers, correctness, finish reasons, input/output
  token counts, runtime settings, GPU UUID/driver, timings, and cost estimates.
- Per-arm `.log` files: model initialization and runtime diagnostics.
- Exact trial source, plan, frozen dataset, model revision, runtime digest, and
  provider billing information.

Request cost is estimated from sequential wall time at the specified rental
rate. The adapter also reports total adapter time; neither estimate includes
all provider startup, idle, storage, or transfer charges. Reconcile with the
actual instance bill. The memory value is a post-workload whole-GPU snapshot,
not peak VRAM. This first adapter does not measure streaming TTFT or concurrent
serving throughput.

Set an external rental deadline before execution. Export evidence and destroy
the Vast instance afterward, including after failures. Exiting the container
does not perform provider teardown.

If the smoke gate passes, test representative prompts, longer contexts,
concurrency, and a larger quality sample. Only then decide whether to transfer
the technique to a larger GLM model or study another paper. A failed or
inconclusive comparison is an acceptable outcome of this first system check.
