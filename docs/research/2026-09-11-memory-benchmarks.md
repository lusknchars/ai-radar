# Memory benchmarks for the first GLM experiment

Research date: 2026-09-11. Sources are the original benchmark repositories, data, scoring code, and papers. This note defines the tests and proposes a small experiment. It does not verify a vendor's reported scores. No model inference, paid judging, or GPU rental was performed.

The recommended first memory experiment is a **40-question LoCoMo subset using two complete conversation histories**, with the same GLM-4.7-Flash model in every arm. This is inexpensive to prepare and inspect. Follow it with selected LongMemEval_S questions to test updates and temporal behavior, then larger BEAM histories if the system earns that investment.

## What the benchmark names mean

| Benchmark | Released evaluation material | Primary purpose | First small trial |
| --- | --- | --- | --- |
| LoCoMo | Ten selected long conversations with QA annotations | Remember facts and relationships across conversations | Two histories and 40 frozen questions |
| LongMemEval | 500 questions with Oracle, S, and M history variants | Extraction, multi-session reasoning, updates, time, abstention | Oracle diagnostic followed by the same selected S questions |
| BEAM | 100 conversations and 2,000 probes at four history lengths | Broader memory behavior as histories grow | One or two 128K histories after smaller tests |

Source details and scoring differences follow. These trial sizes are our recommendations, not official benchmark splits.

## LoCoMo

