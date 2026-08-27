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


def test_schema_forbids_additional_properties():
    """O contrato de saida estruturada exige `additionalProperties: false` em
    todo objeto (spec secao 5). O Pydantic so emite esse campo sob
    extra="forbid"; sem ele a API rejeita o lote inteiro e todo paper do dia
    cai como `sem_julgamento`. A chamada nao da para exercitar offline, entao o
    teste trava a FORMA do schema, que e o que vai no corpo da requisicao."""
    schema = JudgmentSchema.model_json_schema()
    assert schema["additionalProperties"] is False


def test_batch_request_carries_the_schema_with_additional_properties_forbidden():
    """O caminho de lote e o unico que roda em producao: ele monta o schema a
    mao, entao a garantia acima precisa chegar ate o corpo da requisicao."""
    from radar.judge import build_batch_requests
    schema = build_batch_requests([PAPER], model="claude-opus-5")[0]["params"][
        "output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False


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


def test_judge_one_asks_for_adaptive_thinking_at_low_effort():
    """Spec secao 5. No Opus 5 o thinking vem ligado e o esforco default e
    `high`: sem os dois explicitos, cada julgamento de uma frase raciocina muito
    acima do orcado, e tokens de thinking contam como saida."""
    client = FakeClient(valid_schema())
    Judge(client=client, model="claude-opus-5").judge_one(PAPER)
    chamada = client.messages.calls[0]
    assert chamada["thinking"] == {"type": "adaptive"}
    assert chamada["output_config"]["effort"] == "low"


def test_the_verdict_field_tells_the_model_the_criterion():
    """runs_on_3090 e o veredito que o usuario le. O Literal restringe o token
    mas nao diz nada sobre o criterio."""
    campo = JudgmentSchema.model_json_schema()["properties"]["runs_on_3090"]
    assert "FP8" in campo["description"]


def test_max_tokens_leaves_room_for_thinking():
    """Tokens de thinking contam contra o max_tokens. Um teto apertado corta o
    julgamento no meio do JSON, e o truncado e descartado como malformado."""
    from radar.judge import MAX_TOKENS
    assert MAX_TOKENS >= 4096


def test_batch_requests_ask_for_adaptive_thinking_at_low_effort():
    """O caminho de lote e o unico com chamador em producao: e ele que precisa
    carregar a configuracao da spec."""
    from radar.judge import build_batch_requests
    params = build_batch_requests([PAPER], model="claude-opus-5")[0]["params"]
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"]["effort"] == "low"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert params["max_tokens"] >= 4096


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


def _sucesso_com_texto(cid, texto):
    return type("R", (), {
        "custom_id": cid,
        "result": type("Res", (), {
            "type": "succeeded",
            "message": type("M", (), {"content": [
                type("B", (), {"type": "text", "text": texto})()]})()})()})()


def test_a_malformed_judgment_is_logged_with_its_custom_id(caplog):
    """Descartar calado compoe com o resto: o paper aparece como
    `sem_julgamento` no markdown e nao ha como saber qual quebrou nem por que."""
    from radar.judge import collect_batch_results
    with caplog.at_level("WARNING", logger="radar.judge"):
        out = collect_batch_results([_sucesso_com_texto("2508.44444", '{"technique":')])
    assert out == {}
    assert "2508.44444" in caplog.text


def test_a_judgment_with_an_invalid_verdict_is_logged_not_swallowed(caplog):
    from radar.judge import collect_batch_results
    payload = ('{"technique":"T","summary":"S","runs_on_3090":"talvez",'
               '"rationale":"R"}')
    with caplog.at_level("WARNING", logger="radar.judge"):
        out = collect_batch_results([_sucesso_com_texto("2508.55555", payload)])
    assert out == {}
    assert "2508.55555" in caplog.text
