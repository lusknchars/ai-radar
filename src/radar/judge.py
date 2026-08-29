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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import Judgment, Paper

_log = logging.getLogger(__name__)

BATCH_POLL_SECONDS = 30
BATCH_TIMEOUT_SECONDS = 45 * 60   # um cron diario que espera mais que isso ja falhou

HARDWARE_BRIEF = (
    "A maquina alvo tem uma NVIDIA RTX 3090: arquitetura Ampere GA102, 24 GB de "
    "VRAM, 936 GB/s de banda de memoria, PCIe 4.0, e SEM unidades FP8. Tecnicas "
    "que dependem de FP8, de multiplas GPUs, ou de mais de 24 GB nao rodam nela."
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


class JudgmentSchema(BaseModel):
    # extra="forbid" e o que faz o Pydantic emitir `additionalProperties: false`
    # no schema. O contrato de saida estruturada exige esse campo em todo objeto
    # (spec secao 5); sem ele a API rejeita o lote inteiro, `collect_batch_results`
    # devolve {} e todo paper do dia vira `sem_julgamento`.
    model_config = ConfigDict(extra="forbid")

    technique: str = Field(description="Rotulo curto da tecnica, ate 8 palavras")
    summary: str = Field(description="UMA frase dizendo o que a tecnica faz")
    runs_on_3090: Literal["sim", "sim_com_ressalva", "nao"] = Field(
        description="'sim' se a tecnica roda na 3090 como descrita; "
                    "'sim_com_ressalva' se roda com perda, adaptacao ou modelo "
                    "menor; 'nao' se depende de FP8, de multiplas GPUs ou de "
                    "mais de 24 GB. O Literal restringe o token, e esta "
                    "descricao diz ao modelo qual criterio usar -- este campo e "
                    "o veredito que o usuario le.")
    rationale: str = Field(description="Uma linha justificando o veredito de hardware")


def build_prompt(paper: Paper) -> str:
    return (
        f"{HARDWARE_BRIEF}\n\n"
        f"Paper (arXiv {paper.arxiv_id}):\n"
        f"Titulo: {paper.title}\n"
        f"Resumo: {paper.abstract}\n\n"
        f"Resuma a tecnica em uma frase e diga se ela roda nessa maquina. "
        f"Escreva em portugues, sem emoji, sem adjetivo promocional."
    )


def _to_domain(schema: JudgmentSchema) -> Judgment:
    return Judgment(technique=schema.technique, summary=schema.summary,
                    runs_on_3090=schema.runs_on_3090, rationale=schema.rationale)


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
