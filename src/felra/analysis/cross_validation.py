from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import write_csv
from felra.config import CrossValidationAnalysisSpec, ModelCandidateSpec, ModelComparisonAnalysisSpec
from felra.data import Dataset
from felra.figures import FigureFactory


@dataclass(frozen=True)
class FoldPlan:
    train_indices: np.ndarray
    test_indices: np.ndarray


@dataclass
class CandidateEvaluation:
    name: str
    model: str
    degree: int
    fold_rows: list[dict[str, Any]]
    predictions: np.ndarray
    observed: np.ndarray
    row_indices: np.ndarray
    summary: dict[str, float]


def _relative(path: Path, output_root: Path) -> str:
    return str(path.relative_to(output_root))


def _complete_matrix(
    dataset: Dataset,
    features: tuple[str, ...],
    target: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    feature_columns = [np.asarray(dataset.columns[name], dtype=float).reshape(-1) for name in features]
    target_values = np.asarray(dataset.columns[target], dtype=float).reshape(-1)
    if not feature_columns:
        raise ValueError("At least one feature is required")
    matrix = np.column_stack(feature_columns)
    mask = np.all(np.isfinite(matrix), axis=1) & np.isfinite(target_values)
    rows = np.flatnonzero(mask)
    if rows.size < 4:
        raise ValueError("Cross-validation requires at least four complete finite rows")
    return matrix[mask], target_values[mask], rows


def _folds(sample_count: int, fold_count: int, *, shuffle: bool, seed: int) -> list[FoldPlan]:
    if fold_count < 2:
        raise ValueError("folds must be at least 2")
    if fold_count > sample_count:
        raise ValueError("folds cannot exceed the number of complete observations")
    indices = np.arange(sample_count)
    if shuffle:
        np.random.default_rng(seed).shuffle(indices)
    test_parts = np.array_split(indices, fold_count)
    plans: list[FoldPlan] = []
    for test_indices in test_parts:
        train_mask = np.ones(sample_count, dtype=bool)
        train_mask[test_indices] = False
        plans.append(FoldPlan(train_indices=indices[train_mask[indices]], test_indices=test_indices))
    return plans


def _transform_features(
    train: np.ndarray,
    test: np.ndarray,
    *,
    standardize: bool,
) -> tuple[np.ndarray, np.ndarray]:
    if not standardize:
        return train, test
    mean = np.mean(train, axis=0)
    scale = np.std(train, axis=0, ddof=0)
    scale = np.where(scale == 0.0, 1.0, scale)
    return (train - mean) / scale, (test - mean) / scale


def _design_matrix(values: np.ndarray, model: str, degree: int) -> np.ndarray:
    if model not in {"linear", "polynomial"}:
        raise ValueError(f"Unsupported model {model!r}")
    effective_degree = 1 if model == "linear" else degree
    if effective_degree < 1:
        raise ValueError("Polynomial degree must be at least 1")
    columns = [np.ones(values.shape[0], dtype=float)]
    for power in range(1, effective_degree + 1):
        columns.extend(values[:, index] ** power for index in range(values.shape[1]))
    return np.column_stack(columns)


def _metrics(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    residual = observed - predicted
    mse = float(np.mean(residual**2))
    mae = float(np.mean(np.abs(residual)))
    denominator = float(np.sum((observed - np.mean(observed)) ** 2))
    r2 = 1.0 - float(np.sum(residual**2)) / denominator if denominator else math.nan
    return {"rmse": math.sqrt(mse), "mae": mae, "r2": r2}


def evaluate_candidate(
    dataset: Dataset,
    *,
    features: tuple[str, ...],
    target: str,
    folds: int,
    shuffle: bool,
    seed: int,
    candidate: ModelCandidateSpec,
) -> CandidateEvaluation:
    matrix, target_values, source_rows = _complete_matrix(dataset, features, target)
    plans = _folds(matrix.shape[0], folds, shuffle=shuffle, seed=seed)
    predictions = np.full(target_values.shape, np.nan, dtype=float)
    fold_rows: list[dict[str, Any]] = []
    for fold_index, plan in enumerate(plans, start=1):
        train_x, test_x = _transform_features(
            matrix[plan.train_indices],
            matrix[plan.test_indices],
            standardize=candidate.standardize,
        )
        train_design = _design_matrix(train_x, candidate.model, candidate.degree)
        test_design = _design_matrix(test_x, candidate.model, candidate.degree)
        coefficients, *_ = np.linalg.lstsq(train_design, target_values[plan.train_indices], rcond=None)
        predicted = test_design @ coefficients
        predictions[plan.test_indices] = predicted
        fold_metrics = _metrics(target_values[plan.test_indices], predicted)
        fold_rows.append(
            {
                "model": candidate.name,
                "fold": fold_index,
                "train_n": int(plan.train_indices.size),
                "test_n": int(plan.test_indices.size),
                **fold_metrics,
            }
        )
    if np.any(~np.isfinite(predictions)):
        raise RuntimeError("Cross-validation did not produce one prediction per complete row")
    summary: dict[str, float] = {}
    for metric in ("rmse", "mae", "r2"):
        values = np.asarray([row[metric] for row in fold_rows], dtype=float)
        summary[f"mean_{metric}"] = float(np.mean(values))
        summary[f"std_{metric}"] = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    return CandidateEvaluation(
        name=candidate.name,
        model=candidate.model,
        degree=candidate.degree,
        fold_rows=fold_rows,
        predictions=predictions,
        observed=target_values,
        row_indices=source_rows,
        summary=summary,
    )


def _write_evaluation(
    evaluation: CandidateEvaluation,
    output_dir: Path,
    output_root: Path,
    *,
    title: str,
    target: str,
) -> tuple[list[str], list[str]]:
    fold_csv = output_dir / "fold_metrics.csv"
    write_csv(fold_csv, {key: [row[key] for row in evaluation.fold_rows] for key in evaluation.fold_rows[0]})
    prediction_csv = output_dir / "predictions.csv"
    write_csv(
        prediction_csv,
        {
            "source_row": evaluation.row_indices,
            "observed": evaluation.observed,
            "predicted": evaluation.predictions,
            "residual": evaluation.observed - evaluation.predictions,
        },
    )
    factory = FigureFactory(output_dir / "figures")
    scatter = factory.scatter_plot(
        evaluation.observed,
        evaluation.predictions,
        title=f"{title} — observed vs predicted",
        xlabel=f"Observed {target}",
        ylabel=f"Predicted {target}",
        filename="observed_vs_predicted.png",
    )
    residual = factory.histogram(
        evaluation.observed - evaluation.predictions,
        title=f"{title} — cross-validated residuals",
        xlabel="Residual",
        ylabel="Frequency",
        bins=30,
        filename="residual_distribution.png",
    )
    figures = [_relative(scatter, output_root), _relative(residual, output_root)]
    artifacts = [_relative(fold_csv, output_root), _relative(prediction_csv, output_root), *figures]
    return artifacts, figures


def run_cross_validation(
    spec: CrossValidationAnalysisSpec,
    dataset: Dataset,
    output_dir: Path,
    output_root: Path,
    *,
    default_seed: int,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = ModelCandidateSpec(
        name=spec.model,
        model=spec.model,
        degree=spec.degree,
        standardize=spec.standardize,
    )
    evaluation = evaluate_candidate(
        dataset,
        features=spec.features,
        target=spec.target,
        folds=spec.folds,
        shuffle=spec.shuffle,
        seed=default_seed if spec.seed is None else spec.seed,
        candidate=candidate,
    )
    artifacts, figures = _write_evaluation(
        evaluation, output_dir, output_root, title=spec.title, target=spec.target
    )
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=bool(
            all(
                np.isfinite(value)
                for key, value in evaluation.summary.items()
                if "r2" not in key
            )
            and np.isfinite(evaluation.summary["mean_r2"])
        ),
        summary=(
            f"{spec.folds}-fold cross-validation completed for {spec.model}; "
            f"mean RMSE={evaluation.summary['mean_rmse']:.6g}, "
            f"mean R²={evaluation.summary['mean_r2']:.6g}."
        ),
        metrics={
            "dataset": spec.dataset,
            "features": list(spec.features),
            "target": spec.target,
            "model": spec.model,
            "degree": spec.degree,
            "folds": spec.folds,
            "shuffle": spec.shuffle,
            "seed": default_seed if spec.seed is None else spec.seed,
            "standardize": spec.standardize,
            "summary": evaluation.summary,
            "complete_rows": int(evaluation.observed.size),
            "basis_note": "Polynomial models include per-feature powers without interaction terms.",
        },
        artifacts=artifacts,
        figures=figures,
        warnings=[
            "Cross-validation estimates predictive performance on the declared dataset; it does not certify external validity."
        ],
        claim_id=spec.claim_id,
    )


def run_model_comparison(
    spec: ModelComparisonAnalysisSpec,
    dataset: Dataset,
    output_dir: Path,
    output_root: Path,
    *,
    default_seed: int,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    seed = default_seed if spec.seed is None else spec.seed
    evaluations = [
        evaluate_candidate(
            dataset,
            features=spec.features,
            target=spec.target,
            folds=spec.folds,
            shuffle=spec.shuffle,
            seed=seed,
            candidate=candidate,
        )
        for candidate in spec.models
    ]
    primary_key = f"mean_{spec.primary_metric}"
    reverse = spec.primary_metric == "r2"
    ordered = sorted(evaluations, key=lambda item: item.summary[primary_key], reverse=reverse)
    ranking_rows: list[dict[str, Any]] = []
    for rank, evaluation in enumerate(ordered, start=1):
        ranking_rows.append(
            {
                "rank": rank,
                "model": evaluation.name,
                "type": evaluation.model,
                "degree": evaluation.degree,
                **evaluation.summary,
            }
        )
    comparison_csv = output_dir / "model_comparison.csv"
    write_csv(comparison_csv, {key: [row[key] for row in ranking_rows] for key in ranking_rows[0]})
    fold_rows = [row for evaluation in evaluations for row in evaluation.fold_rows]
    fold_csv = output_dir / "model_fold_metrics.csv"
    write_csv(fold_csv, {key: [row[key] for row in fold_rows] for key in fold_rows[0]})
    factory = FigureFactory(output_dir / "figures")
    comparison_figure = factory.bar_plot(
        [row["model"] for row in ranking_rows],
        [row[primary_key] for row in ranking_rows],
        title=f"{spec.title} — {spec.primary_metric}",
        xlabel="Model",
        ylabel=spec.primary_metric.upper(),
        filename="model_ranking.png",
    )
    best = ordered[0]
    scatter = factory.scatter_plot(
        best.observed,
        best.predictions,
        title=f"{spec.title} — best model: {best.name}",
        xlabel=f"Observed {spec.target}",
        ylabel=f"Predicted {spec.target}",
        filename="best_model_predictions.png",
    )
    figures = [_relative(comparison_figure, output_root), _relative(scatter, output_root)]
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=True,
        summary=(
            f"Compared {len(evaluations)} models on shared {spec.folds}-fold splits; "
            f"best {spec.primary_metric} model={best.name}."
        ),
        metrics={
            "dataset": spec.dataset,
            "features": list(spec.features),
            "target": spec.target,
            "folds": spec.folds,
            "shuffle": spec.shuffle,
            "seed": seed,
            "primary_metric": spec.primary_metric,
            "best_model": best.name,
            "ranking": ranking_rows,
            "shared_fold_plan": True,
            "selection_is_exploratory": True,
        },
        artifacts=[_relative(comparison_csv, output_root), _relative(fold_csv, output_root), *figures],
        figures=figures,
        warnings=[
            "Selecting a model on the same cross-validation results used for comparison is exploratory; use nested validation for confirmatory selection."
        ],
        claim_id=spec.claim_id,
    )
