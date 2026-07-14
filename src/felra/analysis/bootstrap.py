from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from felra.analysis.models import AnalysisResult
from felra.config import BootstrapCIAnalysisSpec
from felra.data import Dataset
from felra.figures import FigureFactory


def _relative(path: Path, output_root: Path) -> str:
    return str(path.relative_to(output_root))


def run_bootstrap_ci(
    spec: BootstrapCIAnalysisSpec,
    dataset: Dataset,
    output_dir: Path,
    output_root: Path,
    *,
    default_seed: int,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    values = np.asarray(dataset.columns[spec.column], dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size < 2:
        raise ValueError("Bootstrap confidence interval requires at least two finite observations")
    statistic = np.mean if spec.statistic == "mean" else np.median
    estimate = float(statistic(values))
    seed = default_seed if spec.seed is None else spec.seed
    rng = np.random.default_rng(seed)
    distribution = np.empty(spec.resamples, dtype=float)
    for index in range(spec.resamples):
        sample = rng.choice(values, size=values.size, replace=True)
        distribution[index] = float(statistic(sample))
    tail = (1.0 - spec.confidence) / 2.0
    lower, upper = np.quantile(distribution, [tail, 1.0 - tail])
    standard_error = float(np.std(distribution, ddof=1))

    distribution_csv = output_dir / "bootstrap_distribution.csv"
    with distribution_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["replicate", spec.statistic])
        writer.writerows(enumerate(distribution, start=1))
    factory = FigureFactory(output_dir / "figures")
    figure = factory.bootstrap_distribution(
        distribution,
        estimate=estimate,
        lower=float(lower),
        upper=float(upper),
        title=spec.title,
        xlabel=f"Bootstrap {spec.statistic}",
        bins=50,
        filename="bootstrap_distribution.png",
    )
    artifacts = [_relative(distribution_csv, output_root), _relative(figure, output_root)]
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=True,
        summary=(
            f"{spec.confidence:.1%} percentile bootstrap CI for {spec.statistic}: "
            f"[{float(lower):.6g}, {float(upper):.6g}]."
        ),
        metrics={
            "dataset": spec.dataset,
            "column": spec.column,
            "statistic": spec.statistic,
            "estimate": estimate,
            "confidence": spec.confidence,
            "ci_lower": float(lower),
            "ci_upper": float(upper),
            "bootstrap_standard_error": standard_error,
            "resamples": spec.resamples,
            "seed": seed,
            "sample_count": int(values.size),
            "method": "percentile_bootstrap",
        },
        artifacts=artifacts,
        figures=[_relative(figure, output_root)],
        claim_id=spec.claim_id,
    )
