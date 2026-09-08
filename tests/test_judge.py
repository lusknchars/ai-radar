import json

import pytest

from radar.formulas import (FormulaCandidate, FormulaSelection,
                            FormulaSelectionItem)
from radar.judge import (JUDGMENT_PROMPT_VERSION, LEITOR_BRIEF, Judge, JudgmentSchema,
                         KimiFormulaSelector, KimiJudge,
                         build_formula_selection_prompt,
                         build_kimi_formula_request, build_kimi_request,
                         build_prompt)
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
    return JudgmentSchema(technique="Kernel INT4 fundido", familia="quantizacao",
                          pratica="testar", ganho_eixo="velocidade",
                          ganho_fator=2.3, ganho_texto="2.3x sobre FP16",
                          resumo="Troca o kernel FP16 por INT4 fundido.",
                          porque="Roda em infra pequena, mas o ganho depende do caso.")


def test_leitor_brief_descreve_a_restricao_que_importa():
    for fato in ("Inference Observatory", "PUBLIC LLM API", "time to first token",
                 "behavioral", "no provider internals"):
        assert fato in LEITOR_BRIEF


def test_prompt_includes_the_paper_and_the_reader_brief():
    prompt = build_prompt(PAPER)
    assert PAPER.title in prompt
    assert PAPER.abstract in prompt
    assert LEITOR_BRIEF in prompt


def test_prompt_versions_and_defines_the_public_api_relevance_gate():
    prompt = build_prompt(PAPER)
    assert JUDGMENT_PROMPT_VERSION in prompt
    assert "set pratica to nao_aplica" in prompt
    assert "custom CMOS accelerator" in prompt
    assert "public endpoint" in prompt


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


def test_schema_rejects_a_familia_outside_the_enum():
    with pytest.raises(Exception):
        JudgmentSchema(technique="T", familia="familia_inventada",
                       pratica="testar", ganho_eixo="nenhum", ganho_texto="",
                       resumo="R", porque="P")


def test_judge_one_returns_a_domain_judgment():
    judge = Judge(client=FakeClient(valid_schema()), model="claude-opus-5")
    result = judge.judge_one(PAPER)
    assert isinstance(result, Judgment)
    assert result.pratica == "testar"
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


class FakeKimiResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _kimi_payload(schema=None):
    schema = schema or valid_schema()
    return {"choices": [{"message": {"content": schema.model_dump_json()}}]}


def test_kimi_request_uses_strict_json_schema_and_low_reasoning():
    body = build_kimi_request(PAPER, "kimi-k3")
    assert body["model"] == "kimi-k3"
    assert body["max_completion_tokens"] == 8192
    assert "max_tokens" not in body
    assert body["reasoning_effort"] == "low"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"][
        "additionalProperties"] is False


