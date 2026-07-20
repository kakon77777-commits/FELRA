from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from felra.analysis.effect import (
    adjust_pvalues,
    independent_effect_sizes,
    mann_whitney_rank_biserial,
)
from felra.analysis.models import AnalysisResult
from felra.analysis.utils import write_csv
from felra.config import MultipleComparisonAnalysisSpec
from felra.data import Dataset
from felra.figures import FigureFactory


def _relative(path: Path, output_root: Path) -> str:
    return str(path.relative_to(output_root))


def _group_values(dataset: Dataset, column: str, group_by: str, group: str) -> np.ndarray:
    values = np.asarray(dataset.columns[column], dtype=float).reshape(-1)
    labels = np.asarray(dataset.columns[group_by], dtype=object).reshape(-1)
    mask = np.asarray([str(value) == group for value in labels], dtype=bool) & np.isfinite(values)
    selected = values[mask]
    if selected.size == 0:
        raise ValueError(f"Group {group!r} contains no finite values")
    return selected


def run_multiple_comparisons(
    spec: MultipleComparisonAnalysisSpec,
    dataset: Dataset,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    declared_groups = list(spec.groups)
    if not declared_groups:
        declared_groups = sorted({str(value) for value in dataset.columns[spec.group_by].tolist()})
    pairs = list(spec.comparisons) if spec.comparisons else list(combinations(declared_groups, 2))
    if not pairs:
        raise ValueError("Multiple-comparison analysis requires at least one group pair")
    rows: list[dict[str, Any]] = []
    raw_pvalues: list[float] = []
    for first, second in pairs:
        x = _group_values(dataset, spec.column, spec.group_by, first)
        y = _group_values(dataset, spec.column, spec.group_by, second)
        if spec.test == "independent_t":
            result = stats.ttest_ind(
                x,
                y,
                equal_var=spec.equal_var,
                alternative=spec.alternative,
            )
            effects = independent_effect_sizes(x, y)
            effect_name = "hedges_g"
            effect_value = effects[effect_name]
        else:
            result = stats.mannwhitneyu(x, y, alternative=spec.alternative)
            effect_name = "rank_biserial"
            effect_value = mann_whitney_rank_biserial(float(result.statistic), x.size, y.size)
            effects = {effect_name: effect_value}
        raw_p = float(result.pvalue)
        raw_pvalues.append(raw_p)
        rows.append(
            {
                "comparison": f"{first} vs {second}",
                "group_a": first,
                "group_b": second,
                "n_a": int(x.size),
                "n_b": int(y.size),
                "statistic": float(result.statistic),
                "raw_p": raw_p,
                "effect_name": effect_name,
                "effect_size": effect_value,
                "effect_sizes": effects,
            }
        )
    adjusted = adjust_pvalues(raw_pvalues, spec.correction)
    for row, adjusted_p in zip(rows, adjusted, strict=True):
        row["adjusted_p"] = float(adjusted_p)
        row["reject_after_correction"] = bool(adjusted_p < spec.alpha)
    table_csv = output_dir / "multiple_comparisons.csv"
    csv_rows = [
        {key: value for key, value in row.items() if key != "effect_sizes"}
        for row in rows
    ]
    write_csv(table_csv, {key: [row[key] for row in csv_rows] for key in csv_rows[0]})
    factory = FigureFactory(output_dir / "figures")
    figure = factory.bar_plot(
        [row["comparison"] for row in rows],
        [row["adjusted_p"] for row in rows],
        title=f"{spec.title} — adjusted p-values",
        xlabel="Comparison",
        ylabel="Adjusted p-value",
        filename="adjusted_pvalues.png",
    )
    figure_path = _relative(figure, output_root)
    rejection_count = sum(bool(row["reject_after_correction"]) for row in rows)
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=True,
        summary=(
            f"Corrected {len(rows)} comparisons using {spec.correction}; "
            f"{rejection_count} remained below alpha={spec.alpha}."
        ),
        metrics={
            "dataset": spec.dataset,
            "column": spec.column,
            "group_by": spec.group_by,
            "test": spec.test,
            "correction": spec.correction,
            "alpha": spec.alpha,
            "family_size": len(rows),
            "comparisons": rows,
            "rejections": rejection_count,
        },
        artifacts=[_relative(table_csv, output_root), figure_path],
        figures=[figure_path],
        warnings=[
            "The comparison family is defined by this analysis block; changing the family changes the adjusted p-values."
        ],
        claim_id=spec.claim_id,
    )
