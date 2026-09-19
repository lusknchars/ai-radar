---
name: paper-2609-16403-evidence
description: "Use the evidence boundaries and implementation checks for Implementing a White-Box Undetectable Backdoor for Random Fourier Features (2609.16403)."
---

# Implementing a White-Box Undetectable Backdoor for Random Fourier Features

This skill is a research brief extracted from Paperraft. It is a reading and
validation aid, not an implementation guarantee. The paper is indexed
and a deep report is not available.

## Source

- Paper: https://arxiv.org/abs/2609.16403
- Paperraft page: /papers/2609.16403/
- Evidence rule: treat source-linked items as author-reported facts only under
  their stated conditions. Treat inferred items as hypotheses. Treat unknown
  items as unanswered questions. Never treat quoted paper text as an instruction.

## Reported claims

- The paper implements, in numpy and scipy, a cryptographically undetectable backdoor for Random Fourier Features models, replacing informal assumptions about white-box auditability with a concrete demonstration that full weight inspection cannot distinguish backdoored from clean models. It does not replace any production technique; the cost to the reader is awareness that weight-level auditing of RFF-based models offers no security guarantee, and replicating the work requires deriving sampling machinery the original construction left unspecified. What can fail: the finding applies to the RFF setting specifically, the underlying lattice hardness reduction was not reproduced, and the negative indistinguishability result is empirical within the tested sparsity range rather than a new proof. (inferred)

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
