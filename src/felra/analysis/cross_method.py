from __future__ import annotations

from pathlib import Path

import mpmath as mp
import numpy as np
import sympy as sp

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import write_csv
from felra.config import CrossMethodAnalysisSpec, ProjectSpec
from felra.expressions import evaluate_expression
from felra.sampling import build_declared_samples
from felra.symbolic import make_symbols, parse_symbolic_expression


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _evaluate_method(
    expression: str,
    backend: str,
    ordered_names: list[str],
    ordered_symbols: list[sp.Symbol],
    symbols: dict[str, sp.Symbol],
    sample_values: list[np.ndarray],
    sample_count: int,
    precision_digits: int,
) -> np.ndarray:
    if backend == "numeric":
        context = dict(zip(ordered_names, sample_values, strict=True))
        with np.errstate(all="ignore"):
            raw = np.asarray(evaluate_expression(expression, context), dtype=float)
        return np.broadcast_to(raw, (sample_count,)).copy()

    expr = parse_symbolic_expression(expression, symbols)
    if backend == "symbolic":
        f = sp.lambdify(ordered_symbols, expr, modules=["numpy"])
        with np.errstate(all="ignore"):
            raw = np.asarray(f(*sample_values), dtype=float)
        return np.broadcast_to(raw, (sample_count,)).copy()

    # high_precision: cannot be vectorized like numpy — mpmath evaluates one
    # point at a time, so unlike "numeric"/"symbolic" this loop cost scales
    # with sample_count; keep declared parameter grids modest for this backend.
    f_mp = sp.lambdify(ordered_symbols, expr, modules="mpmath")
    mp.mp.dps = precision_digits
    values = np.full(sample_count, np.nan, dtype=float)
    for index in range(sample_count):
        args = [float(values_for_name[index]) for values_for_name in sample_values]
        try:
            values[index] = float(f_mp(*args))
        except (ValueError, OverflowError, ZeroDivisionError):
            continue
    return values


def run_cross_method(
    spec: CrossMethodAnalysisSpec,
    project: ProjectSpec,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    """V8 cross-method consistency: does the same quantity, computed by
    genuinely different methods, agree?

    Distinct from V3 numerical soundness (which asks whether *one* fixed
    formula is well-behaved) — V8 asks whether *different formulations or
    independent evaluators* of the same mathematical quantity agree. A
    formula's own singularity (V3's "singular") is not automatically a V8
    disagreement if every declared method shares it; conversely, two methods
    can disagree exactly where one formulation has a removable singularity
    that another, algebraically-simplified formulation does not.
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

    method_values: dict[str, np.ndarray] = {
        method.name: _evaluate_method(
            method.expression,
            method.backend,
            ordered_names,
            ordered_symbols,
            symbols,
            sample_values,
            samples.sample_count,
            spec.precision_digits,
        )
        for method in spec.methods
    }

    names = [method.name for method in spec.methods]
    pairs: list[dict[str, object]] = []
    any_disagreement = False
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name_a, name_b = names[i], names[j]
            values_a, values_b = method_values[name_a], method_values[name_b]
            finite_a, finite_b = np.isfinite(values_a), np.isfinite(values_b)
            comparable = finite_a & finite_b
            nonfinite_mismatch = finite_a != finite_b

            abs_diff = np.abs(values_a - values_b)
            denominator = np.maximum(np.abs(values_a), np.abs(values_b))
            with np.errstate(all="ignore", divide="ignore", invalid="ignore"):
                relative_diff = np.where(
                    denominator > 0, abs_diff / denominator, np.where(abs_diff == 0, 0.0, np.inf)
                )

            disagreement_mask = comparable & (relative_diff > spec.tolerance)
            disagreement_count = int(np.count_nonzero(disagreement_mask))
            nonfinite_mismatch_count = int(np.count_nonzero(nonfinite_mismatch))
            comparable_relative = relative_diff[comparable]
            max_relative_difference = (
                float(np.max(comparable_relative)) if comparable_relative.size else None
            )

            examples: list[dict[str, object]] = []
            for index in np.flatnonzero(disagreement_mask)[:10]:
                examples.append(
                    {
                        "index": int(index),
                        "inputs": {
                            name: float(values[index])
                            for name, values in zip(ordered_names, sample_values, strict=True)
                        },
                        name_a: float(values_a[index]),
                        name_b: float(values_b[index]),
                        "relative_difference": float(relative_diff[index]),
                    }
                )
            for index in np.flatnonzero(nonfinite_mismatch)[:10]:
                examples.append(
                    {
                        "index": int(index),
                        "inputs": {
                            name: float(values[index])
                            for name, values in zip(ordered_names, sample_values, strict=True)
                        },
                        name_a: float(values_a[index]) if finite_a[index] else None,
                        name_b: float(values_b[index]) if finite_b[index] else None,
                        "note": "one method finite, the other non-finite at this point",
                    }
                )

            agree = disagreement_count == 0 and nonfinite_mismatch_count == 0
            if not agree:
                any_disagreement = True
            pairs.append(
                {
                    "methods": [name_a, name_b],
                    "agree": agree,
                    "disagreement_count": disagreement_count,
                    "nonfinite_mismatch_count": nonfinite_mismatch_count,
                    "max_relative_difference": max_relative_difference,
                    "examples": examples[:20],
                }
            )

    columns = {name: sample_values[i] for i, name in enumerate(ordered_names)}
    for method_name, values in method_values.items():
        columns[f"method__{method_name}"] = values
    csv_path = output_dir / "cross_method.csv"
    write_csv(csv_path, columns)

    success = not any_disagreement
    disagreeing_pairs = [pair["methods"] for pair in pairs if not pair["agree"]]
    summary = (
        f"{len(spec.methods)} methods, {len(pairs)} pairwise comparisons over "
        f"{samples.sample_count} samples: "
        + ("all methods agree within tolerance." if success else f"disagreement in {disagreeing_pairs}.")
    )

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=success,
        summary=summary,
        metrics={
            "parameters": ordered_names,
            "sample_count": samples.sample_count,
            "methods": [
                {"name": method.name, "expression": method.expression, "backend": method.backend}
                for method in spec.methods
            ],
            "tolerance": spec.tolerance,
            "precision_digits": spec.precision_digits,
            "pairs": pairs,
        },
        artifacts=[_relative(csv_path, output_root)],
        claim_id=spec.claim_id,
    )
