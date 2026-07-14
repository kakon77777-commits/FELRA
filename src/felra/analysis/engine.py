from __future__ import annotations

import json
from pathlib import Path

from felra.analysis.bootstrap import run_bootstrap_ci
from felra.analysis.models import AnalysisResult
from felra.analysis.pareto import run_pareto
from felra.analysis.residual import run_residual
from felra.analysis.sensitivity import run_sensitivity
from felra.analysis.statistics import run_descriptive, run_hypothesis_test
from felra.analysis.sweep import run_sweep
from felra.analysis.utils import jsonable
from felra.config import (
    AnalysisSpec,
    BootstrapCIAnalysisSpec,
    DescriptiveAnalysisSpec,
    HypothesisTestAnalysisSpec,
    ParetoAnalysisSpec,
    ProjectSpec,
    ResidualAnalysisSpec,
    SensitivityAnalysisSpec,
    SweepAnalysisSpec,
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
) -> AnalysisResult:
    output_dir = output_root / "analyses" / spec.analysis_id
    datasets = datasets or {}
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
    _write_result(result, output_dir)
    report_path = str((output_dir / "analysis_report.md").relative_to(output_root))
    metrics_path = str((output_dir / "metrics.json").relative_to(output_root))
    for path in (metrics_path, report_path):
        if path not in result.artifacts:
            result.artifacts.insert(0, path)
    # Rewrite once so the artifact index includes the report and metrics files themselves.
    _write_result(result, output_dir)
    return result
