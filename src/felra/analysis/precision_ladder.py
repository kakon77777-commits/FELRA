"""The precision-ladder analysis type (addendum stage D, §18.2).

One expression, evaluated in Decimal at a rising precision, until the tail settles
or the declared ceiling is reached. The verdict is three-valued and `unstable` is
never a pass — 不把未穩定結果標記為通過.

Where the same expression can also be evaluated exactly in rationals, the true
error is reported alongside the ladder's own estimate. That is a *check on the
estimate*, not an input to it: a ladder that needed the exact answer would be
useless everywhere the exact answer is unavailable, which is everywhere it is
worth having.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from felra.analysis.models import AnalysisResult
from felra.config import PrecisionLadderAnalysisSpec
from felra.numeric_backends import (
    NumericBackendError,
    evaluate_arithmetic,
    exact_parse,
)
from felra.precision_ladder import bits_to_digits, run_ladder


def run_precision_ladder(
    spec: PrecisionLadderAnalysisSpec,
    *,
    output_dir: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    results: list[dict[str, Any]] = []
    statuses: list[str] = []

    for row in spec.points:
        env = {name: exact_parse(text) for name, text in row.items()}

        def evaluate(bits: int, _env=env) -> Fraction:
            return evaluate_arithmetic(
                spec.expression, _env, "decimal", decimal_prec=bits_to_digits(bits)
            )

        try:
            ladder = run_ladder(
                evaluate,
                initial_bits=spec.initial_precision_bits,
                strategy=spec.strategy,
                step_bits=spec.step_bits,
                max_bits=spec.max_precision_bits,
                consecutive_levels=spec.consecutive_levels,
                absolute_tolerance=Fraction(spec.absolute_tolerance),
                relative_tolerance=Fraction(spec.relative_tolerance),
            )
        except NumericBackendError as exc:
            warnings.append("point %r: %s" % (row, exc))
            continue

        payload = ladder.as_dict()
        payload["assignment"] = dict(row)

        # A check on the ladder's self-estimate, never an input to it.
        try:
            exact = evaluate_arithmetic(spec.expression, env, "rational")
            final = ladder.levels[-1].result
            true_error = abs(final - exact)
            estimate = ladder.levels[-1].estimated_accuracy
            payload["exact_reference_available"] = True
            payload["true_error_float"] = float(true_error)
            payload["estimate_bounds_true_error"] = (
                estimate is not None and true_error <= estimate
            )
        except NumericBackendError:
            payload["exact_reference_available"] = False

        results.append(payload)
        statuses.append(ladder.status)

    if not results:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            kind="precision_ladder",
            title=spec.title,
            success=False,
            summary="no point could be evaluated",
            claim_id=spec.claim_id,
            metrics={"expression": spec.expression, "points": []},
            warnings=warnings or ["no points evaluated"],
        )

    stable = all(status == "stable" for status in statuses)
    if "unstable" in statuses:
        warnings.append(
            "at least one point did not settle; an unstable result is not a pass"
        )
    if "exhausted" in statuses:
        warnings.append(
            "at least one point reached the declared precision ceiling without "
            "settling; that is a resource outcome, not evidence that the quantity "
            "fails to converge"
        )

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind="precision_ladder",
        title=spec.title,
        success=stable,
        summary="%d point(s): %s" % (
            len(results),
            ", ".join("%s=%d" % (s, statuses.count(s)) for s in sorted(set(statuses))),
        ),
        claim_id=spec.claim_id,
        metrics={
            "expression": spec.expression,
            "statuses": statuses,
            "all_stable": stable,
            "points": results,
            "note": (
                "`estimated_accuracy` is the ladder's own successive difference. "
                "Where an exact value exists it is reported as a check on that "
                "estimate, never as an input to it."
            ),
        },
        warnings=warnings,
    )
