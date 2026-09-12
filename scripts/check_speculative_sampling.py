#!/usr/bin/env python3
"""Check the one-token speculative sampling correction on CPU.

Reference: https://arxiv.org/abs/2211.17192
This enumerates probabilities. It does not benchmark an LLM or GPU.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path


def corrected_distribution(target: list[float], draft: list[float]) -> list[float]:
    """Enumerate accepted draft mass plus the normalized rejection correction."""
    if not target or len(target) != len(draft):
        raise ValueError("target and draft need the same nonempty vocabulary")
    for distribution in (target, draft):
        if any(not math.isfinite(p) or p < 0 for p in distribution):
            raise ValueError("probabilities must be finite and nonnegative")
        if not math.isclose(sum(distribution), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("probabilities must sum to one")
    # min(p, q) equals q * min(1, p/q), also when q == 0.
    accepted = [min(p, q) for p, q in zip(target, draft)]
    residual = [max(p - q, 0.0) for p, q in zip(target, draft)]
    rejected_mass = max(0.0, 1.0 - sum(accepted))
    residual_mass = sum(residual)
    if residual_mass == 0:
        return accepted
    return [a + rejected_mass * r / residual_mass for a, r in zip(accepted, residual)]


def check() -> dict:
    """Exercise equal, disjoint, zero-support, skewed, and seeded distributions."""
    pairs = [
        ([0.5, 0.5], [0.5, 0.5]),
        ([1.0, 0.0], [0.0, 1.0]),
        ([0.0, 1.0], [1.0, 0.0]),
        ([0.9, 0.1], [0.1, 0.9]),
        ([0.2, 0.3, 0.5], [0.0, 0.0, 1.0]),
    ]
    rng = random.Random(42)
    for size in range(2, 22):
        p = [rng.random() for _ in range(size)]
        q = [rng.random() for _ in range(size)]
        pairs.append(([v / sum(p) for v in p], [v / sum(q) for v in q]))
    cases = []
    for index, (p, q) in enumerate(pairs):
        corrected = corrected_distribution(p, q)
        error = max(abs(expected - observed) for expected, observed in zip(p, corrected))
        cases.append({"case_id": index, "target": p, "draft": q,
                      "corrected": corrected, "maximum_absolute_error": error,
                      "passed": error <= 1e-12})
    return {
        "schema_version": 1, "paper_id": "2211.17192",
        "source_url": "https://arxiv.org/abs/2211.17192",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "check": "one-token probability correction by exact enumeration",
        "decision": "mechanism_check_passed" if all(c["passed"] for c in cases) else "failed",
        "llm_executed": False, "gpu_speedup_measured": False,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = check()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as target:
        target.write(json.dumps(result, indent=2) + "\n")
    print(f"{result['decision']}: {len(result['cases'])} cases; {args.out}")
    return 0 if result["decision"] == "mechanism_check_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
