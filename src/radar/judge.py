"""Camada de julgamento.

O radar (3 itens) usa chamada normal -- volume trivial, resultado imediato.
O feed usa o Batch API: metade do custo, e latencia e irrelevante num cron.

Resultados do batch chegam FORA DE ORDEM. Indexar por custom_id, nunca por
posicao.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Literal, TypeVar

import httpx

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import Judgment, Paper

_log = logging.getLogger(__name__)

BATCH_POLL_SECONDS = 30
BATCH_TIMEOUT_SECONDS = 45 * 60   # um cron diario que espera mais que isso ja falhou

# Substitui o HARDWARE_BRIEF. O produto deixou de ser bancada de reproducao e
# virou jornal: o que importa nao e se a tecnica roda numa placa especifica, e
# se o leitor deve adotar, testar, observar ou ignorar.
LEITOR_BRIEF = (
    "O leitor e um engenheiro de AI/ML com INFRA PEQUENA: uma GPU de 24 GB ou "
    "APIs de terceiros, sem cluster, sem treino de modelo base, orcamento de "
    "nuvem baixo, time pequeno. Ele decide o que adotar nas praticas do dia a "
    "dia, nao o que pesquisar."
)

# Tupla literal, nao `tuple(FAMILIAS)`: frozenset nao tem ordem estavel, e um
# schema JSON que muda de ordem entre execucoes invalida cache de prompt. O
# teste `test_o_schema_cobre_exatamente_a_taxonomia` garante que ela bate com
# FAMILIAS -- e o que impede as duas listas de divergirem em silencio.
_FAMILIAS = (
    "quantizacao", "cache_kv", "decodificacao_especulativa",
    "esparsidade_e_poda", "kernels_e_atencao", "serving_e_batching",
    "arquitetura_eficiente", "destilacao", "treino_eficiente",
    "uso_de_ferramenta", "memoria_e_contexto", "planejamento_e_decomposicao",
    "orquestracao_multiagente", "avaliacao_de_agente", "recuperacao_de_falha",
    "agentes_de_codigo", "seguranca_e_guardrails", "recuperacao_e_rag",
    "outro",
)

# Spec secao 5: thinking adaptativo com esforco baixo -- a tarefa e curta e bem
# definida. Os dois precisam ser explicitos: no Opus 5 o thinking vem ligado por
# padrao e o esforco default e `high`, entao um julgamento de uma frase raciocina
# muito acima do orcado.
THINKING = {"type": "adaptive"}
EFFORT = "low"

# Tokens de thinking contam como saida e contra o max_tokens. Com 1024 um
# julgamento podia ser cortado no meio do JSON, e o resultado truncado sumia
# calado no except de collect_batch_results. O teto e limite de seguranca, nao
# orcamento: so o que for realmente gerado e cobrado, e a saida util aqui e de
# umas 200 palavras.
MAX_TOKENS = 8192
KIMI_DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
KIMI_MAX_RETRIES = 4
StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class JudgmentSchema(BaseModel):
    # extra="forbid" e o que faz o Pydantic emitir `additionalProperties: false`
    # no schema. O contrato de saida estruturada exige esse campo em todo objeto
    # (spec secao 5); sem ele a API rejeita o lote inteiro, `collect_batch_results`
    # devolve {} e todo paper do dia vira `sem_julgamento`.
    model_config = ConfigDict(extra="forbid")

    technique: str = Field(description="Rotulo curto da tecnica, ate 8 palavras")
    familia: Literal[_FAMILIAS] = Field(
        description="A familia da tecnica. Use 'outro' apenas quando nenhuma "
                    "das dezoito couber de verdade -- encaixar a forca destroi "
                    "a agregacao, que e para o que este campo existe.")
    pratica: Literal["adotar", "testar", "observar", "nao_aplica"] = Field(
        description="O que o leitor faz com isso. 'adotar': da para usar ja, "
                    "com infra pequena, ganho claro, sem pre-requisito exotico. "
                    "'testar': plausivel com infra pequena, mas o ganho depende "
                    "de validacao no caso concreto. 'observar': importa, e exige "
                    "escala, hardware ou dado que ele nao tem. 'nao_aplica': "
                    "fora do que ele faz.")
    ganho_eixo: Literal["velocidade", "memoria", "custo", "qualidade", "nenhum"] = Field(
        description="Em que dimensao o paper alega melhorar. 'nenhum' quando o "
                    "paper nao faz alegacao quantificada -- resposta legitima e "
                    "frequente, nao use as outras por educacao.")
    ganho_fator: float | None = Field(
        default=None,
        description="O ganho como FATOR MULTIPLICATIVO de melhora, quando e so "
                    "quando o paper permite. '2.3x mais rapido' vira 2.3. "
                    "'reduz memoria em 60%' vira 2.5, que e 1/0.4. "
                    "'+3 pontos de acuracia' NAO vira fator: e null, porque "
                    "pontos percentuais nao sao razao. Com ganho_eixo='nenhum', "
                    "sempre null.")
    ganho_texto: str = Field(
        description="A alegacao como o paper a faz, em texto curto, para que o "
                    "numero seja auditavel ate a frase que o originou. String "
                    "vazia quando nao ha alegacao.")
    resumo: str = Field(
        description="Ate TRES frases, nesta ordem: o que a tecnica substitui, o "
                    "que ela custa (memoria, latencia, complexidade ou qualidade "
                    "perdida), e o que quebra se o leitor adotar.")
    porque: str = Field(description="Uma linha justificando o veredito de pratica")


def build_prompt(paper: Paper) -> str:
    return (
        f"{LEITOR_BRIEF}\n\n"
        f"Paper (arXiv {paper.arxiv_id}):\n"
        f"Titulo: {paper.title}\n"
        f"Resumo: {paper.abstract}\n\n"
        f"Classifique a tecnica numa familia, diga o que o leitor faz com ela, "
        f"e extraia a alegacao de ganho se houver. No resumo diga o que ela "
        f"substitui, o que custa, e o que quebra. "
        f"Escreva em portugues, sem emoji, sem adjetivo promocional."
    )


def _to_domain(schema: JudgmentSchema) -> Judgment:
    return Judgment(
        technique=schema.technique, familia=schema.familia,
        pratica=schema.pratica, ganho_eixo=schema.ganho_eixo,
        ganho_fator=schema.ganho_fator, ganho_texto=schema.ganho_texto,
        resumo=schema.resumo, porque=schema.porque,
    )


class Judge:
    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    def judge_one(self, paper: Paper) -> Judgment:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": build_prompt(paper)}],
            thinking=THINKING,
            output_config={"effort": EFFORT},
            output_format=JudgmentSchema,
        )
        return _to_domain(response.parsed_output)


def build_kimi_request(paper: Paper, model: str) -> dict:
    """Corpo OpenAI-compatible aceito pelo endpoint da Moonshot."""
    return build_kimi_structured_request(
        messages=[{"role": "user", "content": build_prompt(paper)}],
        model=model,
        output_type=JudgmentSchema,
        schema_name="paper_judgment",
    )


def build_kimi_structured_request(
    *, messages: list[dict], model: str,
    output_type: type[BaseModel], schema_name: str,
) -> dict:
    """Monta uma chamada estruturada sem acoplar Kimi a um unico dominio."""
    return {
        "model": model,
        "max_completion_tokens": MAX_TOKENS,
        "reasoning_effort": EFFORT,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": output_type.model_json_schema(),
            },
        },
    }


class KimiJudge:
    """Julgador Kimi K3 com saida estrita e repeticao limitada.

    K3 nao participa do Batch API da Kimi. O adaptador usa Chat Completions e
    respeita um intervalo configuravel entre papers. A chave fica somente no
    header e nunca entra em logs ou checkpoints.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "kimi-k3",
        *,
        post=None,
        sleep=time.sleep,
        request_interval: float = 20.0,
        max_retries: int = KIMI_MAX_RETRIES,
        base_url: str = KIMI_DEFAULT_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("KIMI_API_KEY ausente")
        if request_interval < 0:
            raise ValueError("request_interval precisa ser >= 0")
        self._api_key = api_key
        self._model = model
        self._post_override = post
        self._http_client: httpx.Client | None = None
        self._sleep = sleep
        self._request_interval = request_interval
        self._max_retries = max_retries
        self._api_url = f"{base_url.rstrip('/')}/chat/completions"

    def judge_one(self, paper: Paper) -> Judgment:
        schema = self.parse_structured(
            messages=[{"role": "user", "content": build_prompt(paper)}],
            output_type=JudgmentSchema,
            schema_name="paper_judgment",
            subject=paper.arxiv_id,
        )
        return _to_domain(schema)

    def parse_structured(
        self, *, messages: list[dict], output_type: type[StructuredOutput],
        schema_name: str, subject: str,
    ) -> StructuredOutput:
        body = build_kimi_structured_request(
            messages=messages, model=self._model, output_type=output_type,
            schema_name=schema_name,
        )
        for attempt in range(self._max_retries):
            try:
                response = self._post(
                    self._api_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=120.0,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 == self._max_retries:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 2 ** attempt
                    except ValueError:
                        delay = 2 ** attempt
                    self._sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                return output_type.model_validate_json(content)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt + 1 == self._max_retries:
                    raise
                self._sleep(2 ** attempt)
            except (KeyError, IndexError, TypeError, ValidationError) as exc:
                if attempt + 1 == self._max_retries:
                    raise RuntimeError(
                        f"Kimi devolveu saida malformada para {subject}"
                    ) from exc
                self._sleep(2 ** attempt)
        raise RuntimeError("Kimi esgotou as tentativas sem devolver julgamento")

    def judge_all(self, papers: list[Paper]) -> dict[str, Judgment]:
        results: dict[str, Judgment] = {}
        try:
            for index, paper in enumerate(papers):
                if index:
                    self.wait_between_requests()
                try:
                    results[paper.arxiv_id] = self.judge_one(paper)
                except Exception as exc:
                    _log.warning("julgamento Kimi de %s falhou: %s", paper.arxiv_id, exc)
        finally:
            self.close()
        return results

    def wait_between_requests(self) -> None:
        self._sleep(self._request_interval)

    def _post(self, *args, **kwargs):
        if self._post_override is not None:
            return self._post_override(*args, **kwargs)
        if self._http_client is None:
            self._http_client = httpx.Client()
        return self._http_client.post(*args, **kwargs)

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None


_CUSTOM_ID_OK = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def para_custom_id(arxiv_id: str) -> str:
    """Converte um arXiv ID em custom_id valido para o Batch API.

    A API exige `^[a-zA-Z0-9_-]{1,64}$` e recusa a requisicao inteira com 400
    se algum id nao casar. arXiv IDs modernos sao `YYMM.NNNNN` -- tem um ponto,
    que nao esta na classe. Sem esta conversao TODO lote falha, e nenhum teste
    pega, porque todos falseiam o SDK.

    Ponto vira underscore. A volta e biunivoca porque o formato moderno so tem
    digitos e um unico ponto, e o filtro de escopo so traz categorias cs.*
    modernas.
    """
    convertido = arxiv_id.replace(".", "_")
    if not _CUSTOM_ID_OK.match(convertido):
        raise ValueError(
            f"arxiv_id {arxiv_id!r} nao vira um custom_id valido "
            f"({convertido!r}); o Batch API recusaria o lote inteiro"
        )
    return convertido


def de_custom_id(custom_id: str) -> str:
    """Volta do custom_id para o arXiv ID."""
    return custom_id.replace("_", ".")


def build_batch_requests(papers: list[Paper], model: str) -> list[dict]:
    """Devolve dicts para permanecer testavel sem o SDK instalado.

    O chamador converte em Request/MessageCreateParamsNonStreaming --
    ver submit_batch abaixo.
    """
    return [
        {
            "custom_id": para_custom_id(paper.arxiv_id),
            "params": {
                "model": model,
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": build_prompt(paper)}],
                "thinking": THINKING,
                "output_config": {
                    "effort": EFFORT,
                    "format": {
                        "type": "json_schema",
                        "schema": JudgmentSchema.model_json_schema(),
                    },
                },
            },
        }
        for paper in papers
    ]


def collect_batch_results(results) -> dict[str, Judgment]:
    """Indexa por custom_id. Resultados do batch chegam fora de ordem."""
    out: dict[str, Judgment] = {}
    for result in results:
        if result.result.type != "succeeded":
            continue
        message = result.result.message
        text = next((b.text for b in message.content if b.type == "text"), None)
        if not text:
            _log.warning("julgamento de %s veio sem bloco de texto", result.custom_id)
            continue
        try:
            out[de_custom_id(result.custom_id)] = _to_domain(JudgmentSchema(**json.loads(text)))
        except Exception as exc:
            # Um julgamento malformado nao derruba o lote, mas tambem nao pode
            # sumir calado: sem o custom_id no log, o paper aparece como
            # `sem_julgamento` no markdown e nao ha como saber qual quebrou.
            _log.warning("julgamento de %s descartado como malformado: %s",
                         result.custom_id, exc)
            continue
    return out


def wait_for_batch(
    client,
    batch_id: str,
    *,
    sleep=time.sleep,
    now=time.monotonic,
    timeout_seconds: float = BATCH_TIMEOUT_SECONDS,
    poll_seconds: float = BATCH_POLL_SECONDS,
) -> bool:
    """Espera o lote terminar. True se terminou; False se estourou o prazo ou
    a consulta de status falhou.

    O laco e LIMITADO de proposito. Sem prazo, um lote que nunca termina prende
    o workflow ate o timeout do runner -- horas queimadas sem produzir digest
    nenhum. Desistir em 45 minutos e devolver False deixa o pipeline seguir e
    contar todos os papers como `sem_julgamento`, motivo que aparece na secao
    de cortes do dia. Degradacao visivel vale mais que espera muda.

    `sleep` e `now` entram por injecao para que o comportamento de prazo seja
    testavel sem esperar de verdade.
    """
    deadline = now() + timeout_seconds
    while True:
        try:
            status = client.messages.batches.retrieve(batch_id).processing_status
        except Exception:
            return False
        if status == "ended":
            return True
        if now() >= deadline:
            return False
        sleep(poll_seconds)


def submit_batch(client, papers: list[Paper], model: str):
    """Fio fino ate o SDK. Isolado aqui para o resto do modulo ficar testavel."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    return client.messages.batches.create(
        requests=[
            Request(custom_id=r["custom_id"],
                    params=MessageCreateParamsNonStreaming(**r["params"]))
            for r in build_batch_requests(papers, model)
        ]
    )
