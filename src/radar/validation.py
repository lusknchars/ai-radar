"""Local experiment contracts and deterministic gates, without GPU provisioning."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .report import InfrastructureTier, load_report


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class ExperimentPlan(Contract):
    schema_version: Literal[1] = 1
    paper_id: str = Field(pattern=r"^\d{4}\.\d{4,5}(v\d+)?$")
    report_path: str = ""
    business_use_case: str = ""
    hypothesis: str = ""
    dataset_path: str = ""
    dataset_sha256: str = ""
    quality_metric: str = ""
    implementation_ref: str = ""
    license_review: str = ""
    environment_ref: str = ""
    baseline_command: list[str] = Field(default_factory=list)
    candidate_command: list[str] = Field(default_factory=list)
    validation_tier: InfrastructureTier = "unknown"
    hardware: str = ""
    phase: Literal["local", "gpu"] = "local"
    evaluation_scope: Literal["smoke", "workload"] = "smoke"
    primary_metric: Literal["latency_ms", "cost_usd", "quality"] = "latency_ms"
    minimum_improvement_fraction: float = Field(default=0.1, gt=0, lt=1)
    maximum_quality_drop: float = Field(default=0.01, ge=0, le=1)
    maximum_case_quality_drop: float | None = Field(default=None, ge=0, le=1)
    minimum_quality: float = Field(default=0.8, ge=0, le=1)
    minimum_cases: int = Field(default=20, ge=20)
    seeds: list[int] = Field(default_factory=lambda: [17, 42, 93], min_length=3)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    max_trial_usd: float = Field(default=0, ge=0)
    max_hourly_usd: float = Field(default=0, ge=0)
    max_hours: float = Field(default=0, ge=0)
    storage_and_transfer_allowance_usd: float = Field(default=0, ge=0)


class Observation(Contract):
    case_id: str = Field(min_length=1)
    quality: float = Field(ge=0, le=1)
    latency_ms: float = Field(gt=0)
    cost_usd: float = Field(ge=0)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(root: Path, value: str) -> Path:
    return (root / value).resolve()


def dataset_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [case.get("case_id") if isinstance(case, dict) else None for case in cases]
    if any(not isinstance(item, str) or not item.strip() for item in ids):
        raise ValueError("every dataset row needs a nonempty string case_id")
    if len(set(ids)) != len(ids):
        raise ValueError("dataset case_id values must be unique")
    return cases


def preflight(plan: ExperimentPlan, root: Path) -> list[str]:
    """Return concrete omissions before any adapter is executed."""
    problems = []
    for field in ("report_path", "business_use_case", "hypothesis", "dataset_path",
                  "dataset_sha256", "quality_metric", "implementation_ref",
                  "license_review", "environment_ref", "hardware"):
        if not getattr(plan, field):
            problems.append(f"fill {field}")
    for field in ("baseline_command", "candidate_command"):
        if not getattr(plan, field) or any(not part for part in getattr(plan, field)):
            problems.append(f"set {field} to an explicit executable and arguments")
    if len(set(plan.seeds)) != len(plan.seeds):
        problems.append("seeds must be unique")
    if plan.validation_tier == "unknown":
        problems.append("resolve the minimum validation infrastructure")
    if plan.max_trial_usd <= 0 or plan.max_hourly_usd <= 0 or plan.max_hours <= 0:
        problems.append("set a positive GPU trial budget, hourly ceiling, and duration")
    estimate = plan.max_hourly_usd * plan.max_hours + plan.storage_and_transfer_allowance_usd
    if estimate > plan.max_trial_usd:
        problems.append("compute plus storage/transfer allowance exceeds the trial budget")
    if plan.report_path:
        try:
            report = load_report(_path(root, plan.report_path))
            if report.arxiv_id != plan.paper_id:
                problems.append("report paper ID does not match the experiment")
            if not any(c.source_page and c.source_excerpt for c in report.report.evidence):
                problems.append("deep report needs at least one source-linked claim")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append(f"cannot load deep report: {exc}")
    if plan.dataset_path:
        try:
            dataset = _path(root, plan.dataset_path)
            cases = dataset_cases(dataset)
            if len(cases) < plan.minimum_cases:
                problems.append(f"dataset needs at least {plan.minimum_cases} cases")
            if digest(dataset) != plan.dataset_sha256:
                problems.append("dataset SHA-256 does not match the frozen input")
        except (OSError, ValueError) as exc:
            problems.append(f"cannot load dataset: {exc}")
    return problems


def summarize(rows: list[Observation]) -> dict[str, float]:
    latencies = sorted(row.latency_ms for row in rows)
    return {
        "quality": mean(row.quality for row in rows),
        "latency_ms": latencies[math.ceil(len(latencies) * 0.95) - 1],
        "cost_usd": mean(row.cost_usd for row in rows),
    }


def compare(plan: ExperimentPlan, baseline: list[Observation],
            candidate: list[Observation], expected_ids: set[str]) -> dict:
    """Gate a paired trial on complete coverage, quality, and measured gain."""
    for rows in (baseline, candidate):
        ids = [row.case_id for row in rows]
        if len(ids) != len(set(ids)) or set(ids) != expected_ids:
            raise ValueError("adapter results must contain every case exactly once")
    before, after = summarize(baseline), summarize(candidate)
    metric = plan.primary_metric
    reference = before[metric]
    # Relative improvement over zero is undefined; it must not become a pass.
    improvement = None if reference == 0 else (
        (after[metric] - reference) / reference if metric == "quality"
        else (reference - after[metric]) / reference
    )
    failures = []
    if after["quality"] < plan.minimum_quality:
        failures.append("candidate quality is below the absolute floor")
    if before["quality"] - after["quality"] > plan.maximum_quality_drop + 1e-12:
        failures.append("candidate quality regressed beyond the allowed drop")
    if plan.maximum_case_quality_drop is not None:
        reference_by_id = {row.case_id: row.quality for row in baseline}
        regressed = [row.case_id for row in candidate
                     if reference_by_id[row.case_id] - row.quality
                     > plan.maximum_case_quality_drop + 1e-12]
        if regressed:
            failures.append("case quality regressed: " + ", ".join(regressed))
    if improvement is None or improvement + 1e-12 < plan.minimum_improvement_fraction:
        failures.append("primary metric did not meet the required improvement")
    return {"baseline": before, "candidate": after,
            "improvement_fraction": improvement, "failures": failures}


def run_adapter(command: list[str], payload: dict, root: Path, timeout: int) -> list[Observation]:
    """Run a deliberately configured adapter; its stdout is a JSON array."""
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE,
                                   stdout=output, stderr=errors, start_new_session=True)
        try:
            process.communicate(json.dumps(payload).encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError(f"adapter timed out after {timeout}s") from None
        finally:
            # Also clean up when the operator interrupts the local controller.
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
        if process.returncode:
            raise ValueError(f"adapter exited with status {process.returncode}; check it locally")
        if output.tell() > 10_000_000:
            raise ValueError("adapter output exceeds 10 MB")
        output.seek(0)
        rows = json.load(output)
    if not isinstance(rows, list):
        raise ValueError("adapter stdout must be a JSON array")
    return [Observation.model_validate(row) for row in rows]


def run_experiment(plan: ExperimentPlan, root: Path) -> dict:
    problems = preflight(plan, root)
    if problems:
        raise ValueError("; ".join(problems))
    cases = dataset_cases(_path(root, plan.dataset_path))
    expected_ids = {case["case_id"] for case in cases}
    result = {
        "schema_version": 1, "paper_id": plan.paper_id, "phase": plan.phase,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan.model_dump(),
        "plan_sha256": hashlib.sha256(plan.model_dump_json().encode()).hexdigest(),
        "report_sha256": digest(_path(root, plan.report_path)),
        "dataset_sha256": plan.dataset_sha256,
        "host": {"platform": platform.platform(), "python": platform.python_version()},
        "trials": [], "decision": "incomplete", "failures": [],
    }
    try:
        for index, seed in enumerate(plan.seeds):
            observations = {}
            order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
            for arm in order:
                observations[arm] = run_adapter(
                    getattr(plan, f"{arm}_command"),
                    {"cases": cases, "seed": seed, "arm": arm},
                    root, plan.timeout_seconds,
                )
            comparison = compare(plan, observations["baseline"], observations["candidate"], expected_ids)
            result["trials"].append({
                "seed": seed, "order": list(order), **comparison,
                "observations": {arm: [row.model_dump() for row in rows]
                                 for arm, rows in observations.items()},
            })
        if digest(_path(root, plan.dataset_path)) != plan.dataset_sha256:
            raise ValueError("dataset changed during the experiment")
        if digest(_path(root, plan.report_path)) != result["report_sha256"]:
            raise ValueError("report changed during the experiment")
        failures = [f"seed {trial['seed']}: {failure}"
                    for trial in result["trials"] for failure in trial["failures"]]
        result["failures"] = failures
        result["decision"] = "revise" if failures else (
            "ready_for_gpu_trial" if plan.phase == "local" else (
                "ready_for_workload_validation" if plan.evaluation_scope == "smoke"
                else "ready_for_product_pilot")
        )
    except (OSError, ValueError) as exc:
        result["failures"].append(str(exc))
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="write an incomplete experiment plan for a paper")
    init.add_argument("paper_id")
    init.add_argument("--out", type=Path, required=True)
    for action in ("check", "run"):
        command = sub.add_parser(action)
        command.add_argument("plan", type=Path)
        if action == "run":
            command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            plan = ExperimentPlan(paper_id=args.paper_id)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8") as target:
                target.write(plan.model_dump_json(indent=2) + "\n")
            print(f"Draft written to {args.out}; fill it before running check.")
            return 0
        plan = ExperimentPlan.model_validate_json(args.plan.read_text())
        root = args.plan.resolve().parent
        problems = preflight(plan, root)
        if problems:
            print(json.dumps({"decision": "blocked", "failures": problems}, indent=2))
            return 1
        if args.action == "check":
            print("Preflight passed. Adapter commands have not been executed.")
            return 0
        # Reserve a new artifact before running work, never overwrite evidence.
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as target:
            target.write('{"decision": "incomplete", "failures": ["run interrupted"]}\n')
            target.flush()
            result = run_experiment(plan, root)
            target.seek(0)
            target.write(json.dumps(result, indent=2) + "\n")
            target.truncate()
        print(f"{result['decision']}: {args.out}")
        return 0 if result["decision"].startswith("ready_for_") else 1
    except (OSError, ValueError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
