"""Cross-backend consistency over numeric ontologies (addendum stage C, §18.3).

Distinct from v1.0.0's `cross_method`, and the distinction is the point:

* `cross_method` asks **do different formulations of the same quantity agree** —
  `(x²−1)/(x−1)` against `x+1`.
* `cross_backend` asks **do different numeric ontologies evaluating the same
  formulation agree** — float64 against Decimal against Rational.

The first finds algebra errors; the second finds representation errors, and they
fail on different inputs. `(0.1 + 0.2) − 0.3` has one formulation and three
answers.

§18.3's acceptance is three-valued, not two: exact / within tolerance /
inconsistent. "Agrees to 1e-12" and "is the same number" are different facts, and
only the first is what a tolerance comparison can establish. A run that reports
`exact` is what the `exact_verified` rung of the evidence ladder rests on, so
collapsing the two would let a tolerance result climb a rung it did not reach.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Any

from felra.analysis.models import AnalysisResult
from felra.config import CrossBackendAnalysisSpec
from felra.numeric_backends import (
    NumericBackendError,
    agreement_class,
    exact_parse,
    evaluate_arithmetic,
)


def run_cross_backend(
    spec: CrossBackendAnalysisSpec,
    *,
    output_dir: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    # `Fraction(x)` is already exact for a float; the `limit_denominator(10**30)`
    # that used to be here silently collapsed any tolerance below 1e-30 to ZERO,
    # so a project declaring `tolerance: 1e-38` was quietly given a strict exact
    # comparison. Found by declaring exactly that on the Collatz anchor project
    # and getting `inconsistent` where the measured error was 3e-41.
    tolerance = Fraction(spec.tolerance)

    points: list[dict[str, Any]] = []
    pair_counts: dict[str, dict[str, int]] = {
        "%s|%s" % pair: {cls: 0 for cls in ("exact", "within_tolerance", "inconsistent")}
        for pair in combinations(spec.backends, 2)
    }
    float64_sourced = False
    errors: list[str] = []

    for row in spec.points:
        try:
            env = {name: exact_parse(text) for name, text in row.items()}
        except NumericBackendError as exc:
            errors.append("point %r: %s" % (row, exc))
            continue
        float64_sourced = float64_sourced or any(v.source_was_float64 for v in env.values())

        values: dict[str, Fraction] = {}
        for backend in spec.backends:
            try:
                values[backend] = evaluate_arithmetic(
                    spec.expression, env, backend, decimal_prec=spec.decimal_prec
                )
            except NumericBackendError as exc:
                errors.append("%s at %r: %s" % (backend, row, exc))
        if len(values) != len(spec.backends):
            continue

        matrix: dict[str, str] = {}
        for a, b in combinations(spec.backends, 2):
            cls = agreement_class(values[a], values[b], tolerance)
            matrix["%s|%s" % (a, b)] = cls
            pair_counts["%s|%s" % (a, b)][cls] += 1
        points.append(
            {
                "assignment": dict(row),
                "values": {k: "%d/%d" % (v.numerator, v.denominator)
                           for k, v in values.items()},
                "values_float": {k: float(v) for k, v in values.items()},
                "agreement": matrix,
            }
        )

    if errors:
        warnings.extend(errors[:5])

    all_exact = bool(points) and all(
        cls == "exact"
        for point in points
        for cls in point["agreement"].values()
    )
    any_inconsistent = any(
        cls == "inconsistent"
        for point in points
        for cls in point["agreement"].values()
    )

    if float64_sourced:
        warnings.append(
            "at least one input arrived as a float64 rather than an exact string, "
            "so an `exact` agreement here is agreement about an already-rounded "
            "value (addendum §9: a high-precision copy of a float64 is not a "
            "high-accuracy result)"
        )
    if all_exact and not float64_sourced:
        exactness = "exact_on_every_point"
    elif any_inconsistent:
        exactness = "inconsistent_somewhere"
    else:
        exactness = "within_tolerance_only"

    success = bool(points) and not any_inconsistent and not errors
    summary = "%d point(s) across %s → %s" % (
        len(points), ", ".join(spec.backends), exactness
    )

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind="cross_backend",
        title=spec.title,
        success=success,
        summary=summary,
        claim_id=spec.claim_id,
        metrics={
            "expression": spec.expression,
            "backends": list(spec.backends),
            "tolerance": spec.tolerance,
            "decimal_prec": spec.decimal_prec,
            "points_compared": len(points),
            "difference_matrix": pair_counts,
            "points": points[: spec.report_points],
            "exactness": exactness,
            "any_input_was_float64": float64_sourced,
            "errors": errors,
            "note": (
                "`exact` means the two ontologies produced the same rational "
                "number; `within_tolerance` means they did not. Only the first "
                "supports the evidence ladder's `exact_verified` rung."
            ),
        },
        warnings=warnings,
    )
