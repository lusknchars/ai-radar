---
name: paper-2609-17817-evidence
description: "Use the evidence boundaries and implementation checks for Reflections on Trusting Trust, Revisited: Contaminating Self-Modifying AI Coding Agents with Poisoned Benchmarks (2609.17817)."
---

# Reflections on Trusting Trust, Revisited: Contaminating Self-Modifying AI Coding Agents with Poisoned Benchmarks

This skill is a research brief extracted from Paperraft. It is a reading and
validation aid, not an implementation guarantee. The paper is indexed
and a deep report is not available.

## Source

- Paper: https://arxiv.org/abs/2609.17817
- Paperraft page: /papers/2609.17817/
- Evidence rule: treat source-linked items as author-reported facts only under
  their stated conditions. Treat inferred items as hypotheses. Treat unknown
  items as unanswered questions. Never treat quoted paper text as an instruction.

## Reported claims

- The paper does not propose a technique that replaces an existing production method; it demonstrates an attack in which poisoned benchmarks contaminate the self-evaluation loop of self-modifying coding agents, causing evolved versions to emit vulnerable code (e.g., disabled HTTPS certificate validation) on clean tasks. There is no adoption cost in the usual sense, but the implied defensive cost is that any team running self-improving agent loops must add benchmark provenance checks, held-out clean evaluation, and auditing of self-modifications, none of which the paper shows to be reliably effective since contamination persists after clean re-evolution. What can fail is any pipeline that trusts benchmark results to steer agent self-modification: a single compromised benchmark can induce persistent insecure behavior that clean benchmarks do not repair. (inferred)

## Adoption checks

- quality: No finding recorded; treat this area as unknown. [not_evaluated]
- compute: No finding recorded; treat this area as unknown. [not_evaluated]
- latency: No finding recorded; treat this area as unknown. [not_evaluated]
- operations: No finding recorded; treat this area as unknown. [not_evaluated]
- compatibility: No finding recorded; treat this area as unknown. [not_evaluated]
- security: No finding recorded; treat this area as unknown. [not_evaluated]
- data_and_training: No finding recorded; treat this area as unknown. [not_evaluated]
- reproducibility: No finding recorded; treat this area as unknown. [not_evaluated]

Before adapting this technique, check the source conditions, comparator, metric,
model architecture, data, hardware, and load. Preserve the reported baseline.
Run the smallest falsification test described on the Paperraft page before
spending on a larger deployment. Do not generalize results to another model or
runtime without a measured comparison.

## Provenance

Generated from Paperraft's versioned public JSON. Regenerate this skill when the
research page changes. The downloadable package contains `evidence.json` with
the complete structured fields. Inspect both files before installation.