def test_k2_6_formula_request_disables_thinking_without_k3_effort():
    body = build_kimi_formula_request(
        messages=[{"role": "user", "content": "Select candidate eq-1."}],
        model="kimi-k2.6",
        thinking="disabled",
        output_type=JudgmentSchema,
        schema_name="formula_selection",
    )
    assert body["model"] == "kimi-k2.6"
    assert body["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in body
    assert body["response_format"]["json_schema"]["strict"] is True


def test_formula_request_rejects_an_unknown_k2_6_thinking_mode():
    with pytest.raises(ValueError, match="thinking"):
        build_kimi_formula_request(
            messages=[], model="kimi-k2.6", thinking="adaptive",
            output_type=JudgmentSchema, schema_name="formula_selection",
        )


FORMULA = FormulaCandidate(
    candidate_id="eq-0123456789abcdef", path="main.tex",
    environment="equation", latex=r"L = \\sum_i e_i",
    context_before="We propose the following objective.",
    context_after="It penalizes reconstruction error.",
)


def test_formula_prompt_includes_exact_candidates_and_forbids_authored_latex():
    prompt = build_formula_selection_prompt(PAPER, [FORMULA])
    assert FORMULA.candidate_id in prompt
    payload = json.loads(prompt.split("Candidates extracted verbatim:\n", 1)[1])
    assert payload[0]["latex"] == FORMULA.latex
    assert PAPER.abstract in prompt
    assert "Never copy, correct, or generate LaTeX" in prompt


def test_k2_6_selector_returns_verified_ids_with_formula_request_shape():
    calls = []
    selection = FormulaSelection(
        kind="formula",
        selected=[FormulaSelectionItem(
            candidate_id=FORMULA.candidate_id, role="loss")],
    )

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return FakeKimiResponse(_kimi_payload(selection))

    result = KimiFormulaSelector(
        "secret", post=post, sleep=lambda _: None, request_interval=0,
    ).select(PAPER, [FORMULA])
    assert result == selection
    assert calls[0]["model"] == "kimi-k2.6"
    assert calls[0]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in calls[0]


def test_k2_6_selector_rejects_an_unknown_returned_id():
    selection = FormulaSelection(
        kind="formula",
        selected=[FormulaSelectionItem(
            candidate_id="eq-fedcba9876543210", role="loss")],
    )
    selector = KimiFormulaSelector(
        "secret",
        post=lambda *a, **k: FakeKimiResponse(_kimi_payload(selection)),
        sleep=lambda _: None, request_interval=0,
    )
    with pytest.raises(ValueError, match="desconhecido"):
        selector.select(PAPER, [FORMULA])


def test_kimi_judge_parses_only_the_structured_message_content():
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        payload = _kimi_payload()
        payload["choices"][0]["message"]["reasoning_content"] = "nao e JSON"
        return FakeKimiResponse(payload)

    result = KimiJudge("secret", post=post, sleep=lambda _: None,
                       request_interval=0).judge_one(PAPER)
    assert result.familia == "quantizacao"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_kimi_judge_uses_the_configured_regional_endpoint():
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return FakeKimiResponse(_kimi_payload())

    KimiJudge("secret", post=post, sleep=lambda _: None, request_interval=0,
              base_url="https://api.moonshot.cn/v1/").judge_one(PAPER)
    assert calls == ["https://api.moonshot.cn/v1/chat/completions"]


def test_kimi_retries_a_rate_limit_using_retry_after():
    responses = [
        FakeKimiResponse({}, status_code=429, headers={"Retry-After": "7"}),
        FakeKimiResponse(_kimi_payload()),
    ]
    sleeps = []
    judge = KimiJudge("secret", post=lambda *a, **k: responses.pop(0),
                      sleep=sleeps.append, request_interval=0)
    assert judge.judge_one(PAPER).pratica == "testar"
    assert sleeps == [7.0]


def test_kimi_judge_all_keeps_good_results_when_one_paper_fails(caplog):
    other = Paper(arxiv_id="2508.22222", title="Other", abstract="A",
                  authors=[], categories=["cs.LG"], published="2026-08-20")
    responses = [FakeKimiResponse(_kimi_payload()),
                 FakeKimiResponse({}, status_code=400)]
    judge = KimiJudge("secret", post=lambda *a, **k: responses.pop(0),
                      sleep=lambda _: None, request_interval=0)
    with caplog.at_level("WARNING", logger="radar.judge"):
        result = judge.judge_all([PAPER, other])
    assert set(result) == {PAPER.arxiv_id}
    assert other.arxiv_id in caplog.text





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


def test_custom_id_satisfies_the_batch_api_pattern():
    """O Batch API exige ^[a-zA-Z0-9_-]{1,64}$ e recusa o lote INTEIRO com 400
    se um id nao casar. arXiv IDs modernos tem ponto, que nao esta na classe.
    Descoberto por requisicao real: nenhum teste com SDK falso pega isto."""
    import re
    from radar.judge import para_custom_id
    assert re.match(r"^[a-zA-Z0-9_-]{1,64}$", para_custom_id("2608.26581"))
    assert "." not in para_custom_id("2608.26581")


def test_custom_id_round_trips_back_to_the_arxiv_id():
    from radar.judge import de_custom_id, para_custom_id
    for pid in ("2608.26581", "2210.17323", "2305.14314"):
        assert de_custom_id(para_custom_id(pid)) == pid


def test_an_arxiv_id_that_cannot_become_a_custom_id_raises_early():
    """Melhor falhar na construcao, com o id no erro, do que levar 400 no lote
    inteiro sem saber qual paper causou."""
    import pytest as _pytest
    from radar.judge import para_custom_id
    with _pytest.raises(ValueError, match="custom_id"):
        para_custom_id("hep-th/9901001")


def test_batch_requests_are_keyed_by_the_papers_own_id_not_by_position():
    """O custom_id deriva do paper, nunca da posicao -- resultados de lote
    chegam fora de ordem e indexar por posicao colaria o julgamento de um
    paper em outro.

    O id vai SANITIZADO: o Batch API exige ^[a-zA-Z0-9_-]{1,64}$ e recusa o
    lote inteiro se um ponto passar. A volta acontece em collect_batch_results.
    """
    from radar.judge import build_batch_requests, de_custom_id
    papers = [PAPER, Paper(arxiv_id="2508.22222", title="T2", abstract="A2",
                           authors=[], categories=["cs.LG"], published="2026-08-21")]
    requests = build_batch_requests(papers, model="claude-opus-5")
    ids = [r["custom_id"] for r in requests]
    assert ids == ["2508_11111", "2508_22222"]
    assert [de_custom_id(i) for i in ids] == [p.arxiv_id for p in papers]
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
                        '{"technique":"%s","familia":"cache_kv","pratica":"testar",'
                        '"ganho_eixo":"nenhum","ganho_texto":"",'
                        '"resumo":"R","porque":"P"}' % tech})()]})()})()

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


