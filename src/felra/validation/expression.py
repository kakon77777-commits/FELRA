from __future__ import annotations

from typing import Any

import numpy as np

from felra.expressions import evaluate_expression
from felra.models import ValidationResult
from felra.sampling import SampleSet


def validate_expression_predicate(
    expression: str,
    samples: SampleSet,
    *,
    check_name: str,
    max_counterexamples: int = 20,
) -> ValidationResult:
    """Evaluate one declarative claim over a traceable sample set."""

    try:
        raw_outcome = evaluate_expression(expression, samples.variables)
        outcome = np.asarray(raw_outcome, dtype=bool)
        if outcome.ndim == 0:
            outcome = np.full(samples.sample_count, bool(outcome), dtype=bool)
        else:
            outcome = outcome.reshape(-1)
    except Exception as exc:
        return ValidationResult(
            check_name=check_name,
            passed=False,
            summary="Expression evaluation failed before the declared domain was tested.",
            metrics={
                "tested_count": 0,
                "strategy": samples.strategy,
                "error": f"{type(exc).__name__}: {exc}",
            },
            counterexamples=({"error": f"{type(exc).__name__}: {exc}"},),
        )

    if outcome.size != samples.sample_count:
        return ValidationResult(
            check_name=check_name,
            passed=False,
            summary="Expression output shape does not match the sample domain.",
            metrics={
                "tested_count": 0,
                "expected_count": samples.sample_count,
                "actual_count": int(outcome.size),
                "strategy": samples.strategy,
            },
        )

    failed_indices = np.flatnonzero(~outcome)
    counterexamples: list[dict[str, Any]] = []
    for index in failed_indices[:max_counterexamples]:
        counterexamples.append(
            {
                "index": int(index),
                "inputs": {
                    name: np.asarray(values)[index].item()
                    for name, values in samples.variables.items()
                },
                "outcome": False,
            }
        )

    passed_count = int(np.count_nonzero(outcome))
    tested_count = int(outcome.size)
    passed = failed_indices.size == 0
    return ValidationResult(
        check_name=check_name,
        passed=passed,
        summary=(
            f"Claim held for all {tested_count} evaluated points."
            if passed
            else f"Claim failed at {failed_indices.size} of {tested_count} evaluated points."
        ),
        metrics={
            "tested_count": tested_count,
            "passed_count": passed_count,
            "failed_count": int(failed_indices.size),
            "pass_rate": passed_count / tested_count,
            "strategy": samples.strategy,
            "exhaustive_declared_grid": samples.exhaustive_declared_grid,
            "finite_domain": True,
        },
        counterexamples=tuple(counterexamples),
    )
