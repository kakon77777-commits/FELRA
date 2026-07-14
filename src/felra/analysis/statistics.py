from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import write_csv
from felra.config import DescriptiveAnalysisSpec, HypothesisTestAnalysisSpec
from felra.data import Dataset
from felra.figures import FigureFactory


def _relative(path: Path, output_root: Path) -> str:
    return str(path.relative_to(output_root))


def _numeric(dataset: Dataset, column: str) -> np.ndarray:
    try:
        values = np.asarray(dataset.columns[column], dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Column {column!r} must be numeric") from exc
    return values[np.isfinite(values)]


def _paired_numeric(dataset: Dataset, first: str, second: str) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(dataset.columns[first], dtype=float).reshape(-1)
    y = np.asarray(dataset.columns[second], dtype=float).reshape(-1)
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


def _mean_ci(values: np.ndarray, confidence: float) -> tuple[float, float, float, float]:
    n = values.size
    mean = float(np.mean(values))
    if n < 2:
        return mean, math.nan, math.nan, math.nan
    std = float(np.std(values, ddof=1))
    sem = std / math.sqrt(n)
    critical = float(stats.t.ppf((1.0 + confidence) / 2.0, n - 1))
    return mean, std, mean - critical * sem, mean + critical * sem


def run_descriptive(
    spec: DescriptiveAnalysisSpec,
    dataset: Dataset,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    factory = FigureFactory(output_dir / "figures")
    rows: list[dict[str, Any]] = []
    figures: list[str] = []
    group_values = dataset.columns[spec.group_by] if spec.group_by else None
    groups = (
        sorted({str(value) for value in group_values.tolist()})
        if group_values is not None
        else ["all"]
    )

    for column in spec.columns:
        raw_numeric = np.asarray(dataset.columns[column], dtype=float).reshape(-1)
        box_groups: list[np.ndarray] = []
        box_labels: list[str] = []
        for group in groups:
            if group_values is None:
                values = raw_numeric[np.isfinite(raw_numeric)]
            else:
                mask = np.asarray([str(value) == group for value in group_values], dtype=bool)
                values = raw_numeric[mask & np.isfinite(raw_numeric)]
            if values.size == 0:
                continue
            mean, std, ci_lower, ci_upper = _mean_ci(values, spec.confidence)
            rows.append(
                {
                    "column": column,
                    "group": group,
                    "n": int(values.size),
                    "mean": mean,
                    "std": std,
                    "median": float(np.median(values)),
                    "minimum": float(np.min(values)),
                    "maximum": float(np.max(values)),
                    "ci_confidence": spec.confidence,
                    "ci_lower": ci_lower,
                    "ci_upper": ci_upper,
                }
            )
            box_groups.append(values)
            box_labels.append(group)

        if box_groups:
            if spec.group_by:
                figure = factory.grouped_boxplot(
                    box_groups,
                    box_labels,
                    title=f"{spec.title} — {column}",
                    ylabel=column,
                    filename=f"{column}_boxplot.png",
                )
            else:
                figure = factory.histogram(
                    box_groups[0],
                    title=f"{spec.title} — {column}",
                    xlabel=column,
                    ylabel="Frequency",
                    bins=spec.bins,
                    filename=f"{column}_histogram.png",
                )
            figures.append(_relative(figure, output_root))

    if not rows:
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            kind=spec.kind,
            title=spec.title,
            success=False,
            summary="No finite numeric observations were available.",
            warnings=["Descriptive analysis found no finite observations."],
            claim_id=spec.claim_id,
        )

    summary_csv = output_dir / "descriptive_summary.csv"
    columns = {key: [row[key] for row in rows] for key in rows[0]}
    write_csv(summary_csv, columns)
    ci_figure = factory.confidence_interval_plot(
        [f"{row['column']}:{row['group']}" for row in rows],
        [row["mean"] for row in rows],
        [row["ci_lower"] for row in rows],
        [row["ci_upper"] for row in rows],
        title=f"{spec.title} — mean confidence intervals",
        ylabel="Mean",
        filename="mean_confidence_intervals.png",
    )
    figures.append(_relative(ci_figure, output_root))
    artifacts = [_relative(summary_csv, output_root), *figures]
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=True,
        summary=f"Computed descriptive statistics for {len(rows)} column/group combinations.",
        metrics={
            "dataset": spec.dataset,
            "columns": list(spec.columns),
            "group_by": spec.group_by,
            "confidence": spec.confidence,
            "summaries": rows,
        },
        artifacts=artifacts,
        figures=figures,
        claim_id=spec.claim_id,
    )


