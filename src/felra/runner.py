from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import scipy
import yaml

from felra.analysis import AnalysisResult, run_analysis
from felra.cache import AnalysisCache
from felra.config import FigureSpec, ProjectSpec, load_project
from felra.data import Dataset, load_dataset, write_dataset_evidence
from felra.evidence import write_evidence_bundle
from felra.expressions import evaluate_expression
from felra.figures import FigureFactory
from felra.models import Claim, EvidenceBundle
from felra.preregistration import PreregistrationError, verify_preregistration
from felra.provenance import build_provenance, write_provenance
from felra.numeric_policy import describe_numeric_environment, evidence_status
from felra.reproducibility import result_sha256, write_replay_project
from felra.registry import append_registry_record, build_registry_record, resolve_registry_path
from felra.sampling import (
    SampleSet,
    build_boundary_samples,
    build_declared_samples,
    build_random_samples,
    parameter_axis,
)
from felra.validation.expression import validate_expression_predicate


@dataclass
class ProjectRun:
    project: ProjectSpec
    bundles: list[EvidenceBundle]
    output_dir: Path
    datasets: dict[str, Dataset] = field(default_factory=dict)
    figures: list[str] = field(default_factory=list)
    analyses: list[AnalysisResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    registry_record: dict[str, Any] | None = None
    preregistration: dict[str, Any] | None = None
    provenance_artifacts: list[str] = field(default_factory=list)
    replay_project: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def claims_passed(self) -> bool:
        return all(bundle.passed for bundle in self.bundles)

    @property
    def analyses_succeeded(self) -> bool:
        return all(analysis.success for analysis in self.analyses)

    @property
    def passed(self) -> bool:
        return bool(self.bundles or self.analyses) and self.claims_passed and self.analyses_succeeded


def _config_hash(project: ProjectSpec) -> str:
    payload = yaml.safe_dump(project.raw, allow_unicode=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parameter_domain_description(project: ProjectSpec) -> str:
    fragments = []
    for name, spec in project.parameters.items():
        if spec.values:
            fragments.append(f"{name} in explicit set of {len(spec.values)} values")
        else:
            fragments.append(
                f"{name} in [{spec.minimum}, {spec.maximum}] with {spec.samples} declared samples"
            )
    return "; ".join(fragments)


def _fixed_context(project: ProjectSpec, varying: set[str]) -> dict[str, float | int]:
    context: dict[str, float | int] = {}
    for name, spec in project.parameters.items():
        if name in varying:
            continue
        axis = parameter_axis(spec)
        context[name] = axis[len(axis) // 2].item()
    return context


def _make_figure(factory: FigureFactory, figure: FigureSpec, project: ProjectSpec) -> Path:
    if figure.kind in {"line", "scatter"}:
        if not figure.x or not figure.y:
            raise ValueError(f"Figure {figure.figure_id!r} requires x and y expressions")
        if figure.x not in project.parameters:
            raise ValueError("Line and scatter x must name a declared parameter")
        x_values = parameter_axis(project.parameters[figure.x])
        context: dict[str, Any] = _fixed_context(project, {figure.x})
        context[figure.x] = x_values
        y_values = np.asarray(evaluate_expression(figure.y, context), dtype=float)
        method = factory.line_plot if figure.kind == "line" else factory.scatter_plot
        return method(
            x_values,
            y_values,
            title=figure.title,
            xlabel=figure.xlabel or figure.x,
            ylabel=figure.ylabel or figure.y,
            filename=figure.filename,
        )

    if figure.kind == "histogram":
        expression = figure.y or figure.x
        if not expression:
            raise ValueError(f"Figure {figure.figure_id!r} requires x or y expression")
        if not project.parameters:
            raise ValueError("Declarative histogram requires parameters")
        samples = build_declared_samples(
            project.parameters,
            max_evaluations=project.execution.max_evaluations,
            seed=project.execution.seed,
        )
        values = np.asarray(evaluate_expression(expression, samples.variables), dtype=float).reshape(-1)
        return factory.histogram(
            values,
            title=figure.title,
            xlabel=figure.xlabel or expression,
            ylabel=figure.ylabel or "Frequency",
            bins=figure.bins,
            filename=figure.filename,
        )

    if figure.kind in {"heatmap", "contour", "phase_map"}:
        if not figure.x or not figure.y or not figure.z:
            raise ValueError(f"Figure {figure.figure_id!r} requires x, y, and z")
        if figure.x not in project.parameters or figure.y not in project.parameters:
            raise ValueError("Heatmap axes must name declared parameters")
        x_axis = parameter_axis(project.parameters[figure.x])
        y_axis = parameter_axis(project.parameters[figure.y])
        x_mesh, y_mesh = np.meshgrid(x_axis, y_axis, indexing="xy")
        context = _fixed_context(project, {figure.x, figure.y})
        context[figure.x] = x_mesh
        context[figure.y] = y_mesh
        z_values = np.asarray(evaluate_expression(figure.z, context))
        common = dict(
            title=figure.title,
            xlabel=figure.xlabel or figure.x,
            ylabel=figure.ylabel or figure.y,
            filename=figure.filename,
        )
        if figure.kind == "heatmap":
            return factory.heatmap(x_axis, y_axis, z_values.astype(float), **common)
        if figure.kind == "contour":
            return factory.contour_plot(x_axis, y_axis, z_values.astype(float), **common)
        return factory.phase_map(x_axis, y_axis, z_values.astype(bool), **common)

    raise ValueError(f"Unsupported figure type {figure.kind!r}")


def _parameter_samples(project: ProjectSpec) -> dict[str, SampleSet]:
    if not project.parameters:
        return {}
    return {
        "numerical": build_declared_samples(
            project.parameters,
            max_evaluations=project.execution.max_evaluations,
            seed=project.execution.seed,
        ),
        "boundaries": build_boundary_samples(project.parameters),
        "counterexample_search": build_random_samples(
            project.parameters,
            sample_count=project.execution.random_samples,
            seed=project.execution.seed + 1,
        ),
    }


def run_project(project_file: str | Path, output_dir: str | Path) -> ProjectRun:
    project = load_project(project_file)
    preregistration: dict[str, Any] | None = None
    preregistration_warning: str | None = None
    if project.preregistration.enabled:
        prereg_path = Path(project.preregistration.path).expanduser()
        if not prereg_path.is_absolute():
            base_dir = project.source_path.parent if project.source_path else Path.cwd()
            prereg_path = (base_dir / prereg_path).resolve()
        verification = verify_preregistration(project, prereg_path)
        preregistration = verification.to_dict()
        if not verification.matched:
            if project.preregistration.mode == "strict":
                raise PreregistrationError(verification.message)
            preregistration_warning = f"Preregistration {verification.status}: {verification.message}"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "claims").mkdir(exist_ok=True)
    (output / "analyses").mkdir(exist_ok=True)
    (output / "datasets").mkdir(exist_ok=True)
    figure_factory = FigureFactory(output / "figures")

    datasets = {dataset_id: load_dataset(spec) for dataset_id, spec in project.datasets.items()}
    cache: AnalysisCache | None = None
    if project.execution.cache:
        cache_path = Path(project.execution.cache_dir).expanduser()
        if not cache_path.is_absolute():
            base_dir = project.source_path.parent if project.source_path else Path.cwd()
            cache_path = (base_dir / cache_path).resolve()
        cache = AnalysisCache(cache_path, refresh=project.execution.refresh_cache)
    warnings: list[str] = []
    if preregistration_warning:
        warnings.append(preregistration_warning)
    for dataset in datasets.values():
        write_dataset_evidence(dataset, output)
        warnings.extend(
            f"Dataset {dataset.spec.dataset_id}: {warning}"
            for warning in dataset.quality.warnings
        )

    parameter_samples = _parameter_samples(project)
    bundles: list[EvidenceBundle] = []
    for claim_spec in project.claims:
        if claim_spec.dataset:
            dataset = datasets[claim_spec.dataset]
            domain_description = (
                f"all {dataset.row_count} normalized rows from dataset {claim_spec.dataset!r}"
            )
            check_samples = {"dataset_rows": dataset.sample_set()}
        else:
            domain_description = _parameter_domain_description(project)
            check_samples = parameter_samples
        claim = Claim(
            claim_id=claim_spec.claim_id,
            statement=claim_spec.statement,
            status=claim_spec.status,
            domain_description=domain_description,
        )
        results = [
            validate_expression_predicate(
                claim_spec.expression,
                check_samples[check],
                check_name=check,
                max_counterexamples=claim_spec.max_counterexamples,
            )
            for check in claim_spec.required_checks
        ]
        metadata: dict[str, Any] = {
            "expression": claim_spec.expression,
            "project_id": project.project_id,
            "config_sha256": _config_hash(project),
            "seed": project.execution.seed,
        }
        if claim_spec.dataset:
            metadata["dataset"] = claim_spec.dataset
            metadata["dataset_sha256"] = datasets[claim_spec.dataset].quality.source_sha256
        bundles.append(EvidenceBundle(claim=claim, results=results, metadata=metadata))

    generated_figures: list[str] = []
    for figure in project.figures:
        try:
            path = _make_figure(figure_factory, figure, project)
        except Exception as exc:
            warnings.append(f"Figure {figure.figure_id}: {type(exc).__name__}: {exc}")
            continue
        relative = str(path.relative_to(output))
        generated_figures.append(relative)
        for bundle in bundles:
            if figure.claim_id is None or figure.claim_id == bundle.claim.claim_id:
                bundle.figures.append(relative)

    analysis_results = [
        run_analysis(spec, project, output, datasets=datasets, cache=cache)
        for spec in project.analyses
    ]
    for analysis in analysis_results:
        warnings.extend(
            f"Analysis {analysis.analysis_id}: {warning}" for warning in analysis.warnings
        )
        if not analysis.success and not analysis.warnings:
            warnings.append(f"Analysis {analysis.analysis_id} did not complete successfully.")
        if analysis.claim_id:
            for bundle in bundles:
                if bundle.claim.claim_id == analysis.claim_id:
                    bundle.figures.extend(
                        figure for figure in analysis.figures if figure not in bundle.figures
                    )
                    bundle.metadata.setdefault("analyses", []).append(
                        {
                            "id": analysis.analysis_id,
                            "type": analysis.kind,
                            "success": analysis.success,
                            "report": f"analyses/{analysis.analysis_id}/analysis_report.md",
                        }
                    )

    for bundle in bundles:
        write_evidence_bundle(bundle, output / "claims" / bundle.claim.claim_id)

    (output / "project_snapshot.yaml").write_text(
        yaml.safe_dump(project.raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    run = ProjectRun(
        project=project,
        bundles=bundles,
        output_dir=output,
        datasets=datasets,
        figures=generated_figures,
        analyses=analysis_results,
        warnings=warnings,
        preregistration=preregistration,
    )
    if preregistration is not None:
        (output / "preregistration_verification.json").write_text(
            json.dumps(preregistration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    replay_path = write_replay_project(run)
    run.replay_project = str(replay_path.relative_to(output))
    provenance_payload = build_provenance(run, _config_hash(project))
    run.provenance_artifacts = write_provenance(provenance_payload, output)
    if project.registry.enabled:
        registry_path = resolve_registry_path(project.registry.path, project.source_path)
        record = build_registry_record(run, _config_hash(project))
        append_registry_record(registry_path, record)
        run.registry_record = {**record, "registry_path": str(registry_path)}
        (output / "registry_record.json").write_text(
            json.dumps(run.registry_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    _write_project_manifest(run)
    return run


def _formal_results(run: ProjectRun) -> list[dict[str, Any]]:
    return [
        analysis.metrics
        for analysis in run.analyses
        if analysis.kind == "formal_check" and analysis.metrics.get("formal_status")
    ]


def _numeric_section(run: ProjectRun) -> dict[str, Any] | None:
    policy = getattr(run.project, "numeric_policy", None)
    if policy is None:
        return None
    section = policy.as_dict()
    section["environment"] = describe_numeric_environment()
    section["conversion_history"] = []
    section["note"] = (
        "stage A records the policy; it does not change how anything is computed. "
        "`declared_but_not_implemented` lists what this version does not yet honour."
    )
    return section


def _evidence_section(run: ProjectRun) -> dict[str, Any]:
    # `falsified` is section 11's F: 發現有效反例 — a counterexample was found.
    # It was briefly driven by `not run.passed`, which conflates "some analysis
    # did not meet its declared expectation" with "the claim is refuted". A
    # cross-backend inconsistency is a finding about REPRESENTATIONS, not a
    # counterexample to the claim, and reporting it as `falsified` would put a
    # verdict on the mathematics that the run never reached. Caught by running
    # this against the Collatz anchor project, where a deliberate float64
    # disagreement was reported as though the claim had been refuted.
    refuted = any(
        not bundle.passed and any(result.counterexamples for result in bundle.results)
        for bundle in run.bundles
    )
    ladders = [a for a in run.analyses if a.kind == "precision_ladder"]
    backends = [a for a in run.analyses if a.kind == "cross_backend"]
    return evidence_status(
        executed=True,
        reproduced=None,
        precision_stable=(all(a.success for a in ladders) if ladders else None),
        cross_backend_consistent=(all(a.success for a in backends)
                                  if backends else None),
        exact_verified=(
            all(a.metrics.get("exactness") == "exact_on_every_point"
                for a in backends) if backends else None),
        formal_results=_formal_results(run),
        falsified=refuted,
    )

def _write_project_manifest(run: ProjectRun) -> None:
    environment = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }
    try:
        from felra import __version__ as felra_version
    except ImportError:  # pragma: no cover
        felra_version = "unknown"
    environment["felra"] = felra_version
    payload: dict[str, Any] = {
        "project": {
            "id": run.project.project_id,
            "title": run.project.title,
            "language": run.project.language,
        },
        "created_at": run.created_at,
        "passed": run.passed,
        "claims_passed": run.claims_passed,
        "analyses_succeeded": run.analyses_succeeded,
        "config_sha256": _config_hash(run.project),
        "result_sha256": result_sha256(run),
        "environment": environment,
        # Stage A governance. Absent unless a policy was declared, so a project
        # that predates v1.2.0 produces a byte-identical manifest shape and an
        # unchanged result_sha256 (addendum 17.1, 17.3).
        "numeric": _numeric_section(run),
        "evidence_status": _evidence_section(run),
        "preregistration": run.preregistration,
        "replay_project": run.replay_project,
        "provenance": run.provenance_artifacts,
        "datasets": [
            {
                "id": dataset.spec.dataset_id,
                "rows": dataset.row_count,
                "source_sha256": dataset.quality.source_sha256,
                "report": f"datasets/{dataset.spec.dataset_id}/dataset_report.md",
                "quality": f"datasets/{dataset.spec.dataset_id}/quality.json",
                "normalized": f"datasets/{dataset.spec.dataset_id}/normalized.csv",
            }
            for dataset in run.datasets.values()
        ],
        "claims": [
            {
                "id": bundle.claim.claim_id,
                "passed": bundle.passed,
                "report": f"claims/{bundle.claim.claim_id}/validation_report.md",
                "metrics": f"claims/{bundle.claim.claim_id}/metrics.json",
            }
            for bundle in run.bundles
        ],
        "analyses": [
            {
                "id": analysis.analysis_id,
                "type": analysis.kind,
                "success": analysis.success,
                "cache_hit": bool(analysis.metrics.get("cache_hit", False)),
                "cache_fingerprint": analysis.metrics.get("cache_fingerprint"),
                "report": f"analyses/{analysis.analysis_id}/analysis_report.md",
                "metrics": f"analyses/{analysis.analysis_id}/metrics.json",
                "artifacts": analysis.artifacts,
            }
            for analysis in run.analyses
        ],
        "figures": run.figures,
        "warnings": run.warnings,
        "registry": run.registry_record,
    }
    (run.output_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# FELRA Project Report — {run.project.title}",
        "",
        f"- Project ID: `{run.project.project_id}`",
        f"- Overall result: **{'PASS' if run.passed else 'ATTENTION REQUIRED'}**",
        f"- Claims supported in declared domain: `{run.claims_passed}`",
        f"- Analyses completed successfully: `{run.analyses_succeeded}`",
        f"- Generated at: `{run.created_at}`",
        f"- Configuration SHA-256: `{_config_hash(run.project)}`",
        f"- Result SHA-256: `{result_sha256(run)}`",
        "",
        "> All results are finite-budget computational evidence, not universal proofs.",
        "",
    ]
    if run.preregistration:
        lines.extend(["## Preregistration", ""])
        lines.append(f"- Status: `{run.preregistration['status']}`")
        lines.append(f"- Matched: `{run.preregistration['matched']}`")
        lines.append(f"- Record: `{run.preregistration['path']}`")
        lines.append("")
    if run.datasets:
        lines.extend(["## Datasets", ""])
        for dataset in run.datasets.values():
            lines.append(
                f"- `{dataset.spec.dataset_id}` — {dataset.row_count} normalized rows "
                f"([report](datasets/{dataset.spec.dataset_id}/dataset_report.md))"
            )
        lines.append("")
    if run.bundles:
        lines.extend(["## Claims", ""])
        for bundle in run.bundles:
            status = "PASS" if bundle.passed else "FAIL"
            lines.append(
                f"- **{status}** `{bundle.claim.claim_id}` — {bundle.claim.statement} "
                f"([report](claims/{bundle.claim.claim_id}/validation_report.md))"
            )
    if run.analyses:
        lines.extend(["", "## Analyses", ""])
        for analysis in run.analyses:
            status = "PASS" if analysis.success else "FAIL"
            lines.append(
                f"- **{status}** `{analysis.analysis_id}` — {analysis.title} "
                f"([report](analyses/{analysis.analysis_id}/analysis_report.md))"
            )
    if run.figures:
        lines.extend(["", "## Declarative figures", ""])
        lines.extend(f"- `{path}`" for path in run.figures)
    if run.registry_record:
        lines.extend(["", "## Experiment registry", ""])
        lines.append(f"- Run ID: `{run.registry_record['run_id']}`")
        lines.append(f"- Registry: `{run.registry_record['registry_path']}`")
        lines.append("- Local record: `registry_record.json`")
    lines.extend(["", "## Reproducibility", ""])
    lines.append(f"- Replay project: `{run.replay_project}`")
    lines.extend(f"- Provenance artifact: `{path}`" for path in run.provenance_artifacts)
    if run.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in run.warnings)
    lines.append("")
    (run.output_dir / "project_report.md").write_text("\n".join(lines), encoding="utf-8")
