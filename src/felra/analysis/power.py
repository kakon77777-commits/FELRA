from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

import numpy as np
from scipy import stats

from felra.analysis.models import AnalysisResult
from felra.analysis.utils import write_csv
from felra.config import PowerAnalysisSpec
from felra.figures import FigureFactory


def _relative(path: Path, output_root: Path) -> str:
    return str(path.relative_to(output_root))


def _tail_power(distribution: stats.rv_continuous, critical: float, alternative: str) -> float:
    if alternative == "greater":
        return float(distribution.sf(critical))
    if alternative == "less":
        return float(distribution.cdf(-critical))
    return float(distribution.sf(critical) + distribution.cdf(-critical))


def _t_power(effect_size: float, n1: int, n2: int | None, alpha: float, alternative: str) -> float:
    if n2 is None:
        df = n1 - 1
        ncp = effect_size * math.sqrt(n1)
    else:
        df = n1 + n2 - 2
        ncp = effect_size / math.sqrt(1.0 / n1 + 1.0 / n2)
    if df <= 0:
        return 0.0
    critical_probability = 1.0 - alpha / 2.0 if alternative == "two-sided" else 1.0 - alpha
    critical = float(stats.t.ppf(critical_probability, df))
    distribution = stats.nct(df, ncp)
    return min(max(_tail_power(distribution, critical, alternative), 0.0), 1.0)


def _correlation_power(effect_size: float, n: int, alpha: float, alternative: str) -> float:
    if n <= 3 or abs(effect_size) >= 1.0:
        return 0.0
    signal = math.atanh(effect_size) * math.sqrt(n - 3)
    critical = float(
        stats.norm.ppf(1.0 - alpha / 2.0 if alternative == "two-sided" else 1.0 - alpha)
    )
    distribution = stats.norm(loc=signal, scale=1.0)
    return min(max(_tail_power(distribution, critical, alternative), 0.0), 1.0)


def _power_function(spec: PowerAnalysisSpec) -> Callable[[int], tuple[float, int | None]]:
    if spec.test in {"one_sample_t", "paired_t"}:
        return lambda n: (_t_power(spec.effect_size, n, None, spec.alpha, spec.alternative), None)
    if spec.test == "independent_t":
        return lambda n: (
            _t_power(
                spec.effect_size,
                n,
                max(2, int(math.ceil(n * spec.allocation_ratio))),
                spec.alpha,
                spec.alternative,
            ),
            max(2, int(math.ceil(n * spec.allocation_ratio))),
        )
    if spec.test == "correlation":
        return lambda n: (_correlation_power(spec.effect_size, n, spec.alpha, spec.alternative), None)
    raise ValueError(f"Unsupported power-analysis test {spec.test!r}")


def run_power_analysis(
    spec: PowerAnalysisSpec,
    output_dir: Path,
    output_root: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    power_at = _power_function(spec)
    minimum = 4 if spec.test == "correlation" else 2
    sample_sizes = np.arange(minimum, spec.max_sample_size + 1, dtype=int)
    powers: list[float] = []
    second_group_sizes: list[int | None] = []
    for n in sample_sizes:
        power, n2 = power_at(int(n))
        powers.append(power)
        second_group_sizes.append(n2)

    required_n: int | None = None
    required_n2: int | None = None
    achieved_power: float | None = None
    if spec.target_power is not None:
        for n, power, n2 in zip(sample_sizes, powers, second_group_sizes, strict=True):
            if power >= spec.target_power:
                required_n = int(n)
                required_n2 = n2
                achieved_power = float(power)
                break
    if spec.sample_size is not None:
        achieved_power, required_n2 = power_at(spec.sample_size)

    curve_path = output_dir / "power_curve.csv"
    write_csv(
        curve_path,
        {
            "sample_size_group_1": sample_sizes,
            "sample_size_group_2": [n2 if n2 is not None else "" for n2 in second_group_sizes],
            "power": powers,
        },
    )
    figure_path = FigureFactory(output_dir).line_plot(
        sample_sizes,
        powers,
        title=spec.title,
        xlabel="Sample size (group 1 or total paired observations)",
        ylabel="Statistical power",
        filename="power_curve.png",
    )

    success = True
    warnings: list[str] = []
    if spec.target_power is not None and required_n is None:
        success = False
        warnings.append(
            f"Target power {spec.target_power:.3f} was not reached by max_sample_size="
            f"{spec.max_sample_size}."
        )
    metrics = {
        "test": spec.test,
        "effect_size": spec.effect_size,
        "alpha": spec.alpha,
        "alternative": spec.alternative,
        "target_power": spec.target_power,
        "requested_sample_size": spec.sample_size,
        "required_sample_size_group_1": required_n,
        "required_sample_size_group_2": required_n2 if spec.test == "independent_t" else None,
        "achieved_power": achieved_power,
        "allocation_ratio": spec.allocation_ratio,
        "max_sample_size": spec.max_sample_size,
        "method": "noncentral_t" if spec.test != "correlation" else "fisher_z_normal_approximation",
    }
    if spec.sample_size is not None:
        summary = f"Achieved power at n={spec.sample_size}: {achieved_power:.4f}."
    elif required_n is not None:
        if spec.test == "independent_t":
            summary = (
                f"Required sample sizes: n1={required_n}, n2={required_n2} for target power "
                f"{spec.target_power:.3f}."
            )
        else:
            summary = f"Required sample size: n={required_n} for target power {spec.target_power:.3f}."
    else:
        summary = "Target power was not reached within the declared search limit."
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=success,
        summary=summary,
        metrics=metrics,
        artifacts=[_relative(curve_path, output_root), _relative(figure_path, output_root)],
        figures=[_relative(figure_path, output_root)],
        warnings=warnings,
        claim_id=spec.claim_id,
    )
