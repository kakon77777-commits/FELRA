from __future__ import annotations

from pathlib import Path

import mpmath as mp
import numpy as np
import sympy as sp

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import write_csv
from felra.config import NumericalSoundnessAnalysisSpec, ProjectSpec
from felra.sampling import build_declared_samples
from felra.symbolic import make_symbols, parse_symbolic_expression


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def run_numerical_soundness(
    spec: NumericalSoundnessAnalysisSpec,
    project: ProjectSpec,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    """V3 numerical soundness: overflow/singularity/ill-conditioning/precision loss.

    A single symbolic parse of ``expression`` (the same safe parser V2 symbolic
    verification uses) drives all three whitepaper-suggested methods from a
    single source of truth, rather than three independently-reimplemented
    evaluators that could subtly disagree with each other:

    1. overflow / NaN — a fast numpy-vectorized evaluation over the declared
       domain, checked for non-finite output;
    2. condition number — the exact symbolic derivative (not a finite-difference
       estimate) gives kappa_i(x) = |x_i * df/dx_i / f(x)| at every sample;
    3. precision loss — the float64 evaluation compared against an arbitrary-
       precision (mpmath) reference on a bounded subset of points, since
       arbitrary-precision evaluation cannot be vectorized the way numpy can.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    parameters = {name: project.parameters[name] for name in spec.parameters}
    samples = build_declared_samples(
        parameters,
        max_evaluations=project.execution.max_evaluations,
        seed=project.execution.seed,
    )
    ordered_names = list(spec.parameters)
    sample_values = [np.asarray(samples.variables[name], dtype=float) for name in ordered_names]

    symbols = make_symbols(tuple(ordered_names), {})
    ordered_symbols = [symbols[name] for name in ordered_names]
    expr = parse_symbolic_expression(spec.expression, symbols)
    partials = [sp.diff(expr, symbol) for symbol in ordered_symbols]

    f_numpy = sp.lambdify(ordered_symbols, expr, modules=["numpy"])
    partial_numpy = [sp.lambdify(ordered_symbols, partial, modules=["numpy"]) for partial in partials]

    with np.errstate(all="ignore"):
        f_values = np.broadcast_to(
            np.asarray(f_numpy(*sample_values), dtype=float), (samples.sample_count,)
        ).copy()
        partial_values = [
            np.broadcast_to(
                np.asarray(fn(*sample_values), dtype=float), (samples.sample_count,)
            ).copy()
            for fn in partial_numpy
        ]

    finite_mask = np.isfinite(f_values) & np.all(
        [np.isfinite(values) for values in partial_values], axis=0
    )
    nonfinite_count = int(samples.sample_count - np.count_nonzero(finite_mask))

    singular_mask = finite_mask & (f_values == 0.0)
    singular_count = int(np.count_nonzero(singular_mask))

    condition_domain_mask = finite_mask & ~singular_mask
    with np.errstate(all="ignore", divide="ignore", invalid="ignore"):
        condition_components = np.stack(
            [
                np.abs(sample_values[index] * partial_values[index] / f_values)
                for index in range(len(ordered_names))
            ],
            axis=0,
        )
    condition_number = np.max(condition_components, axis=0)
    condition_number = np.where(condition_domain_mask, condition_number, np.nan)
    ill_conditioned_mask = condition_domain_mask & (condition_number > spec.condition_threshold)
    ill_conditioned_count = int(np.count_nonzero(ill_conditioned_mask))
    finite_condition_values = condition_number[condition_domain_mask]

    f_mpmath = sp.lambdify(ordered_symbols, expr, modules="mpmath")
    domain_indices = np.flatnonzero(condition_domain_mask)
    if domain_indices.size > spec.precision_sample_limit:
        positions = np.linspace(0, domain_indices.size - 1, spec.precision_sample_limit).astype(int)
        checkable_indices = domain_indices[positions]
    else:
        checkable_indices = domain_indices
    mp.mp.dps = spec.precision_digits
    relative_errors: list[float] = []
    precision_loss_examples: list[dict[str, object]] = []
    for index in checkable_indices:
        args = [float(values[index]) for values in sample_values]
        try:
            high_precision_value = f_mpmath(*args)
            reference = float(high_precision_value)
        except (ValueError, OverflowError, ZeroDivisionError):
            continue
        if reference == 0.0 or not np.isfinite(reference):
            continue
        relative_error = abs(f_values[index] - reference) / abs(reference)
        relative_errors.append(relative_error)
        if relative_error > spec.relative_error_threshold and len(precision_loss_examples) < 20:
            precision_loss_examples.append(
                {
                    "index": int(index),
                    "inputs": {name: float(values[index]) for name, values in zip(
                        ordered_names, sample_values, strict=True
                    )},
                    "float64_value": float(f_values[index]),
                    "high_precision_value": reference,
                    "relative_error": relative_error,
                }
            )
    precision_checked_count = len(relative_errors)
    precision_loss_count = len(precision_loss_examples)
    max_relative_error = max(relative_errors) if relative_errors else None

    ill_conditioned_examples = []
    for index in np.flatnonzero(ill_conditioned_mask)[:20]:
        ill_conditioned_examples.append(
            {
                "index": int(index),
                "inputs": {
                    name: float(values[index]) for name, values in zip(
                        ordered_names, sample_values, strict=True
                    )
                },
                "condition_number": float(condition_number[index]),
            }
        )

    columns = {name: sample_values[i] for i, name in enumerate(ordered_names)}
    columns["value"] = f_values
    columns["condition_number"] = condition_number
    columns["finite"] = finite_mask
    columns["singular"] = singular_mask
    csv_path = output_dir / "numerical_soundness.csv"
    write_csv(csv_path, columns)

    success = nonfinite_count == 0 and ill_conditioned_count == 0 and precision_loss_count == 0
    summary_parts = [
        f"{samples.sample_count} samples",
        f"{nonfinite_count} non-finite",
        f"{singular_count} singular (f(x)=0)",
        f"{ill_conditioned_count} ill-conditioned (kappa > {spec.condition_threshold:g})",
        f"{precision_loss_count}/{precision_checked_count} precision-loss "
        f"(relative error > {spec.relative_error_threshold:g})",
    ]
    summary = "Numerical soundness: " + "; ".join(summary_parts) + "."

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=success,
        summary=summary,
        metrics={
            "expression": spec.expression,
            "parameters": ordered_names,
            "sample_count": samples.sample_count,
            "strategy": samples.strategy,
            "nonfinite_count": nonfinite_count,
            "singular_count": singular_count,
            "condition_threshold": spec.condition_threshold,
            "ill_conditioned_count": ill_conditioned_count,
            "max_condition_number": (
                float(np.max(finite_condition_values))
                if finite_condition_values.size
                else None
            ),
            "mean_condition_number": (
                float(np.mean(finite_condition_values))
                if finite_condition_values.size
                else None
            ),
            "precision_digits": spec.precision_digits,
            "precision_checked_count": precision_checked_count,
            "relative_error_threshold": spec.relative_error_threshold,
            "precision_loss_count": precision_loss_count,
            "max_relative_error": max_relative_error,
            "ill_conditioned_examples": ill_conditioned_examples,
            "precision_loss_examples": precision_loss_examples,
        },
        artifacts=[_relative(csv_path, output_root)],
        claim_id=spec.claim_id,
    )
