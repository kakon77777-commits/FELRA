from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np

from felra.models import ValidationResult


def validate_predicate(
    predicate: Callable[[float], bool],
    samples: Iterable[float],
    *,
    check_name: str = "numerical_predicate",
    max_counterexamples: int = 20,
) -> ValidationResult:
    """Evaluate a Boolean predicate on a finite sample set.

    This is machine validation over the declared samples, not a universal proof.
    """

    values = np.asarray(list(samples), dtype=float)
    if values.size == 0:
        raise ValueError("samples must contain at least one value")

    counterexamples: list[dict[str, Any]] = []
    passed_count = 0

    for value in values:
        try:
            outcome = bool(predicate(float(value)))
        except Exception as exc:  # pragma: no cover - defensive evidence capture
            outcome = False
            counterexamples.append(
                {"input": float(value), "error": f"{type(exc).__name__}: {exc}"}
            )
        else:
            if not outcome:
                counterexamples.append({"input": float(value), "outcome": False})

        if outcome:
            passed_count += 1

        if len(counterexamples) >= max_counterexamples:
            break

    tested_count = int(values.size)
    pass_rate = passed_count / tested_count
    passed = not counterexamples and passed_count == tested_count

    return ValidationResult(
        check_name=check_name,
        passed=passed,
        summary=(
            f"Predicate held for {passed_count}/{tested_count} declared samples."
            if passed
            else "Predicate failed or errored within the declared sample domain."
        ),
        metrics={
            "tested_count": tested_count,
            "passed_count": passed_count,
            "pass_rate": pass_rate,
            "finite_domain": True,
        },
        counterexamples=tuple(counterexamples),
    )