def test_a_judgment_with_an_invalid_familia_is_logged_not_swallowed(caplog):
    from radar.judge import collect_batch_results
    payload = ('{"technique":"T","familia":"nao_existe","pratica":"testar",'
               '"ganho_eixo":"nenhum","ganho_texto":"","resumo":"R","porque":"P"}')
    with caplog.at_level("WARNING", logger="radar.judge"):
        out = collect_batch_results([_sucesso_com_texto("2508.55555", payload)])
    assert out == {}
    assert "2508.55555" in caplog.text


# --- Tarefa 5 do plano do segundo escopo ---

def test_o_schema_cobre_exatamente_a_taxonomia():
    """Se alguem adicionar familia em models.py e esquecer do judge, o modelo
    nunca consegue emitir o valor novo e o campo morre calado."""
    from radar.models import FAMILIAS
    campo = JudgmentSchema.model_fields["familia"]
    assert set(campo.annotation.__args__) == FAMILIAS


def test_o_schema_cobre_exatamente_as_praticas_e_os_eixos():
    from radar.models import GANHO_EIXOS, PRATICAS
    assert set(JudgmentSchema.model_fields["pratica"].annotation.__args__) == PRATICAS
    assert set(JudgmentSchema.model_fields["ganho_eixo"].annotation.__args__) == GANHO_EIXOS


def test_o_schema_nao_pergunta_mais_de_hardware():
    """runs_on_3090 respondeu `sim_com_ressalva` em 566 de 1088 papers no seed
    de 2026-08-29. Um eixo cuja resposta modal e "mais ou menos" nao separa
    nada e custa um campo de saida estruturada em todo julgamento."""
    assert "runs_on_3090" not in JudgmentSchema.model_fields


def test_o_prompt_descreve_o_leitor_e_nao_a_placa():
    texto = build_prompt(PAPER)
    assert "public llm api" in texto.lower()
    assert "no provider internals" in texto.lower()
    assert "3090" not in texto
    assert "RTX" not in texto


def test_o_prompt_pede_as_tres_perguntas_do_resumo():
    """Resumo que nao diz custo nem trade-off e propaganda, e propaganda e o
    que um radar anti-hype nao pode produzir."""
    texto = build_prompt(PAPER).lower()
    for exigencia in ("replaces", "costs", "fail"):
        assert exigencia in texto


def test_o_campo_de_pratica_diz_o_criterio_ao_modelo():
    """O Literal restringe o token; e a descricao que diz qual criterio usar.
    Este e o veredito que o leitor le."""
    campo = JudgmentSchema.model_json_schema()["properties"]["pratica"]
    for criterio in ("adotar", "public-endpoint", "custom hardware"):
        assert criterio in campo["description"]


def test_o_campo_de_fator_ensina_a_normalizacao():
    """A regra mais facil de errar: pontos percentuais NAO sao razao."""
    campo = JudgmentSchema.model_json_schema()["properties"]["ganho_fator"]
    assert "2.5" in campo["description"]      # o exemplo de 1/0.4
    assert "null" in campo["description"].lower()
