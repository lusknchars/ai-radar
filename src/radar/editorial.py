"""Reading prompts for incomplete briefs, never findings about a paper.

These authored questions are selected by research family. Rendering them does
not populate the evidence model, claim a reproduction, or call an LLM.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadingPrompts:
    inspect: str
    compare: str
    ask: str


DEFAULT_PROMPTS = ReadingPrompts(
    "Which assumptions does the proposed method need, and where might your workload violate them?",
    "Identify the baseline, metric, dataset, and experimental settings in the paper. Which can you match?",
    "What implementation and evaluation artifacts are available, and what would you need to supply?",
)

FAMILY_PROMPTS = {
    "quantizacao": ReadingPrompts(
        "Which layers and values are quantized? Check whether calibration data overlaps the evaluation set.",
        "Can you compare the original and quantized model on identical prompts, hardware, and output limits?",
        "Do memory savings and task quality hold at your context length and target concurrency?",
    ),
    "cache_kv": ReadingPrompts(
        "Which tokens or cache entries are retained, compressed, or discarded? Look for tests of lost information.",
        "Can you keep prompts and decoding settings fixed while measuring cache size, latency, and answer quality?",
        "Does the evaluation cover long conversations and questions about information introduced early?",
    ),
    "decodificacao_especulativa": ReadingPrompts(
        "How are proposals verified, and what happens after rejection? Check the assumptions behind any quality guarantee.",
        "Can you compare the same target model with speculation off and on, including proposal and verification time?",
        "Which draft model or prediction heads are needed, and how does acceptance change with the workload?",
    ),
    "memoria_e_contexto": ReadingPrompts(
        "How are memories written, retrieved, updated, and deleted? Look for stale or contradictory information.",
        "Can you compare full context, simple retrieval, and the memory layer using the same questions and context budget?",
        "Does the cost include memory extraction and maintenance as well as answer generation?",
    ),
    "avaliacao_de_agente": ReadingPrompts(
        "Who grades the outputs? Inspect the rubric, disagreements, and whether the evaluator sees the method's identity.",
        "Can you apply the same tasks and rubric to the baseline and candidate, then review disagreements by hand?",
        "Are the results stable across prompts, languages, and task categories relevant to your product?",
    ),
    "serving_e_batching": ReadingPrompts(
        "What arrival pattern, concurrency, and context lengths drive the reported result?",
        "Can you replay one request trace and compare throughput, tail latency, failures, and total cost?",
        "Does the method still meet your latency target during bursts and with mixed request lengths?",
    ),
    "recuperacao_e_rag": ReadingPrompts(
        "Which retrieval and reranking stages change? Check whether supporting evidence is actually retrieved.",
        "Can you freeze the corpus and questions, then compare answer quality and citation support against simple retrieval?",
        "What happens when the answer is missing from the corpus or the indexed content changes?",
    ),
    "kernels_e_atencao": ReadingPrompts(
        "Which tensor shapes, precision settings, and hardware support the reported kernel result?",
        "Can you compare against the existing implementation on the same inputs, checking numerical error and end-to-end time?",
        "Are the gains limited to a microbenchmark, or do they appear in the complete model workload?",
    ),
    "agentes_de_codigo": ReadingPrompts(
        "Does the evaluation use held-out repositories and tests the agent cannot modify?",
        "Can you run both agents against the same repository snapshot, tool permissions, and time budget?",
        "How many tasks pass independent tests, and what is the cost per accepted change?",
    ),
}

EXPOSURE_PROMPTS = {
    "quality": "Which tasks improve, and which regress against the baseline?",
    "compute": "What memory, hardware, and total compute does the complete method require?",
    "latency": "Are startup time, typical response time, and slow requests measured separately?",
    "operations": "What must be monitored, maintained, and rolled back?",
    "compatibility": "Does the implementation support your model, runtime, and hardware?",
    "security": "What new data access, permissions, or trust boundaries does it introduce?",
    "data_and_training": "What data preparation or training is required, and is it included in the cost?",
    "reproducibility": "Are code, versions, inputs, and evaluation scripts available?",
}


def reading_prompts(family: str) -> ReadingPrompts:
    return FAMILY_PROMPTS.get(family, DEFAULT_PROMPTS)
