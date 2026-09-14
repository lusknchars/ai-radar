"""Editorial application guides, kept separate from extracted paper evidence.

Area plans are suggestions. Selected full-paper reviews are pinned to the PDF
and saved report they were checked against. No model calls or metric parsing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from .public_research import ResearchPage
    from .report import ReportDocument


class BuilderPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario: str = Field(min_length=1)
    change: str = Field(min_length=1)
    baseline: str = Field(min_length=1)
    steps: tuple[str, ...] = Field(min_length=3, max_length=6)
    measure: str = Field(min_length=1)
    decision: str = Field(min_length=1)


class BenchmarkReading(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    baseline_name: str = Field(min_length=1)
    method_name: str = Field(min_length=1)
    before: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    after: float = Field(ge=0, allow_inf_nan=False)
    unit: Literal["percent", "tokens/s", "tokens/step", "USD", "score"]
    scope: str = Field(min_length=1)
    caveat: str = Field(min_length=1)
    source_page: int = Field(ge=1)
    source_locator: str = Field(min_length=1)

    @model_validator(mode="after")
    def percentage_bounds(self):
        if self.unit == "percent" and any(
            value is not None and value > 100 for value in (self.before, self.after)
        ):
            raise ValueError("percentages use a 0–100 scale")
        return self

    def display(self, value: float | None) -> str:
        if value is None:
            return "Not compared"
        if self.unit == "USD":
            return f"${value:.2f}" if value == 0 or value >= .01 else f"${value:.6g}"
        return f"{value:g}{'%' if self.unit == 'percent' else ' ' + self.unit}"

    @property
    def difference(self) -> str:
        if self.before is None:
            return "No matched comparison"
        delta = self.after - self.before
        if self.unit == "percent":
            return f"{delta:+g} percentage points"
        absolute = f"{delta:+.6g}"
        if self.before == 0:
            return f"{absolute} {self.unit}; relative change undefined"
        relative = delta / self.before * 100
        return f"{absolute} {self.unit} ({relative:+.1f}%)"


class BuilderReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arxiv_id: str = Field(pattern=r"^\d{4}\.\d{4,5}$")
    source_url: str
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_at: date
    intro: str = Field(min_length=1, max_length=600)
    mechanism: str = Field(min_length=1)
    method_page: int = Field(ge=1)
    takeaway: str = Field(min_length=1)
    comparisons: tuple[BenchmarkReading, ...] = Field(min_length=1, max_length=4)
    plan: BuilderPlan

    @model_validator(mode="after")
    def versioned_source(self):
        if not re.fullmatch(
            rf"https://arxiv\.org/pdf/{re.escape(self.arxiv_id)}v[1-9]\d*",
            self.source_url,
        ):
            raise ValueError("builder review requires this paper's versioned PDF")
        return self


def report_digest(report: ReportDocument) -> str:
    return hashlib.sha256(json.dumps(
        report.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()


def apply_builder_review(
    page: ResearchPage, path: Path, report: ReportDocument | None,
) -> ResearchPage:
    if not path.exists():
        return page
    review = BuilderReview.model_validate_json(path.read_text(encoding="utf-8"))
    if review.arxiv_id != page.arxiv_id:
        raise ValueError("builder review belongs to a different paper")
    if (report is None or report.arxiv_id != page.arxiv_id
            or report.source.pdf_sha256 != review.pdf_sha256
            or report_digest(report) != review.report_sha256):
        logging.getLogger(__name__).warning(
            "Skipped stale builder review for %s; using area guidance", page.arxiv_id)
        return page
    pages = [review.method_page, *(item.source_page for item in review.comparisons)]
    if report.source.pages is None or max(pages) > report.source.pages:
        raise ValueError("builder review cites a page outside the source PDF")
    return page.model_copy(update={"builder_review": review, "builder_plan": review.plan})


# Each entry describes a possible product bottleneck, never a finding attributed
# to an unread paper. Unknown families deliberately keep the general plan.
_AREA_PLANS = {
    "quantizacao": (
        "A self-hosted assistant is too expensive because its model uses most of the GPU memory.",
        "Try the paper's supported lower-precision weights on a copy of your serving setup.",
        "The same model at its original precision, on the same GPU.",
        "Peak memory, task pass rate, latency, and total serving cost at the same context and load."),
    "cache_kv": (
        "Long customer conversations exhaust memory or limit concurrent requests.",
        "Change only the attention cache policy, after checking model and runtime support.",
        "The same model with its ordinary attention cache.",
        "Peak cache memory, long-context answer quality, first-token latency, and requests completed."),
    "decodificacao_especulativa": (
        "Your self-hosted model spends too long generating answers token by token.",
        "Check whether a compatible draft model and serving integration exist before renting compute.",
        "The same target with speculation off, then your existing drafter if you have one.",
        "Accepted draft length, tokens per second, tail latency, output quality, and total GPU cost."),
    "memoria_e_contexto": (
        "A support or data assistant repeats work across related customer requests.",
        "Try the paper's memory change in a replay of past tasks, with separate memory per customer.",
        "Your current memory pipeline plus a no-memory control using the same agent.",
        "Task success, stale memories, retrieval misses, response latency, and all memory maintenance costs."),
    "avaliacao_de_agente": (
        "An agent looks good in demos, but you cannot tell which product tasks it fails.",
        "Use the study's evaluation idea to inspect a small set of tasks with human-checked answers.",
        "Your current evaluator and a manually reviewed reference set.",
        "Agreement with human review, missed failures, false alarms, and evaluation cost per task."),
    "seguranca_e_guardrails": (
        "An agent reads external documents or tool responses that may contain malicious instructions.",
        "Replay attacks and legitimate lookalikes in an isolated copy of your agent workflow.",
        "Your existing checks with the same tasks, permissions, and tool responses.",
        "Successful attacks missed, legitimate actions blocked, detection delay, and review cost."),
    "serving_e_batching": (
        "Your inference service slows down when several customers send requests together.",
        "Replay a recorded request trace with only the proposed serving policy changed.",
        "Your current scheduler on the same model and hardware.",
        "Requests meeting your latency target, throughput, failures, and cost per successful request."),
    "recuperacao_e_rag": (
        "A product assistant retrieves plausible documents but gives unsupported answers.",
        "Change one retrieval or ranking step while keeping the document snapshot fixed.",
        "Your current retrieval pipeline with identical questions and answer model.",
        "Supported answers, retrieval misses, correct abstentions, index cost, and response latency."),
    "kernels_e_atencao": (
        "Profiling shows attention computation is a bottleneck in your self-hosted service.",
        "Check the supported GPU, tensor shapes, and precision, then replace only the relevant kernel.",
        "The existing kernel inside the same complete serving pipeline.",
        "Numerical differences, end-to-end latency, throughput, and memory at realistic shapes."),
    "agentes_de_codigo": (
        "Your coding assistant makes changes that still need substantial repair before merging.",
        "Try the technique on held-out issues from a repository with reliable tests.",
        "The same coding agent, repository snapshot, tools, and token budget.",
        "Correct patches, regression failures, human repair time, and total cost per accepted change."),
    "uso_de_ferramenta": (
        "An assistant chooses the wrong API or sends arguments your product cannot use.",
        "Apply the proposed tool-selection or argument-generation change in a sandbox.",
        "Your current agent with the same tool schemas and task budget.",
        "Correct completed actions, invalid calls, retries, latency, and cost per completed task."),
    "planejamento_e_decomposicao": (
        "A multi-step product task fails because the agent loses track of dependencies.",
        "Try the proposed planning step on tasks with checkable intermediate outcomes.",
        "The same agent solving the same tasks without the new planning step.",
        "Task completion, unnecessary steps, planning tokens, response time, and total cost."),
    "orquestracao_multiagente": (
        "A workflow needs specialist review, but extra agents may add more cost than useful work.",
        "Test the proposed division of work against a single-agent implementation.",
        "One agent with the same tools and an equal total token and time budget.",
        "Accepted outputs, coordination failures, wall-clock time, and total cost across all agents."),
    "recuperacao_de_falha": (
        "Tool errors or unavailable services cause your agent to abandon recoverable tasks.",
        "Inject repeatable tool failures and change only the recovery policy.",
        "Your current retry and fallback behavior under the same injected failures.",
        "Recovered tasks, duplicate side effects, retries, time to recovery, and total cost."),
    "esparsidade_e_poda": (
        "A self-hosted model uses more compute or memory than your workload can justify.",
        "Check for a usable pruned checkpoint and runtime support before attempting model surgery.",
        "The original unpruned model at the same precision, context, and load.",
        "Task quality, actual GPU memory, serving throughput, and preparation cost."),
    "arquitetura_eficiente": (
        "Your workload might fit a smaller or differently structured model.",
        "Check for available weights and a compatible runtime before planning a product trial.",
        "Your current model on identical held-out tasks and the same resource budget.",
        "Task success, latency, memory, context limits, and migration cost."),
    "destilacao": (
        "A narrow, repeated product task may not need your largest model.",
        "Check whether a released student model fits the task before generating training data.",
        "Your current model and an off-the-shelf small model on the same held-out tasks.",
        "Student quality, serving cost, teacher calls, training cost, and failures on unusual inputs."),
    "treino_eficiente": (
        "You already need task-specific training and want to reduce its memory or compute cost.",
        "Change only the training technique on a small controlled run after checking prerequisites.",
        "Your current training recipe with the same model, data split, and evaluation.",
        "Held-out quality, peak memory, training time, and full compute cost to the target quality."),
    "outro": (
        "Start with one repeated product task that has a measurable failure or cost.",
        "Read the methods and identify one change you can isolate in that workflow.",
        "Your current implementation on the same held-out tasks.",
        "Successful outcomes, response time, human rework, and total cost per successful task."),
}


def plan_for_family(family: str) -> BuilderPlan:
    scenario, change, baseline, measure = _AREA_PLANS.get(family, _AREA_PLANS["outro"])
    return BuilderPlan(
        scenario=scenario, change=change, baseline=baseline,
        steps=(
            "Locate the paper's implementation and check its license, model support, data needs, and hardware requirements. Stop here if you cannot obtain the required artifacts.",
            "Save a small set of representative product tasks and expected outcomes. Keep evaluation tasks out of any training or tuning, and choose quality and cost limits before running.",
            "Run the baseline and the proposed change on identical inputs. Keep other settings fixed and repeat paired runs to expose variation.",
            "Save per-task outputs, failures, timings, and all usage costs. Review regressions before expanding the test.",
        ),
        measure=measure,
        decision="Keep the change only if it meets your preselected quality and latency limits and improves the metric you care about after setup and operating costs. Otherwise retain the baseline. This is an exploration plan, not a validated recommendation.",
    )


def render_application_plan(page: ResearchPage) -> str:
    plan = page.builder_plan or plan_for_family(page.family)
    review = page.builder_review
    basis = "Paperraft interpretation of the full paper" if review else "Research-area suggestion; paper-specific feasibility is not established"
    readings = ""
    if review:
        readings = "\n## Read the benchmark correctly\n\n" + "\n\n".join(
            f"### {item.title}\n\n{item.definition}\n\n"
            f"{item.baseline_name}: {item.display(item.before)}. "
            f"{item.method_name}: {item.display(item.after)}. "
            f"Difference: {item.difference}.\n\n{item.scope}\n\n{item.caveat}\n\n"
            f"Source: {review.source_url}#page={item.source_page}, {item.source_locator}."
            for item in review.comparisons)
    return (
        f"# Try the idea: {page.title}\n\n{basis}. No Paperraft experiment has been run.\n\n"
        f"Paper: {review.source_url if review else page.source_url}\n\n"
        f"## Possible product use\n\n{plan.scenario}\n\n{plan.change}\n\n"
        f"## Baseline\n\n{plan.baseline}\n\n## First test\n\n"
        + "\n".join(f"{i}. {step}" for i, step in enumerate(plan.steps, 1))
        + f"\n\n## Measure\n\n{plan.measure}\n\n## Decision rule\n\n{plan.decision}\n"
        + readings
        + "\n\n## Record your result\n\n"
        "- Model and version:\n- Code revision and configuration:\n- Task set and split:\n"
        "- Hardware or API:\n- Run count and seed/order:\n- Quality and latency limits chosen before testing:\n"
        "- Baseline outputs and cost:\n- Changed outputs and cost:\n- Setup and maintenance cost:\n"
        "- Regressions and uncertainty:\n- Decision and rollback:\n\n"
        "Compare total cost per successful task, including failed attempts, retries, preparation, "
        "and maintenance. A benchmark percentage is not a prediction of savings for your product.\n"
    )
