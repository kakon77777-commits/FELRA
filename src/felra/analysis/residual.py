from __future__ import annotations

from pathlib import Path

import numpy as np

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import broadcast_expression, sample_columns, write_csv
from felra.config import ProjectSpec, ResidualAnalysisSpec
from felra.figures import FigureFactory
from felra.sampling import build_declared_samples


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def run_residual(
    spec: ResidualAnalysisSpec,
    project: ProjectSpec,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = build_declared_samples(
        project.parameters,
        max_evaluations=project.execution.max_evaluations,
        seed=project.execution.seed,
    )
    reference = broadcast_expression(spec.reference, samples.variables, samples.sample_count)
    approximation = broadcast_expression(
        spec.approximation,
        samples.variables,
        samples.sample_count,
    )
    residual = reference - approximation
    finite = np.isfinite(reference) & np.isfinite(approximation) & np.isfinite(residual)
    finite_residual = residual[finite]

    columns = sample_columns(samples)
    columns.update(
        {
            "reference": reference,
            "approximation": approximation,
            "residual": residual,
            "finite": finite,
        }
    )
    csv_path = output_dir / "residuals.csv"
    write_csv(csv_path, columns)

    warnings: list[str] = []
    if not np.all(finite):
        warnings.append(f"Excluded {int(np.count_nonzero(~finite))} non-finite residual rows.")

    figures: list[str] = []
    artifacts = [_relative(csv_path, output_root)]
    factory = FigureFactory(output_dir / "figures")
    if finite_residual.size:
        if spec.independent:
            x_values = np.asarray(samples.variables[spec.independent]).reshape(-1)[finite]
            xlabel = spec.independent
        else:
            x_values = np.flatnonzero(finite)
            xlabel = "Sample index"
        scatter_path = factory.residual_plot(
            x_values,
            finite_residual,
            title=f"{spec.title} — residuals",
            xlabel=xlabel,
            ylabel="Reference − approximation",
            filename="residual_scatter.png",
        )
        histogram_path = factory.histogram(
            finite_residual,
            title=f"{spec.title} — residual distribution",
            xlabel="Residual",
            ylabel="Frequency",
            bins=spec.bins,
            filename="residual_histogram.png",
        )
        figures.extend(
            [_relative(scatter_path, output_root), _relative(histogram_path, output_root)]
        )
        artifacts.extend(figures)

    if finite_residual.size:
        mae = float(np.mean(np.abs(finite_residual)))
        rmse = float(np.sqrt(np.mean(np.square(finite_residual))))
        bias = float(np.mean(finite_residual))
        median = float(np.median(finite_residual))
        std = float(np.std(finite_residual))
        maximum = float(np.max(np.abs(finite_residual)))
    else:
        mae = rmse = bias = median = std = maximum = float("nan")

    tolerance_passed = spec.tolerance is None or (np.isfinite(rmse) and rmse <= spec.tolerance)
    success = bool(finite_residual.size and tolerance_passed)
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=success,
        summary=(
            (
                f"Computed residual metrics over {finite_residual.size} finite samples; "
                f"RMSE={rmse:.6g}."
            )
            if finite_residual.size
            else "Residual analysis produced no finite samples."
        ),
        metrics={
            "reference": spec.reference,
            "approximation": spec.approximation,
            "sample_count": samples.sample_count,
            "finite_count": int(finite_residual.size),
            "strategy": samples.strategy,
            "exhaustive_declared_grid": samples.exhaustive_declared_grid,
            "mean_absolute_error": mae,
            "root_mean_squared_error": rmse,
            "bias": bias,
            "median_residual": median,
            "residual_std": std,
            "max_absolute_residual": maximum,
            "tolerance": spec.tolerance,
            "tolerance_passed": tolerance_passed,
        },
        artifacts=artifacts,
        figures=figures,
        warnings=warnings,
        claim_id=spec.claim_id,
    )
