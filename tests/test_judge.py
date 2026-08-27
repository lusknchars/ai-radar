import pytest

from radar.judge import HARDWARE_BRIEF, Judge, JudgmentSchema, build_prompt
from radar.models import Judgment, Paper

PAPER = Paper(arxiv_id="2508.11111", title="Fused INT4 Kernels",
              abstract="We present a fused INT4 by FP16 kernel.",
              authors=["A B"], categories=["cs.LG"], published="2026-08-20")


class FakeParsed:
    def __init__(self, parsed):
        self.parsed_output = parsed


class FakeMessages:
    def __init__(self, parsed):
        self._parsed = parsed
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return FakeParsed(self._parsed)


class FakeClient:
    def __init__(self, parsed):
        self.messages = FakeMessages(parsed)


def valid_schema():
    return JudgmentSchema(technique="Kernel INT4 fundido",
                          summary="Satura banda em batch unitario.",
                          runs_on_3090="sim", rationale="INT4 roda em Ampere.")


def test_hardware_brief_names_the_real_constraints():
    """O veredito so vale se o modelo souber o que a maquina nao tem."""
    for fact in ("Ampere", "24", "FP8", "936"):
        assert fact in HARDWARE_BRIEF


def test_prompt_includes_the_paper_and_the_hardware_brief():
    prompt = build_prompt(PAPER)
    assert PAPER.title in prompt
    assert PAPER.abstract in prompt
    assert HARDWARE_BRIEF in prompt


def test_schema_rejects_a_verdict_outside_the_enum():
    with pytest.raises(Exception):
        JudgmentSchema(technique="T", summary="S", runs_on_3090="talvez", rationale="R")


def test_judge_one_returns_a_domain_judgment():
    judge = Judge(client=FakeClient(valid_schema()), model="claude-opus-5")
    result = judge.judge_one(PAPER)
    assert isinstance(result, Judgment)
    assert result.runs_on_3090 == "sim"
    assert result.technique == "Kernel INT4 fundido"


def test_judge_one_passes_the_configured_model():
    client = FakeClient(valid_schema())
    Judge(client=client, model="claude-opus-5").judge_one(PAPER)
    assert client.messages.calls[0]["model"] == "claude-opus-5"


def test_judge_one_uses_structured_output_not_free_text():
    client = FakeClient(valid_schema())
    Judge(client=client, model="claude-opus-5").judge_one(PAPER)
    assert client.messages.calls[0]["output_format"] is JudgmentSchema


def test_batch_requests_are_keyed_by_arxiv_id():
    from radar.judge import build_batch_requests
    papers = [PAPER, Paper(arxiv_id="2508.22222", title="T2", abstract="A2",
                           authors=[], categories=["cs.LG"], published="2026-08-21")]
    requests = build_batch_requests(papers, model="claude-opus-5")
    assert [r["custom_id"] for r in requests] == ["2508.11111", "2508.22222"]


class FakeBatches:
    def __init__(self, statuses, raise_on=None):
        self._statuses = list(statuses)
        self._raise_on = raise_on
        self.consultas = 0

    def retrieve(self, batch_id):
        self.consultas += 1
        if self._raise_on is not None and self.consultas >= self._raise_on:
            raise RuntimeError("API fora do ar")
        status = self._statuses[min(self.consultas - 1, len(self._statuses) - 1)]
        return type("B", (), {"processing_status": status})()


def fake_client_with(statuses, raise_on=None):
    batches = FakeBatches(statuses, raise_on)
    client = type("C", (), {"messages": type("M", (), {"batches": batches})()})()
    return client, batches


def test_wait_returns_true_when_the_batch_has_already_ended():
    from radar.judge import wait_for_batch
    client, batches = fake_client_with(["ended"])
    naps = []
    assert wait_for_batch(client, "b1", sleep=naps.append, now=lambda: 0.0) is True
    assert naps == []          # nao dorme se ja terminou


def test_wait_polls_until_the_batch_ends():
    from radar.judge import wait_for_batch
    client, batches = fake_client_with(["in_progress", "in_progress", "ended"])
    naps = []
    assert wait_for_batch(client, "b1", sleep=naps.append, now=lambda: 0.0) is True
    assert batches.consultas == 3
    assert len(naps) == 2      # dorme ENTRE consultas, nao depois da ultima


def test_wait_gives_up_at_the_deadline_instead_of_hanging():
    """Sem prazo, um lote travado prende o workflow ate o timeout do runner."""
    from radar.judge import wait_for_batch
    client, _ = fake_client_with(["in_progress"])
    relogio = iter([0.0, 0.0, 10_000.0])
    assert wait_for_batch(client, "b1", sleep=lambda s: None,
                          now=lambda: next(relogio), timeout_seconds=60) is False


def test_wait_returns_false_when_status_lookup_raises():
    from radar.judge import wait_for_batch
    client, _ = fake_client_with(["in_progress"], raise_on=1)
    assert wait_for_batch(client, "b1", sleep=lambda s: None, now=lambda: 0.0) is False


def test_wait_survives_a_lookup_that_starts_failing_midway():
    from radar.judge import wait_for_batch
    client, batches = fake_client_with(["in_progress", "in_progress"], raise_on=2)
    assert wait_for_batch(client, "b1", sleep=lambda s: None, now=lambda: 0.0) is False
    assert batches.consultas == 2


def test_wait_uses_the_configured_poll_interval():
    from radar.judge import wait_for_batch
    client, _ = fake_client_with(["in_progress", "ended"])
    naps = []
    wait_for_batch(client, "b1", sleep=naps.append, now=lambda: 0.0, poll_seconds=7)
    assert naps == [7]


def test_batch_results_are_keyed_not_positional():
    """Resultados do Batch API chegam fora de ordem. Indexar por posicao e bug."""
    from radar.judge import collect_batch_results

    class R:
        def __init__(self, cid, tech):
            self.custom_id = cid
            self.result = type("Res", (), {
                "type": "succeeded",
                "message": type("M", (), {"content": [
                    type("B", (), {"type": "text", "text":
                        '{"technique":"%s","summary":"S","runs_on_3090":"sim",'
                        '"rationale":"R"}' % tech})()]})()})()

    out = collect_batch_results([R("2508.22222", "B"), R("2508.11111", "A")])
    assert out["2508.11111"].technique == "A"
    assert out["2508.22222"].technique == "B"


def test_batch_skips_failed_results_without_crashing():
    from radar.judge import collect_batch_results

    class Errored:
        custom_id = "2508.33333"
        result = type("Res", (), {"type": "errored"})()

    assert collect_batch_results([Errored()]) == {}
