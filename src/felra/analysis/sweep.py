from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import (
    broadcast_expression,
    clamp_to_domain,
    default_context,
    sample_columns,
    write_csv,
    write_json,
)
from felra.config import ProjectSpec, SweepAnalysisSpec
from felra.figures import FigureFactory
from felra.sampling import build_declared_samples, parameter_axis


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def run_sweep(
    spec: SweepAnalysisSpec,
    project: ProjectSpec,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = spec.parameters or tuple(project.parameters)
    selected_specs = {name: project.parameters[name] for name in selected}
    samples = build_declared_samples(
        selected_specs,
        max_evaluations=project.execution.max_evaluations,
        seed=project.execution.seed,
    )
    fixed = default_context(project.parameters)
    for name, value in spec.fixed.items():
        fixed[name] = clamp_to_domain(value, project.parameters[name])
    context: dict[str, Any] = dict(fixed)
    context.update(samples.variables)
    objective = broadcast_expression(spec.objective, context, samples.sample_count)
    finite = np.isfinite(objective)

    columns = sample_columns(samples)
    columns.update({"objective": objective, "finite": finite})
    csv_path = output_dir / "sweep.csv"
    write_csv(csv_path, columns)

    finite_indices = np.flatnonzero(finite)
    if spec.goal == "minimize":
        order = finite_indices[np.argsort(objective[finite_indices], kind="stable")]
    else:
        order = finite_indices[np.argsort(-objective[finite_indices], kind="stable")]
    top_indices = order[: spec.top_k]
    top_points = [
        {
            "rank": rank,
            "parameters": {
                name: np.asarray(samples.variables[name])[index].item() for name in selected
            },
            "objective": float(objective[index]),
        }
        for rank, index in enumerate(top_indices, start=1)
    ]
    top_path = output_dir / "best_points.json"
    write_json(top_path, {"goal": spec.goal, "points": top_points})

    artifacts = [_relative(csv_path, output_root), _relative(top_path, output_root)]
    figures: list[str] = []
    factory = FigureFactory(output_dir / "figures")
    if len(selected) == 1 and finite_indices.size:
        name = selected[0]
        x = np.asarray(samples.variables[name], dtype=float)[finite]
        y = objective[finite]
        sort_order = np.argsort(x, kind="stable")
        if samples.exhaustive_declared_grid:
            path = factory.line_plot(
                x[sort_order],
                y[sort_order],
                title=spec.title,
                xlabel=name,
                ylabel=spec.objective,
                filename="sweep_curve.png",
            )
        else:
            path = factory.scatter_plot(
                x,
                y,
                title=spec.title,
                xlabel=name,
                ylabel=spec.objective,
                filename="sweep_scatter.png",
            )
        figures.append(_relative(path, output_root))
    elif len(selected) == 2 and samples.exhaustive_declared_grid:
        x_name, y_name = selected
        x_axis = parameter_axis(project.parameters[x_name])
        y_axis = parameter_axis(project.parameters[y_name])
        z = objective.reshape(len(x_axis), len(y_axis)).T
        heatmap = factory.heatmap(
            x_axis,
            y_axis,
            z,
            title=f"{spec.title} — heatmap",
            xlabel=x_name,
            ylabel=y_name,
            filename="sweep_heatmap.png",
        )
        contour = factory.contour_plot(
            x_axis,
            y_axis,
            z,
            title=f"{spec.title} — contour",
            xlabel=x_name,
            ylabel=y_name,
            filename="sweep_contour.png",
        )
        figures.extend([_relative(heatmap, output_root), _relative(contour, output_root)])
    elif finite_indices.size:
        histogram = factory.histogram(
            objective[finite],
            title=f"{spec.title} — objective distribution",
            xlabel=spec.objective,
            ylabel="Frequency",
            bins=40,
            filename="objective_histogram.png",
        )
        figures.append(_relative(histogram, output_root))
    artifacts.extend(figures)

    best = top_points[0] if top_points else None
    success = bool(finite_indices.size)
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=success,
        summary=(
            (
                f"Evaluated {samples.sample_count} sweep points; "
                f"best objective={best['objective']:.6g}."
            )
            if best
            else "Parameter sweep produced no finite objective values."
        ),
        metrics={
            "objective": spec.objective,
            "goal": spec.goal,
            "parameters": list(selected),
            "fixed": {name: fixed[name] for name in fixed if name not in selected},
            "sample_count": samples.sample_count,
            "finite_count": int(finite_indices.size),
            "strategy": samples.strategy,
            "exhaustive_declared_grid": samples.exhaustive_declared_grid,
            "best_point": best,
            "top_k": len(top_points),
        },
        artifacts=artifacts,
        figures=figures,
        claim_id=spec.claim_id,
    )
