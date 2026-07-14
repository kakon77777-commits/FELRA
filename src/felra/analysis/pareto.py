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
)
from felra.config import ParetoAnalysisSpec, ProjectSpec
from felra.figures import FigureFactory
from felra.sampling import build_declared_samples


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _pareto_mask_two_objectives(values: np.ndarray, goals: tuple[str, str]) -> np.ndarray:
    """Return an exact non-dominated mask for two finite objectives.

    Objectives are converted to minimization. Equal objective pairs are all kept because
    neither duplicate strictly dominates another.
    """

    normalized = values.copy()
    for column, goal in enumerate(goals):
        if goal == "maximize":
            normalized[:, column] *= -1.0

    order = np.lexsort((normalized[:, 1], normalized[:, 0]))
    sorted_values = normalized[order]
    mask_sorted = np.zeros(len(order), dtype=bool)
    best_previous_second = np.inf
    start = 0
    while start < len(order):
        stop = start + 1
        first_value = sorted_values[start, 0]
        while stop < len(order) and sorted_values[stop, 0] == first_value:
            stop += 1
        group = sorted_values[start:stop]
        group_min_second = float(np.min(group[:, 1]))
        if group_min_second < best_previous_second:
            group_winners = group[:, 1] == group_min_second
            mask_sorted[start:stop] = group_winners
            best_previous_second = group_min_second
        start = stop

    mask = np.zeros(len(order), dtype=bool)
    mask[order] = mask_sorted
    return mask


def run_pareto(
    spec: ParetoAnalysisSpec,
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

    objective_arrays = [
        broadcast_expression(objective.expression, context, samples.sample_count)
        for objective in spec.objectives
    ]
    values = np.column_stack(objective_arrays)
    finite = np.all(np.isfinite(values), axis=1)
    finite_values = values[finite]
    finite_indices = np.flatnonzero(finite)
    frontier_finite = (
        _pareto_mask_two_objectives(
            finite_values,
            (spec.objectives[0].goal, spec.objectives[1].goal),
        )
        if finite_values.size
        else np.zeros(0, dtype=bool)
    )
    frontier = np.zeros(samples.sample_count, dtype=bool)
    frontier[finite_indices] = frontier_finite

    columns = sample_columns(samples)
    for objective, array in zip(spec.objectives, objective_arrays, strict=True):
        columns[objective.name] = array
    columns.update({"finite": finite, "pareto_frontier": frontier})
    csv_path = output_dir / "pareto_points.csv"
    write_csv(csv_path, columns)

    frontier_columns = {
        name: np.asarray(values_)[frontier] for name, values_ in columns.items() if name != "finite"
    }
    frontier_path = output_dir / "pareto_frontier.csv"
    write_csv(frontier_path, frontier_columns)

    artifacts = [_relative(csv_path, output_root), _relative(frontier_path, output_root)]
    figures: list[str] = []
    if finite_values.size:
        figure = FigureFactory(output_dir / "figures").pareto_plot(
            finite_values[:, 0],
            finite_values[:, 1],
            frontier_finite,
            title=spec.title,
            xlabel=f"{spec.objectives[0].name} ({spec.objectives[0].goal})",
            ylabel=f"{spec.objectives[1].name} ({spec.objectives[1].goal})",
            filename="pareto_frontier.png",
        )
        figures.append(_relative(figure, output_root))
        artifacts.extend(figures)

    frontier_count = int(np.count_nonzero(frontier))
    success = bool(frontier_count)
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=success,
        summary=(
            (
                f"Found {frontier_count} non-dominated points among "
                f"{finite_values.shape[0]} finite candidates."
            )
            if finite_values.size
            else "Pareto analysis produced no finite candidate points."
        ),
        metrics={
            "parameters": list(selected),
            "fixed": {name: fixed[name] for name in fixed if name not in selected},
            "objectives": [
                {
                    "name": objective.name,
                    "expression": objective.expression,
                    "goal": objective.goal,
                }
                for objective in spec.objectives
            ],
            "sample_count": samples.sample_count,
            "finite_count": int(finite_values.shape[0]),
            "frontier_count": frontier_count,
            "frontier_fraction": (
                frontier_count / finite_values.shape[0] if finite_values.shape[0] else 0.0
            ),
            "strategy": samples.strategy,
            "exhaustive_declared_grid": samples.exhaustive_declared_grid,
        },
        artifacts=artifacts,
        figures=figures,
        claim_id=spec.claim_id,
    )
