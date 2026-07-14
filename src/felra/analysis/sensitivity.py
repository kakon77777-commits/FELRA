from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import (
    clamp_to_domain,
    default_context,
    scalar_expression,
    write_csv,
)
from felra.config import ProjectSpec, SensitivityAnalysisSpec
from felra.figures import FigureFactory
from felra.sampling import parameter_axis


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _neighbors(
    value: float | int,
    project: ProjectSpec,
    parameter: str,
    relative_step: float,
    absolute_step: float | None,
) -> tuple[float | int, float | int]:
    spec = project.parameters[parameter]
    axis = parameter_axis(spec)
    if spec.values:
        values = np.sort(axis.astype(float))
        lower = values[values < float(value)]
        upper = values[values > float(value)]
        minus = lower[-1] if lower.size else float(value)
        plus = upper[0] if upper.size else float(value)
    else:
        assert spec.minimum is not None and spec.maximum is not None
        span = float(spec.maximum) - float(spec.minimum)
        step = absolute_step if absolute_step is not None else relative_step * max(span, 1.0)
        if spec.kind == "int":
            step = max(1.0, round(step))
        minus = float(value) - step
        plus = float(value) + step

    return clamp_to_domain(minus, spec), clamp_to_domain(plus, spec)


def run_sensitivity(
    spec: SensitivityAnalysisSpec,
    project: ProjectSpec,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = spec.parameters or tuple(project.parameters)
    baseline = default_context(project.parameters)
    for name, value in spec.baseline.items():
        baseline[name] = clamp_to_domain(value, project.parameters[name])

    base_value = scalar_expression(spec.expression, baseline)
    rows: list[dict[str, Any]] = []
    epsilon = np.finfo(float).eps

    for name in selected:
        parameter_spec = project.parameters[name]
        minus, plus = _neighbors(
            baseline[name],
            project,
            name,
            spec.relative_step,
            spec.absolute_step,
        )
        minus_context = dict(baseline)
        plus_context = dict(baseline)
        minus_context[name] = minus
        plus_context[name] = plus
        minus_value = scalar_expression(spec.expression, minus_context)
        plus_value = scalar_expression(spec.expression, plus_context)
        denominator = float(plus) - float(minus)
        derivative = np.nan if denominator == 0 else (plus_value - minus_value) / denominator

        axis = parameter_axis(parameter_spec)
        minimum_context = dict(baseline)
        maximum_context = dict(baseline)
        minimum_context[name] = axis[0].item()
        maximum_context[name] = axis[-1].item()
        minimum_value = scalar_expression(spec.expression, minimum_context)
        maximum_value = scalar_expression(spec.expression, maximum_context)
        domain_span = float(axis[-1]) - float(axis[0])
        normalized = (
            abs(derivative) * abs(domain_span) / max(abs(base_value), epsilon)
            if np.isfinite(derivative)
            else np.nan
        )
        elasticity = (
            derivative * float(baseline[name]) / max(abs(base_value), epsilon)
            if np.isfinite(derivative)
            else np.nan
        )
        rows.append(
            {
                "parameter": name,
                "baseline": baseline[name],
                "minus": minus,
                "plus": plus,
                "f_minus": minus_value,
                "f_baseline": base_value,
                "f_plus": plus_value,
                "derivative": derivative,
                "elasticity": elasticity,
                "domain_effect": maximum_value - minimum_value,
                "normalized_abs_sensitivity": normalized,
            }
        )

    csv_path = output_dir / "sensitivity.csv"
    write_csv(
        csv_path,
        {key: [row[key] for row in rows] for key in rows[0]},
    )

    figure_path = FigureFactory(output_dir / "figures").bar_plot(
        [str(row["parameter"]) for row in rows],
        [float(row["normalized_abs_sensitivity"]) for row in rows],
        title=spec.title,
        xlabel="Parameter",
        ylabel="Normalized absolute sensitivity",
        filename="sensitivity.png",
    )

    finite_count = int(
        np.count_nonzero([np.isfinite(float(row["derivative"])) for row in rows])
    )
    ranking = sorted(
        rows,
        key=lambda row: (
            -float(row["normalized_abs_sensitivity"])
            if np.isfinite(float(row["normalized_abs_sensitivity"]))
            else float("inf")
        ),
    )
    success = np.isfinite(base_value) and finite_count > 0
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=bool(success),
        summary=(
            f"Computed local finite-difference sensitivity for {len(rows)} parameters."
            if success
            else "Sensitivity analysis did not produce a finite derivative."
        ),
        metrics={
            "expression": spec.expression,
            "baseline": baseline,
            "baseline_value": base_value,
            "relative_step": spec.relative_step,
            "absolute_step": spec.absolute_step,
            "finite_derivative_count": finite_count,
            "ranking": [
                {
                    "parameter": row["parameter"],
                    "normalized_abs_sensitivity": row["normalized_abs_sensitivity"],
                }
                for row in ranking
            ],
        },
        artifacts=[_relative(csv_path, output_root), _relative(figure_path, output_root)],
        figures=[_relative(figure_path, output_root)],
        claim_id=spec.claim_id,
    )
