"""GPU adapter for a fixed GLM-4.7-Flash MTP comparison.

Importing this module needs no GPU packages. Actual execution requires the
pinned vLLM container on the rented GPU. Input/output follow radar.validation.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation import Observation, digest

MODEL = "zai-org/GLM-4.7-Flash"
REVISION = "7dd20894a642a0aa287e9827cb1a1f7f91386b67"
VLLM_VERSION = "0.29.0"


def grade_json(text: str, expected: Any, finish_reason: str) -> float:
    """Compare complete JSON answers, preserving JSON types and list order."""
    if finish_reason != "stop":
        return 0.0
    answer = text.strip()
    if answer.startswith("```json\n") and answer.endswith("\n```"):
        answer = answer[8:-4]
    try:
        actual = json.loads(answer)
        canonical = lambda value: json.dumps(value, sort_keys=True, allow_nan=False)
        return float(canonical(actual) == canonical(expected))
    except (ValueError, TypeError):
        return 0.0


def engine_settings(arm: str, seed: int) -> dict:
    """Only the candidate enables MTP; all other engine inputs are identical."""
    if arm not in {"baseline", "candidate"}:
        raise ValueError("arm must be baseline or candidate")
    settings = dict(model=MODEL, revision=REVISION, tokenizer_revision=REVISION,
                    dtype="bfloat16", tensor_parallel_size=1, max_model_len=4096,
                    max_num_seqs=1, gpu_memory_utilization=0.85,
                    enable_prefix_caching=False, seed=seed)
    if arm == "candidate":
        settings["speculative_config"] = {"method": "mtp", "num_speculative_tokens": 1}
    return settings


def benchmark(engine, cases: list[dict], sampling_params, hourly_rate: float,
              clock=time.perf_counter) -> tuple[list[Observation], list[dict]]:
    """Measure sequential, complete responses with two unmeasured warmups."""
    if not math.isfinite(hourly_rate) or hourly_rate <= 0:
        raise ValueError("hourly rate must be finite and positive")
    def generate(prompt):
        return engine.chat(
            [{"role": "user", "content": prompt}], sampling_params=sampling_params,
            use_tqdm=False, chat_template_kwargs={"enable_thinking": False},
        )[0]

    for _ in range(2):
        generate('Return only the JSON object {"ready": true}.')
    observations, details = [], []
    for case in cases:
        started = clock()
        response = generate(case["prompt"])
        elapsed = clock() - started
        output = response.outputs[0]
        observation = Observation(
            case_id=case["case_id"],
            quality=grade_json(output.text, case["expected_json"], output.finish_reason),
            latency_ms=elapsed * 1000,
            cost_usd=hourly_rate * elapsed / 3600,
        )
        observations.append(observation)
        details.append({
            **observation.model_dump(), "category": case["category"],
            "output": output.text, "finish_reason": output.finish_reason,
            "prompt_tokens": len(response.prompt_token_ids),
            "output_tokens": len(output.token_ids),
        })
    return observations, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hourly-rate-usd", required=True, type=float)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.hourly_rate_usd) or args.hourly_rate_usd <= 0:
        parser.error("hourly rate must be finite and positive")
    payload = json.load(sys.stdin)
    cases = payload["cases"]
    if not cases or len({c["case_id"] for c in cases}) != len(cases):
        parser.error("cases must be nonempty and have unique IDs")
    settings = engine_settings(payload["arm"], payload["seed"])
    if importlib.metadata.version("vllm").split("+")[0] != VLLM_VERSION:
        parser.error(f"this experiment requires vLLM {VLLM_VERSION}")

    import torch
    from vllm import LLM, SamplingParams

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        parser.error("expose exactly one CUDA GPU to this experiment")
    gpu = subprocess.check_output([
        "nvidia-smi", "--query-gpu=name,uuid,memory.total,driver_version",
        "--format=csv,noheader",
    ], text=True).strip()
    if "H200" not in gpu:
        parser.error("this initial experiment is specified for one H200")
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = args.evidence_dir / f"{payload['arm']}-{payload['seed']}-{uuid.uuid4().hex}.json"
    evidence = {
        "schema_version": 1, "status": "incomplete", "engine": settings,
        "vllm_version": VLLM_VERSION, "torch_version": torch.__version__,
        "adapter_sha256": digest(Path(__file__)),
        "gpu": gpu, "started_at": datetime.now(timezone.utc).isoformat(),
        "dataset_kind": "generated engineering smoke cases, not production traffic",
        "sampling": {"temperature": 0.0, "max_tokens": 1024, "seed": payload["seed"]},
        "thinking": False, "concurrency": 1, "hourly_rate_usd": args.hourly_rate_usd,
        "cost_basis": "request wall time only; total adapter time also reported separately",
        "observations": [],
    }
    started = time.perf_counter()
    # Preserve diagnostics separately; C++/worker logging must not corrupt stdout JSON.
    original_stdout = os.dup(1)
    original_stderr = os.dup(2)
    runtime_log = evidence_path.with_suffix(".log").open("x", encoding="utf-8")
    try:
        os.dup2(runtime_log.fileno(), 2)
        os.dup2(2, 1)
        with evidence_path.open("x", encoding="utf-8") as target:
            target.write(json.dumps(evidence, indent=2) + "\n")
            target.flush()
            try:
                engine = LLM(**settings)
                observations, details = benchmark(
                    engine, cases, SamplingParams(**evidence["sampling"]), args.hourly_rate_usd,
                )
                evidence["observations"] = details
                evidence["gpu_memory_after_workload_mib"] = subprocess.check_output([
                    "nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                ], text=True).strip()
                evidence["memory_note"] = "Whole-GPU snapshot after workload, not peak VRAM."
                evidence["status"] = "complete"
            except Exception as exc:
                evidence["error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                evidence["adapter_seconds"] = time.perf_counter() - started
                evidence["adapter_compute_estimate_usd"] = (
                    evidence["adapter_seconds"] * args.hourly_rate_usd / 3600)
                evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
                target.seek(0)
                target.write(json.dumps(evidence, indent=2) + "\n")
                target.truncate()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(original_stdout, 1)
        os.dup2(original_stderr, 2)
        os.close(original_stdout)
        os.close(original_stderr)
        runtime_log.close()
    print(json.dumps([row.model_dump() for row in observations]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
