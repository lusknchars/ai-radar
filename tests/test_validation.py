import json
import sys

import pytest
from pydantic import ValidationError

from radar.report import generate_report, save_report
from radar.validation import (ExperimentPlan, Observation, compare, digest, main,
                              preflight, run_adapter, run_experiment)
from tests.test_report import FakeKimi, PAPER, deep_report


@pytest.fixture
def plan(tmp_path):
    report = deep_report()
    excerpt = "Measured results on the held-out retrieval evaluation set."
    report.evidence[0].source_page = 1
    report.evidence[0].source_excerpt = excerpt
    document = generate_report(PAPER, f"[AI-RADAR PAGE 1]\n{excerpt}",
                               FakeKimi(report), provider="test", model="fixture")
    report_path = save_report(document, tmp_path / "reports")
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text("\n".join(json.dumps({"case_id": str(i)}) for i in range(20)))
    return ExperimentPlan(
        paper_id=PAPER.arxiv_id, report_path=str(report_path),
        business_use_case="Reduce document-search latency", hypothesis="Same quality, lower p95",
        dataset_path="cases.jsonl", dataset_sha256=digest(dataset),
        quality_metric="Exact-match accuracy", implementation_ref="test fixture revision 1",
        license_review="Owned test fixture", environment_ref="Python test environment",
        baseline_command=[sys.executable, "adapter.py"],
        candidate_command=[sys.executable, "adapter.py"],
        validation_tier="api_or_cpu", hardware="CPU test fixture",
        max_trial_usd=5, max_hourly_usd=1, max_hours=2,
        storage_and_transfer_allowance_usd=1,
    )


def rows(latency=100, quality=0.9, cost=0.01):
    return [Observation(case_id=str(i), latency_ms=latency, quality=quality, cost_usd=cost)
            for i in range(20)]


IDS = {str(i) for i in range(20)}


def test_fast_but_wrong_candidate_fails(plan):
    result = compare(plan, rows(), rows(latency=50, quality=0.7), IDS)
    assert result["improvement_fraction"] == 0.5
    assert len(result["failures"]) == 2


def test_paired_quality_gate_detects_regressions_hidden_by_the_mean(plan):
    plan.maximum_case_quality_drop = 0
    before, after = rows(quality=1), rows(latency=50, quality=1)
    before[0].quality = 0
    after[1].quality = 0
    result = compare(plan, before, after, IDS)
    assert result["baseline"]["quality"] == result["candidate"]["quality"]
    assert any("case quality regressed: 1" == failure for failure in result["failures"])


def test_missing_or_duplicate_results_cannot_pass(plan):
    for bad_rows in (rows()[:-1], rows() + rows()[:1]):
        with pytest.raises(ValueError, match="every case exactly once"):
            compare(plan, rows(), bad_rows, IDS)


def test_p95_catches_slow_tail(plan):
    candidate = rows(latency=40)
    candidate[-1].latency_ms = 300
    candidate[-2].latency_ms = 300
    result = compare(plan, rows(), candidate, IDS)
    assert result["candidate"]["latency_ms"] == 300
    assert result["failures"]


