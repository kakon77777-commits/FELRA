from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from scipy import stats


def hedges_correction(degrees_of_freedom: float) -> float:
    """Small-sample correction used by Hedges' g."""
    if degrees_of_freedom <= 1:
        return math.nan
    return float(1.0 - 3.0 / (4.0 * degrees_of_freedom - 1.0))


def independent_effect_sizes(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 2 or y.size < 2:
        return {"cohen_d": math.nan, "hedges_g": math.nan, "glass_delta": math.nan}
    pooled_numerator = (x.size - 1) * np.var(x, ddof=1) + (y.size - 1) * np.var(y, ddof=1)
    degrees_of_freedom = x.size + y.size - 2
    pooled = math.sqrt(pooled_numerator / degrees_of_freedom) if degrees_of_freedom else math.nan
    mean_difference = float(np.mean(x) - np.mean(y))
    cohen_d = mean_difference / pooled if pooled and np.isfinite(pooled) else math.nan
    control_std = float(np.std(y, ddof=1))
    glass_delta = mean_difference / control_std if control_std else math.nan
    correction = hedges_correction(float(degrees_of_freedom))
    return {
        "cohen_d": float(cohen_d),
        "hedges_g": float(cohen_d * correction) if np.isfinite(correction) else math.nan,
        "glass_delta": float(glass_delta),
    }


def one_sample_effect_sizes(x: np.ndarray, mu: float) -> dict[str, float]:
    x = np.asarray(x, dtype=float)
    if x.size < 2:
        return {"cohen_d": math.nan, "hedges_g": math.nan}
    std = float(np.std(x, ddof=1))
    cohen_d = float((np.mean(x) - mu) / std) if std else math.nan
    correction = hedges_correction(float(x.size - 1))
    return {
        "cohen_d": cohen_d,
        "hedges_g": float(cohen_d * correction) if np.isfinite(correction) else math.nan,
    }


def paired_effect_sizes(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    difference = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    if difference.size < 2:
        return {"cohen_dz": math.nan, "hedges_gz": math.nan}
    std = float(np.std(difference, ddof=1))
    cohen_dz = float(np.mean(difference) / std) if std else math.nan
    correction = hedges_correction(float(difference.size - 1))
    return {
        "cohen_dz": cohen_dz,
        "hedges_gz": float(cohen_dz * correction) if np.isfinite(correction) else math.nan,
    }


def mann_whitney_rank_biserial(u_statistic: float, n_x: int, n_y: int) -> float:
    denominator = n_x * n_y
    return float(2.0 * u_statistic / denominator - 1.0) if denominator else math.nan


def wilcoxon_rank_biserial(x: np.ndarray, y: np.ndarray) -> float:
    differences = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    differences = differences[np.isfinite(differences) & (differences != 0.0)]
    if differences.size == 0:
        return math.nan
    ranks = stats.rankdata(np.abs(differences))
    positive = float(np.sum(ranks[differences > 0]))
    negative = float(np.sum(ranks[differences < 0]))
    total = positive + negative
    return float((positive - negative) / total) if total else math.nan


def adjust_pvalues(pvalues: Iterable[float], method: str) -> np.ndarray:
    """Adjust one family of p-values using a deterministic correction method."""
    raw = np.asarray(list(pvalues), dtype=float)
    if raw.ndim != 1 or raw.size == 0:
        raise ValueError("pvalues must contain at least one value")
    if np.any(~np.isfinite(raw)) or np.any((raw < 0.0) | (raw > 1.0)):
        raise ValueError("pvalues must be finite and lie in [0, 1]")
    method = method.lower()
    count = raw.size
    if method == "none":
        return raw.copy()
    if method == "bonferroni":
        return np.minimum(raw * count, 1.0)
    order = np.argsort(raw, kind="stable")
    sorted_p = raw[order]
    adjusted_sorted = np.empty_like(sorted_p)
    if method == "holm":
        scaled = (count - np.arange(count)) * sorted_p
        adjusted_sorted = np.maximum.accumulate(scaled)
    elif method == "fdr_bh":
        scaled = count * sorted_p / np.arange(1, count + 1)
        adjusted_sorted = np.minimum.accumulate(scaled[::-1])[::-1]
    else:
        raise ValueError("method must be none, bonferroni, holm, or fdr_bh")
    adjusted_sorted = np.minimum(adjusted_sorted, 1.0)
    adjusted = np.empty_like(adjusted_sorted)
    adjusted[order] = adjusted_sorted
    return adjusted
