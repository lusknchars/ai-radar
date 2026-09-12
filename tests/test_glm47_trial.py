from pathlib import Path
from types import SimpleNamespace

import pytest

from radar.glm47_trial import benchmark, engine_settings, grade_json
from radar.validation import ExperimentPlan, preflight


def test_prepared_pack_passes_preflight_with_frozen_inputs():
    root = Path(__file__).resolve().parents[1] / "experiments" / "glm47-mtp"
    plan = ExperimentPlan.model_validate_json((root / "plan.json").read_text())
    assert preflight(plan, root) == []
    assert plan.evaluation_scope == "smoke"
    assert plan.maximum_case_quality_drop == 0


@pytest.mark.parametrize("text,expected,reason,score", [
    ('{"answer":42}', {"answer": 42}, "stop", 1),
    ('```json\n{"answer":42}\n```', {"answer": 42}, "stop", 1),
    ('{"answer":43}', {"answer": 42}, "stop", 0),
    ('{"answer":true}', {"answer": 1}, "stop", 0),
    ('{"answer":42}', {"answer": 42}, "length", 0),
    ('Here it is: {"answer":42}', {"answer": 42}, "stop", 0),
    ('{"answer":NaN}', {"answer": 42}, "stop", 0),
])
def test_grader_requires_correct_complete_typed_json(text, expected, reason, score):
    assert grade_json(text, expected, reason) == score


def test_only_mtp_changes_between_arms():
    baseline, candidate = engine_settings("baseline", 42), engine_settings("candidate", 42)
    assert candidate.pop("speculative_config") == {"method": "mtp", "num_speculative_tokens": 1}
    assert candidate == baseline
    assert baseline["enable_prefix_caching"] is False


def test_benchmark_scores_real_outputs_and_includes_failed_cases():
    class Engine:
        def __init__(self):
            self.calls = []
        def chat(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            answer = '42' if len(self.calls) == 3 else '0'
            return [SimpleNamespace(prompt_token_ids=[1, 2, 3], outputs=[
                SimpleNamespace(text=answer, finish_reason="stop", token_ids=[4])])]

    engine = Engine()
    cases = [{"case_id": str(i), "category": "arithmetic", "prompt": "Compute", "expected_json": 42}
             for i in range(2)]
    ticks = iter([0.0, 1.0, 2.0, 4.0])
    rows, details = benchmark(engine, cases, object(), 3.6, clock=lambda: next(ticks))
    assert len(engine.calls) == 4  # two warmups plus the two scored cases
    assert [r.quality for r in rows] == [1, 0]
    assert [r.latency_ms for r in rows] == [1000, 2000]
    assert rows[0].cost_usd == pytest.approx(0.001)
    assert details[1]["output"] == "0"
    assert all(call[1]["chat_template_kwargs"] == {"enable_thinking": False}
               for call in engine.calls)
