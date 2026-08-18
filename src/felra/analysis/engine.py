from __future__ import annotations

import json
from pathlib import Path

from felra.analysis.bootstrap import run_bootstrap_ci
from felra.analysis.cross_method import run_cross_method
from felra.analysis.cross_backend import run_cross_backend
from felra.analysis.precision_ladder import run_precision_ladder
from felra.analysis.formal_check import run_formal_check
from felra.analysis.cross_validation import run_cross_validation, run_model_comparison
from felra.analysis.models import AnalysisResult
from felra.analysis.multiple_comparisons import run_multiple_comparisons
from felra.analysis.numerical_soundness import run_numerical_soundness
from felra.analysis.pareto import run_pareto
from felra.analysis.power import run_power_analysis
from felra.analysis.residual import run_residual
from felra.analysis.robustness import run_robustness
from felra.analysis.sensitivity import run_sensitivity
from felra.analysis.statistics import run_descriptive, run_hypothesis_test
from felra.analysis.sweep import run_sweep
from felra.analysis.symbolic import run_symbolic
from felra.analysis.utils import jsonable
from felra.cache import AnalysisCache, analysis_fingerprint
from felra.config import (
    AnalysisSpec,
    BootstrapCIAnalysisSpec,
    CrossBackendAnalysisSpec,
    PrecisionLadderAnalysisSpec,
    CrossMethodAnalysisSpec,
    FormalCheckAnalysisSpec,
    CrossValidationAnalysisSpec,
    DescriptiveAnalysisSpec,
    HypothesisTestAnalysisSpec,
    ModelComparisonAnalysisSpec,
    MultipleComparisonAnalysisSpec,
    NumericalSoundnessAnalysisSpec,
    ParetoAnalysisSpec,
    PowerAnalysisSpec,
    ProjectSpec,
    ResidualAnalysisSpec,
    RobustnessAnalysisSpec,
    SensitivityAnalysisSpec,
    SweepAnalysisSpec,
    SymbolicAnalysisSpec,
)
from felra.data import Dataset