def _cohen_d_independent(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 2 or y.size < 2:
        return math.nan
    pooled_numerator = (x.size - 1) * np.var(x, ddof=1) + (y.size - 1) * np.var(y, ddof=1)
    pooled = math.sqrt(pooled_numerator / (x.size + y.size - 2))
    return float((np.mean(x) - np.mean(y)) / pooled) if pooled else math.nan


def run_hypothesis_test(
    spec: HypothesisTestAnalysisSpec,
    dataset: Dataset,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    factory = FigureFactory(output_dir / "figures")
    test = spec.test
    statistic: float
    pvalue: float
    effect_size: float | None = None
    sample_sizes: dict[str, int] = {}
    figures: list[str] = []
    warnings: list[str] = []

    if test == "one_sample_t":
        if not spec.column:
            raise ValueError("one_sample_t requires column")
        x = _numeric(dataset, spec.column)
        result = stats.ttest_1samp(x, popmean=spec.mu, alternative=spec.alternative)
        statistic, pvalue = float(result.statistic), float(result.pvalue)
        effect_size = float((np.mean(x) - spec.mu) / np.std(x, ddof=1)) if x.size > 1 else math.nan
        sample_sizes = {spec.column: int(x.size)}
        figure = factory.histogram(
            x,
            title=f"{spec.title} — {spec.column}",
            xlabel=spec.column,
            ylabel="Frequency",
            bins=30,
            filename="sample_distribution.png",
        )
        figures.append(_relative(figure, output_root))

    elif test in {"independent_t", "mann_whitney"}:
        if not spec.column or not spec.group_by or len(spec.groups) != 2:
            raise ValueError(f"{test} requires column, group_by, and exactly two groups")
        values = np.asarray(dataset.columns[spec.column], dtype=float).reshape(-1)
        labels = np.asarray(dataset.columns[spec.group_by], dtype=object).reshape(-1)
        groups: list[np.ndarray] = []
        for group in spec.groups:
            mask = np.asarray([str(value) == group for value in labels], dtype=bool)
            group_values = values[mask & np.isfinite(values)]
            if not group_values.size:
                raise ValueError(f"Group {group!r} contains no finite values")
            groups.append(group_values)
            sample_sizes[group] = int(group_values.size)
        x, y = groups
        if test == "independent_t":
            result = stats.ttest_ind(
                x,
                y,
                equal_var=spec.equal_var,
                alternative=spec.alternative,
            )
            effect_size = _cohen_d_independent(x, y)
            warnings.append("Normality and variance assumptions are not automatically certified.")
        else:
            result = stats.mannwhitneyu(x, y, alternative=spec.alternative)
            effect_size = float(1.0 - (2.0 * float(result.statistic)) / (x.size * y.size))
        statistic, pvalue = float(result.statistic), float(result.pvalue)
        figure = factory.grouped_boxplot(
            groups,
            list(spec.groups),
            title=spec.title,
            ylabel=spec.column,
            filename="group_comparison.png",
        )
        figures.append(_relative(figure, output_root))

    elif test in {"paired_t", "wilcoxon", "pearson", "spearman"}:
        if len(spec.columns) != 2:
            raise ValueError(f"{test} requires exactly two columns")
        x, y = _paired_numeric(dataset, spec.columns[0], spec.columns[1])
        if not x.size:
            raise ValueError("No complete finite pairs are available")
        sample_sizes = {"pairs": int(x.size)}
        if test == "paired_t":
            result = stats.ttest_rel(x, y, alternative=spec.alternative)
            difference = x - y
            effect_size = (
                float(np.mean(difference) / np.std(difference, ddof=1))
                if difference.size > 1 and np.std(difference, ddof=1)
                else math.nan
            )
            warnings.append("Normality of paired differences is not automatically certified.")
        elif test == "wilcoxon":
            result = stats.wilcoxon(x, y, alternative=spec.alternative)
        elif test == "pearson":
            result = stats.pearsonr(x, y, alternative=spec.alternative)
            effect_size = float(result.statistic)
        else:
            result = stats.spearmanr(x, y, alternative=spec.alternative)
            effect_size = float(result.statistic)
        statistic, pvalue = float(result.statistic), float(result.pvalue)
        if test in {"pearson", "spearman"}:
            figure = factory.scatter_plot(
                x,
                y,
                title=spec.title,
                xlabel=spec.columns[0],
                ylabel=spec.columns[1],
                filename="paired_scatter.png",
            )
        else:
            figure = factory.grouped_boxplot(
                [x, y],
                list(spec.columns),
                title=spec.title,
                ylabel="Value",
                filename="paired_comparison.png",
            )
        figures.append(_relative(figure, output_root))

    else:  # pragma: no cover
        raise ValueError(f"Unsupported hypothesis test {test!r}")

    decision = "reject_null" if pvalue < spec.alpha else "fail_to_reject_null"
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=bool(np.isfinite(statistic) and np.isfinite(pvalue)),
        summary=(
            f"{test} produced statistic={statistic:.6g}, p={pvalue:.6g}; "
            f"decision={decision} at alpha={spec.alpha}."
        ),
        metrics={
            "dataset": spec.dataset,
            "test": test,
            "statistic": statistic,
            "p_value": pvalue,
            "alpha": spec.alpha,
            "alternative": spec.alternative,
            "decision": decision,
            "effect_size": effect_size,
            "sample_sizes": sample_sizes,
            "column": spec.column,
            "columns": list(spec.columns),
            "group_by": spec.group_by,
            "groups": list(spec.groups),
            "mu": spec.mu,
            "equal_var": spec.equal_var,
        },
        artifacts=list(figures),
        figures=figures,
        warnings=warnings,
        claim_id=spec.claim_id,
    )