The current release contains ten conversations in `data/locomo10.json`. It replaced an earlier 50-conversation release with a selected set intended to retain long histories and better annotations. Data includes session timestamps, dialog IDs, questions, category labels, and evidence references. It also includes generated observations and session summaries. Images themselves are not redistributed, although URLs and captions are present. [Original repository](https://github.com/snap-research/locomo)

Direct inspection of the pinned JSON found 1,986 questions. Category counts are 282 multi-hop, 321 temporal, 96 open-domain, 841 single-hop, and 446 adversarial. Excluding adversarial questions leaves 1,540; a result on that subset has a different denominator. Counts were computed from the source JSON, not copied from a vendor report. [Pinned dataset](https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json)

The original QA scorer uses normalized, stemmed token F1 for single-hop, temporal, and open-domain questions, with a multi-answer variation for multi-hop. Adversarial questions use phrase matching for an answer that says information is unavailable. This is materially different from binary correctness assigned by an LLM judge. The scorer also sets its retrieval-recall output to one when usable context evidence is absent; an adapter must mark such recall as unavailable instead of treating that default as a measured retrieval result. [Pinned scoring code](https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/task_eval/evaluation.py)

Practical caveats: token overlap can penalize valid paraphrases, and the adversarial phrase rule can accept an answer that also contains a fabricated claim. We should retain the original metric for compatibility and independently review the small trial's answers. Keep per-category results visible. A memory system may improve recall while becoming less willing to abstain.

## LongMemEval

The repository releases 500 questions testing five abilities. S histories are approximately 115K Llama-3 tokens and 40 sessions; M histories contain roughly 500 sessions. Oracle contains only the evidence sessions. These are history variants of the question collection, not interchangeable difficulty levels or separate train/test partitions. The September 2025 cleaned release fixes interfering history content, so the dataset revision matters. [Original repository and variant definitions](https://github.com/xiaowu0162/LongMemEval)

Data carries question type, question date, session timestamps, answer-session IDs, and per-turn answer labels. Those labels enable retrieval diagnostics but must be withheld from the system being tested. The same README now links a separate LongMemEval-V2 release. Specify the original cleaned benchmark when comparing with an unspecified "LongMemEval" claim. [Pinned data schema and release notices](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/README.md)

The official answer evaluator asks a model for binary correctness with category-specific instructions. Temporal grading tolerates off-by-one time counts; preference grading need not require every rubric point. Knowledge-update grading accepts older information alongside the required update. The script iterates over supplied predictions, so AI Radar must separately check that every planned question has exactly one valid result. Otherwise an incomplete file can produce a misleading average. Keep judge model, prompt, and raw verdict with each score. [Pinned evaluator](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py)

A cheap Oracle run can diagnose whether GLM answers correctly when relevant material is provided. It cannot establish that a memory system finds the material. For retrieval testing, use the full S history for each selected question and ingest it chronologically. Truncating the history or retaining only gold evidence changes the test.

## BEAM

BEAM has 20 conversations at 128K tokens, 35 at 500K, 35 at 1M, and ten at 10M. Its ten abilities cover abstention, contradictions, event order, extraction, instructions, updates, multi-session reasoning, preferences, summarization, and temporal reasoning. The original repository provides pre-generated data and separate generation, answering, and evaluation stages. The 10M data is distributed separately. These sizes describe stored conversation histories; they do not require feeding the entire history into one model request when evaluating retrieval memory. [Original BEAM repository](https://github.com/mohammadtavakoli78/BEAM)

The paper selects two probes per ability per conversation. Most abilities use atomic rubric criteria scored by an LLM as zero, one-half, or one, then averaged. Event ordering uses an LLM to align events before an order-sensitive metric. The conversations are generated; human reviewers validate probes and inspect sampled portions of the long histories rather than every turn. These details limit what a high score proves about real users. [BEAM paper, sections 2.4 and B.2](https://arxiv.org/html/2510.27246v2)

Implementation detail worth recording: the event-order code multiplies normalized Kendall tau-b by event F1, and also emits a separate rubric-judge score. A reported overall result must identify which field was aggregated. The code can make several judge calls for one answer because it grades individual rubric items and aligns event pairs. [Pinned metric implementation](https://github.com/mohammadtavakoli78/BEAM/blob/b2da22eac88bb0874c64665f13457eb99835774a/src/evaluation/compute_metrics.py)

The evaluation runner accepts conversation-index ranges and result-file filters. A small subset is feasible, but reducing the number of questions does not remove the cost of ingesting a complete long history. Start with 128K and measure ingestion before proposing 1M or 10M. [Evaluation runner](https://github.com/mohammadtavakoli78/BEAM/blob/b2da22eac88bb0874c64665f13457eb99835774a/src/evaluation/run_evaluation.py)

## Proposed first GLM-4.7-Flash memory test

1. Pin LoCoMo at `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`. Use conversations `conv-26` and `conv-41`. Both contain all five question categories, verified by inspecting the data. Deterministically select four questions per category per conversation, giving 40 total. Freeze IDs before generating answers. Keep the other eight conversations out of tuning.
2. Ingest only the raw conversation, timestamps, and speaker identity. Keep QA answers, evidence IDs, annotated event summaries, and generated memory artifacts outside the runtime input. Retain image captions only if the chosen text-only protocol explicitly includes them in every arm.
3. Compare a timestamped raw-chunk retrieval baseline against one memory-layer candidate. Keep GLM revision, quantization, inference engine, prompt format, response-token limit, and retrieved-context budget fixed. A recent-history-only arm can be an additional diagnostic; it is too weak to be the sole comparator.
4. Build each conversation's memory before showing evaluation questions. Use separate stores for each conversation and arm. Freeze the store during QA so earlier benchmark questions and answers cannot teach later ones. Record ingestion and query phases separately.
5. Save answers and retrieved source IDs. Report original category metrics and independent human correctness review for all 40 answers. Repeat generation with the same declared seeds across arms. These correlated questions from two histories are a smoke test, not a reliable estimate across users.
6. Record memory-building tokens and time, extraction-model calls, embedding work, storage, query retrieval time, generation time, and failed attempts. Amortize ingestion at several declared query counts instead of presenting query-only cost as the total.

For the next stage, preselect 20 questions from the cleaned LongMemEval_S release, covering all declared types and abstention. Run the Oracle version of those IDs only as a diagnostic, then evaluate the S histories with all distractors retained. Passing the Oracle diagnostic while failing S points toward a memory or retrieval problem; failure in both requires inspecting generation and grading too. Reserve a larger untouched set for a later claim.

## Minimum information required beside any score

- Dataset release, variant, included categories, frozen IDs, and completed/planned counts.
- Answering model, memory method, extraction model, embedding model, retrieval budget, and history-ingestion policy.
- Exact metric, judge model and prompt where applicable, aggregation method, and uncertainty.
- Query cost and total ingestion-plus-query cost, with latency and failed cases.

LoCoMo F1, LongMemEval judged correctness, and BEAM rubric/order scores have different meanings. A number such as 92.5 on one cannot be ranked against 94.4 on another without the protocol. None of these benchmark scores alone establishes lower production cost or reliable behavior for a particular SaaS workload.