def test_zero_cost_baseline_is_not_infinite_savings(plan):
    plan.primary_metric = "cost_usd"
    result = compare(plan, rows(cost=0), rows(cost=0), IDS)
    assert result["improvement_fraction"] is None
    assert result["failures"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_measurements_rejected(value):
    with pytest.raises(ValidationError):
        Observation(case_id="1", latency_ms=value, quality=0.9, cost_usd=0)


def test_preflight_checks_source_data_and_budget(plan, tmp_path):
    assert preflight(plan, tmp_path) == []
    plan.max_trial_usd = 0.5
    plan.seeds = [1, 1, 1]
    (tmp_path / "cases.jsonl").write_text('{"case_id":"changed"}\n')
    failures = preflight(plan, tmp_path)
    assert any("budget" in f for f in failures)
    assert any("unique" in f for f in failures)
    assert any("SHA-256" in f for f in failures)
    assert any("20 cases" in f for f in failures)


def test_unlinked_report_and_wrong_paper_block_preflight(plan, tmp_path):
    report = json.loads((tmp_path / plan.report_path).read_text())
    report["report"]["evidence"][0]["source_page"] = None
    (tmp_path / plan.report_path).write_text(json.dumps(report))
    plan.paper_id = "2601.12345"
    failures = preflight(plan, tmp_path)
    assert any("source-linked" in f for f in failures)
    assert any("paper ID" in f for f in failures)


ADAPTER = '''import json, sys
request = json.load(sys.stdin)
# Synthetic protocol fixture. These numbers are not measurements of a paper.
latency = 100 if request["arm"] == "baseline" else 70
print(json.dumps([{"case_id": c["case_id"], "quality": 0.9,
                   "latency_ms": latency, "cost_usd": 0.01}
                  for c in request["cases"]]))
'''


def test_runner_records_all_paired_trials_and_alternates_order(plan, tmp_path):
    (tmp_path / "adapter.py").write_text(ADAPTER)
    result = run_experiment(plan, tmp_path)
    assert result["decision"] == "ready_for_gpu_trial"
    assert len(result["trials"]) == 3
    assert result["trials"][0]["order"] == ["baseline", "candidate"]
    assert result["trials"][1]["order"] == ["candidate", "baseline"]
    assert len(result["trials"][0]["observations"]["candidate"]) == 20
    assert result["report_sha256"] == digest(tmp_path / plan.report_path)
    assert result["plan"]["hypothesis"] == plan.hypothesis


def test_gpu_smoke_does_not_claim_product_pilot_readiness(plan, tmp_path):
    (tmp_path / "adapter.py").write_text(ADAPTER)
    plan.phase = "gpu"
    result = run_experiment(plan, tmp_path)
    assert result["decision"] == "ready_for_workload_validation"


def test_crashed_adapter_produces_incomplete_evidence(plan, tmp_path):
    (tmp_path / "adapter.py").write_text("raise SystemExit(2)")
    result = run_experiment(plan, tmp_path)
    assert result["decision"] == "incomplete"
    assert result["trials"] == []
    assert result["failures"]


def test_input_mutation_during_run_invalidates_measurements(plan, tmp_path):
    (tmp_path / "adapter.py").write_text(ADAPTER + '\nopen("cases.jsonl", "a").write("\\n")\n')
    result = run_experiment(plan, tmp_path)
    assert result["decision"] == "incomplete"
    assert any("dataset changed" in failure for failure in result["failures"])


def test_non_array_adapter_output_cannot_pass(plan, tmp_path):
    (tmp_path / "adapter.py").write_text('print("{}")')
    result = run_experiment(plan, tmp_path)
    assert result["decision"] == "incomplete"
    assert result["failures"]


def test_timeout_is_a_failure(tmp_path):
    with pytest.raises(ValueError, match="timed out"):
        run_adapter([sys.executable, "-c", "import time; time.sleep(30)"], {}, tmp_path, 1)


def test_one_bad_seed_blocks_promotion(plan, tmp_path):
    (tmp_path / "adapter.py").write_text(ADAPTER.replace(
        'latency = 100 if request["arm"] == "baseline" else 70',
        'latency = 100 if request["arm"] == "baseline" or request["seed"] == 42 else 70'))
    result = run_experiment(plan, tmp_path)
    assert result["decision"] == "revise"
    assert result["failures"][0].startswith("seed 42:")


def test_draft_cli_blocks_execution_and_never_overwrites(tmp_path):
    path = tmp_path / "plan.json"
    assert main(["init", "2601.12345", "--out", str(path)]) == 0
    original = path.read_text()
    assert main(["init", "2601.54321", "--out", str(path)]) == 1
    assert path.read_text() == original
    assert main(["check", str(path)]) == 1


def test_cli_runs_and_preserves_result_artifact(plan, tmp_path):
    (tmp_path / "adapter.py").write_text(ADAPTER)
    path, artifact = tmp_path / "plan.json", tmp_path / "result.json"
    path.write_text(plan.model_dump_json())
    assert main(["check", str(path)]) == 0
    assert main(["run", str(path), "--out", str(artifact)]) == 0
    original = artifact.read_text()
    assert json.loads(original)["decision"] == "ready_for_gpu_trial"
    assert main(["run", str(path), "--out", str(artifact)]) == 1
    assert artifact.read_text() == original