def _write_result(result: AnalysisResult, output_dir: Path) -> None:
    payload = {
        "id": result.analysis_id,
        "type": result.kind,
        "title": result.title,
        "success": result.success,
        "summary": result.summary,
        "claim_id": result.claim_id,
        "created_at": result.created_at,
        "metrics": jsonable(result.metrics),
        "artifacts": result.artifacts,
        "figures": result.figures,
        "warnings": result.warnings,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"# FELRA Analysis Report — {result.title}",
        "",
        f"- Analysis ID: `{result.analysis_id}`",
        f"- Type: `{result.kind}`",
        f"- Execution success: `{result.success}`",
        f"- Summary: {result.summary}",
        f"- Generated at: `{result.created_at}`",
        "",
        "> Analysis outputs are finite-budget computational evidence and diagnostics.",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(jsonable(result.metrics), ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    if result.artifacts:
        lines.extend(["## Artifacts", ""])
        lines.extend(f"- `{path}`" for path in result.artifacts)
        lines.append("")
    if result.warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in result.warnings)
        lines.append("")
    (output_dir / "analysis_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_analysis(
    spec: AnalysisSpec,
    project: ProjectSpec,
    output_root: Path,
    datasets: dict[str, Dataset] | None = None,
    cache: AnalysisCache | None = None,
) -> AnalysisResult:
    output_dir = output_root / "analyses" / spec.analysis_id
    datasets = datasets or {}
    fingerprint = analysis_fingerprint(spec, project, datasets)
    if cache is not None:
        restored = cache.restore(fingerprint, output_dir)
        if restored is not None:
            _write_result(restored, output_dir)
            return restored
    try:
        if isinstance(spec, SensitivityAnalysisSpec):
            result = run_sensitivity(spec, project, output_dir, output_root)
        elif isinstance(spec, ResidualAnalysisSpec):
            result = run_residual(spec, project, output_dir, output_root)
        elif isinstance(spec, SweepAnalysisSpec):
            result = run_sweep(spec, project, output_dir, output_root)
        elif isinstance(spec, ParetoAnalysisSpec):
            result = run_pareto(spec, project, output_dir, output_root)
        elif isinstance(spec, DescriptiveAnalysisSpec):
            result = run_descriptive(spec, datasets[spec.dataset], output_dir, output_root)
        elif isinstance(spec, HypothesisTestAnalysisSpec):
            result = run_hypothesis_test(spec, datasets[spec.dataset], output_dir, output_root)
        elif isinstance(spec, BootstrapCIAnalysisSpec):
            result = run_bootstrap_ci(
                spec,
                datasets[spec.dataset],
                output_dir,
                output_root,
                default_seed=project.execution.seed,
            )
        elif isinstance(spec, PowerAnalysisSpec):
            result = run_power_analysis(spec, output_dir, output_root)
        elif isinstance(spec, RobustnessAnalysisSpec):
            result = run_robustness(
                spec,
                datasets[spec.dataset],
                output_dir,
                output_root,
                default_seed=project.execution.seed,
            )
        elif isinstance(spec, MultipleComparisonAnalysisSpec):
            result = run_multiple_comparisons(
                spec, datasets[spec.dataset], output_dir, output_root
            )
        elif isinstance(spec, CrossValidationAnalysisSpec):
            result = run_cross_validation(
                spec,
                datasets[spec.dataset],
                output_dir,
                output_root,
                default_seed=project.execution.seed,
            )
        elif isinstance(spec, ModelComparisonAnalysisSpec):
            result = run_model_comparison(
                spec,
                datasets[spec.dataset],
                output_dir,
                output_root,
                default_seed=project.execution.seed,
            )
        elif isinstance(spec, SymbolicAnalysisSpec):
            result = run_symbolic(spec, output_dir, output_root)
        elif isinstance(spec, NumericalSoundnessAnalysisSpec):
            result = run_numerical_soundness(spec, project, output_dir, output_root)
        elif isinstance(spec, CrossMethodAnalysisSpec):
            result = run_cross_method(spec, project, output_dir, output_root)
        elif isinstance(spec, PrecisionLadderAnalysisSpec):
            result = run_precision_ladder(spec, output_dir=output_dir)
        elif isinstance(spec, CrossBackendAnalysisSpec):
            result = run_cross_backend(spec, output_dir=output_dir)
        elif isinstance(spec, FormalCheckAnalysisSpec):
            # Paths in a formal_check are relative to the project file, not to the
            # process working directory, so a project stays portable.
            base_dir = (
                project.source_path.parent
                if project.source_path is not None
                else Path.cwd()
            )
            result = run_formal_check(spec, base_dir=base_dir, output_dir=output_dir)
        else:  # pragma: no cover - exhaustive type guard
            raise TypeError(f"Unsupported analysis spec {type(spec).__name__}")
    except Exception as exc:
        output_dir.mkdir(parents=True, exist_ok=True)
        result = AnalysisResult(
            analysis_id=spec.analysis_id,
            kind=spec.kind,
            title=spec.title,
            success=False,
            summary=f"Analysis failed: {type(exc).__name__}: {exc}",
            warnings=[f"{type(exc).__name__}: {exc}"],
            claim_id=spec.claim_id,
        )
    result.metrics.setdefault("cache_hit", False)
    result.metrics.setdefault("cache_fingerprint", fingerprint)
    _write_result(result, output_dir)
    report_path = str((output_dir / "analysis_report.md").relative_to(output_root))
    metrics_path = str((output_dir / "metrics.json").relative_to(output_root))
    for path in (metrics_path, report_path):
        if path not in result.artifacts:
            result.artifacts.insert(0, path)
    # Rewrite once so the artifact index includes the report and metrics files themselves.
    _write_result(result, output_dir)
    if cache is not None:
        cache.store(fingerprint, output_dir)
    return result
