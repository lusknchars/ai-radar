"""English labels for stable internal taxonomy and storage keys.

The pipeline keeps its original enum values so historical data remains valid.
Every public channel resolves those keys here before presenting them.
"""
from __future__ import annotations

FAMILY_LABELS = {
    "quantizacao": "quantization",
    "cache_kv": "KV cache",
    "decodificacao_especulativa": "speculative decoding",
    "esparsidade_e_poda": "sparsity and pruning",
    "kernels_e_atencao": "attention and kernels",
    "serving_e_batching": "serving and batching",
    "arquitetura_eficiente": "efficient architectures",
    "destilacao": "distillation",
    "treino_eficiente": "efficient training",
    "uso_de_ferramenta": "tool use",
    "memoria_e_contexto": "memory and context",
    "planejamento_e_decomposicao": "planning and decomposition",
    "orquestracao_multiagente": "multi-agent orchestration",
    "avaliacao_de_agente": "agent evaluation",
    "recuperacao_de_falha": "failure recovery",
    "agentes_de_codigo": "coding agents",
    "seguranca_e_guardrails": "safety and guardrails",
    "recuperacao_e_rag": "retrieval and RAG",
    "outro": "other",
}

PRACTICE_LABELS = {
    "adotar": "adopt",
    "testar": "test",
    "observar": "watch",
    "nao_aplica": "not applicable",
}

GAIN_AXIS_LABELS = {
    "velocidade": "speed",
    "memoria": "memory",
    "custo": "cost",
    "qualidade": "quality",
    "nenhum": "none",
}

INFRASTRUCTURE_LABELS = {
    "api_or_cpu": "API or CPU",
    "single_gpu_24gb": "1 GPU, up to 24 GB",
    "single_gpu_48_80gb": "1 GPU, 48 to 80 GB",
    "multi_gpu": "multiple GPUs",
    "cluster": "cluster",
    "custom_hardware": "specialized hardware",
    "unknown": "not reported",
}

INFRASTRUCTURE_BASIS_LABELS = {
    "explicit": "stated in the paper",
    "inferred": "inferred from requirements",
    "unknown": "not reported",
}

TRAINING_LABELS = {
    "none": "none",
    "inference_only": "inference only",
    "fine_tuning": "fine-tuning",
    "train_from_scratch": "training from scratch",
    "unknown": "not reported",
}

TECHNICAL_CORE_LABELS = {
    "formula": "formula-based core",
    "algorithm": "algorithmic core",
    "system": "system-level core",
    "evaluation_protocol": "evaluation protocol",
    "concept": "conceptual core",
    "none": "not yet classified",
}

FORMULA_ROLE_LABELS = {
    "baseline": "baseline",
    "proposed_method": "proposed method",
    "loss": "loss function",
    "metric": "metric",
    "complexity": "complexity",
}

FORMULA_STATUS_LABELS = {
    "concept_only": "concept identified; notation not verified",
    "not_applicable": "the technical core does not depend on a new formula",
    "extraction_failed": "notation could not be extracted safely",
}

SOFTWARE_SETUP_LABELS = {
    "standard_python": "standard Python",
    "containerized": "containerized",
    "custom_runtime": "custom runtime",
    "custom_cuda_kernel": "custom CUDA kernel",
    "distributed_stack": "distributed stack",
    "specialized_simulator": "specialized simulator",
    "unknown": "not reported",
}

CUT_LABELS = {
    "abaixo_do_piso": "below the signal threshold",
    "fora_de_escopo": "outside the research scope",
    "ja_conhecido": "already indexed",
    "ja_entregue": "already published",
    "ja_estourou": "above the attention threshold",
    "reconsulta_abaixo_do_piso": "rechecked: below the signal threshold",
    "reconsulta_fora_do_top3": "rechecked: outside the delivery set",
    "reconsulta_ja_estourou": "rechecked: above the attention threshold",
    "reconsulta_sem_julgamento": "rechecked: analysis unavailable",
    "reconsulta_sinal_indisponivel": "rechecked: signal unavailable",
    "sem_julgamento": "analysis unavailable",
    "sinal_indisponivel": "signal unavailable",
    "termo_falhou": "search term failed",
}

AUTHORSHIP_REASON_LABELS = {
    "mais_antigo_e_mais_estrelado": "oldest and most-starred repository",
    "sobrenome": "author surname matched the repository owner",
}


def public_label(labels: dict[str, str], value: str) -> str:
    """Resolve a stable key without leaking underscore-separated labels."""
    return labels.get(value, value.replace("_", " "))
