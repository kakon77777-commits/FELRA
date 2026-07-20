from __future__ import annotations

from pathlib import Path

import numpy as np

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import write_csv
from felra.config import RobustnessAnalysisSpec
from felra.data import Dataset
from felra.figures import FigureFactory


def _relative(path: Path, output_root: Path) -> str:
    return str(path.relative_to(output_root))


def _finite(dataset: Dataset, column: str) -> np.ndarray:
    values = np.asarray(dataset.columns[column], dtype=float).reshape(-1)
    return values[np.isfinite(values)]


def _observed(spec: RobustnessAnalysisSpec, dataset: Dataset, indices: np.ndarray | None = None) -> float:
    if spec.statistic in {"mean", "median", "std"}:
        values = _finite(dataset, spec.columns[0])
        if indices is not None:
            values = values[indices]
        if spec.statistic == "mean":
            return float(np.mean(values))
        if spec.statistic == "median":
            return float(np.median(values))
        return float(np.std(values, ddof=1))
    if spec.statistic == "correlation":
        x = np.asarray(dataset.columns[spec.columns[0]], dtype=float)
        y = np.asarray(dataset.columns[spec.columns[1]], dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if indices is not None:
            x, y = x[indices], y[indices]
        return float(np.corrcoef(x, y)[0, 1])
    if spec.statistic == "mean_difference":
        values = np.asarray(dataset.columns[spec.columns[0]], dtype=float)
        groups = np.asarray(dataset.columns[spec.group_by], dtype=object)
        mask = np.isfinite(values)
        values, groups = values[mask], groups[mask]
        if indices is not None:
            values, groups = values[indices], groups[indices]
        first = values[groups == spec.groups[0]]
        second = values[groups == spec.groups[1]]
        if first.size == 0 or second.size == 0:
            raise ValueError("A resample omitted one of the requested groups")
        return float(np.mean(second) - np.mean(first))
    raise ValueError(f"Unsupported robustness statistic {spec.statistic!r}")


def _base_size(spec: RobustnessAnalysisSpec, dataset: Dataset) -> int:
    if spec.statistic in {"mean", "median", "std"}:
        return _finite(dataset, spec.columns[0]).size
    if spec.statistic == "correlation":
        x = np.asarray(dataset.columns[spec.columns[0]], dtype=float)
        y = np.asarray(dataset.columns[spec.columns[1]], dtype=float)
        return int(np.sum(np.isfinite(x) & np.isfinite(y)))
    values = np.asarray(dataset.columns[spec.columns[0]], dtype=float)
    return int(np.sum(np.isfinite(values)))


def run_robustness(
    spec: RobustnessAnalysisSpec,
    dataset: Dataset,
    output_dir: Path,
    output_root: Path,
    *,
    default_seed: int,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    seed = default_seed if spec.seed is None else spec.seed
    rng = np.random.default_rng(seed)
    n = _base_size(spec, dataset)
    if n < 3:
        raise ValueError("Robustness analysis requires at least three usable observations")
    resample_size = n if spec.method == "bootstrap" else max(2, int(round(n * spec.fraction)))
    values: list[float] = []
    failed = 0
    for _ in range(spec.repetitions):
        replace = spec.method == "bootstrap"
        indices = rng.choice(n, size=resample_size, replace=replace)
        try:
            value = _observed(spec, dataset, indices)
        except ValueError:
            failed += 1
            continue
        if np.isfinite(value):
            values.append(value)
        else:
            failed += 1
    if len(values) < max(20, spec.repetitions // 5):
        raise ValueError("Too few valid resamples were produced")

    observed = _observed(spec, dataset)
    array = np.asarray(values, dtype=float)
    alpha = 1.0 - spec.confidence
    lower, upper = np.quantile(array, [alpha / 2.0, 1.0 - alpha / 2.0])
    resample_mean = float(np.mean(array))
    resample_std = float(np.std(array, ddof=1))
    sign = np.sign(observed)
    sign_stability = float(np.mean(np.sign(array) == sign)) if sign != 0 else None
    relative_dispersion = resample_std / abs(observed) if observed != 0 else None
    csv_path = output_dir / "robustness_distribution.csv"
    write_csv(
        csv_path,
        {
            "replicate": np.arange(1, len(values) + 1, dtype=int),
            "estimate": values,
        },
    )
    figure_path = FigureFactory(output_dir).bootstrap_distribution(
        array,
        estimate=observed,
        lower=float(lower),
        upper=float(upper),
        title=spec.title,
        xlabel=spec.statistic,
        bins=spec.bins,
        filename="robustness_distribution.png",
    )
    metrics = {
        "dataset": spec.dataset,
        "statistic": spec.statistic,
        "columns": list(spec.columns),
        "group_by": spec.group_by,
        "groups": list(spec.groups),
        "method": spec.method,
        "seed": seed,
        "repetitions_requested": spec.repetitions,
        "repetitions_valid": len(values),
        "repetitions_failed": failed,
        "fraction": spec.fraction,
        "resample_size": resample_size,
        "observed_estimate": observed,
        "resample_mean": resample_mean,
        "resample_standard_deviation": resample_std,
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "confidence": spec.confidence,
        "sign_stability": sign_stability,
        "relative_dispersion": relative_dispersion,
    }
    warnings = []
    if failed:
        warnings.append(f"{failed} resamples were discarded because the statistic was undefined.")
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=True,
        summary=(
            f"Observed {spec.statistic}={observed:.6g}; {spec.confidence:.1%} resampling interval "
            f"[{lower:.6g}, {upper:.6g}]."
        ),
        metrics=metrics,
        artifacts=[_relative(csv_path, output_root), _relative(figure_path, output_root)],
        figures=[_relative(figure_path, output_root)],
        warnings=warnings,
        claim_id=spec.claim_id,
    )
