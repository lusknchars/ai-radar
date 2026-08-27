"""Camada de julgamento.

O radar (3 itens) usa chamada normal -- volume trivial, resultado imediato.
O feed usa o Batch API: metade do custo, e latencia e irrelevante num cron.

Resultados do batch chegam FORA DE ORDEM. Indexar por custom_id, nunca por
posicao.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from .models import Judgment, Paper

HARDWARE_BRIEF = (
    "A maquina alvo tem uma NVIDIA RTX 3090: arquitetura Ampere GA102, 24 GB de "
    "VRAM, 936 GB/s de banda de memoria, PCIe 4.0, e SEM unidades FP8. Tecnicas "
    "que dependem de FP8, de multiplas GPUs, ou de mais de 24 GB nao rodam nela."
)

MAX_TOKENS = 1024


class JudgmentSchema(BaseModel):
    technique: str = Field(description="Rotulo curto da tecnica, ate 8 palavras")
    summary: str = Field(description="UMA frase dizendo o que a tecnica faz")
    runs_on_3090: Literal["sim", "sim_com_ressalva", "nao"]
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
            output_format=JudgmentSchema,
        )
        return _to_domain(response.parsed_output)


def build_batch_requests(papers: list[Paper], model: str) -> list[dict]:
    """Devolve dicts para permanecer testavel sem o SDK instalado.

    O chamador converte em Request/MessageCreateParamsNonStreaming --
    ver submit_batch abaixo.
    """
    return [
        {
            "custom_id": paper.arxiv_id,
            "params": {
                "model": model,
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": build_prompt(paper)}],
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": JudgmentSchema.model_json_schema(),
                    }
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
            continue
        try:
            out[result.custom_id] = _to_domain(JudgmentSchema(**json.loads(text)))
        except Exception:
            continue          # julgamento malformado nao derruba o lote
    return out


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
