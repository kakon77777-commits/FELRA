from __future__ import annotations

import csv
import json
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from felra.runner import ProjectRun, run_project


class BatchConfigError(ValueError):
    """Raised when a FELRA batch manifest is invalid."""


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    group_id: str
    replicate_index: int
    project_path: Path
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentResult:
    experiment_id: str
    group_id: str
    replicate_index: int
    success: bool
    passed: bool
    output_dir: str
    project_id: str | None = None
    claims_passed: bool | None = None
    analyses_succeeded: bool | None = None
    elapsed_seconds: float | None = None
    error: str | None = None


@dataclass
class BatchRun:
    batch_id: str
    title: str
    experiments: list[ExperimentResult]
    output_dir: Path
    workers: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return bool(self.experiments) and all(
            item.success and item.passed for item in self.experiments
        )


def _safe_id(value: str) -> str:
    if not value or value in {".", ".."} or any(separator in value for separator in ("/", "\\")):
        raise BatchConfigError(f"Unsafe experiment ID {value!r}")
    return value


def _set_path(mapping: dict[str, Any], dotted_path: str, value: Any) -> None:
    keys = dotted_path.split(".")
    if not all(keys):
        raise BatchConfigError(f"Invalid override path {dotted_path!r}")
    current: dict[str, Any] = mapping
    for key in keys[:-1]:
        existing = current.get(key)
        if existing is None:
            current[key] = {}
            existing = current[key]
        if not isinstance(existing, dict):
            raise BatchConfigError(
                f"Override path {dotted_path!r} crosses non-mapping field {key!r}"
            )
        current = existing
    current[keys[-1]] = value


def _expand_experiment(path: Path, item: dict[str, Any], index: int) -> list[ExperimentSpec]:
    if "project" not in item:
        raise BatchConfigError(f"Experiment {index} requires a project path")
    group_id = _safe_id(str(item.get("id", f"experiment_{index:03d}")))
    project_path = (path.parent / str(item["project"])).resolve()
    overrides = item.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise BatchConfigError(f"Experiment {group_id!r} overrides must be a mapping")
    base_overrides = {str(key): value for key, value in overrides.items()}
    repeat = item.get("repeat") or {}
    if not isinstance(repeat, dict):
        raise BatchConfigError(f"Experiment {group_id!r} repeat must be a mapping")
    count = int(repeat.get("count", 1))
    if count < 1:
        raise BatchConfigError("repeat.count must be positive")
    seed_path = str(repeat.get("seed_path", "execution.seed"))
    seed_start = int(repeat.get("seed_start", 0))
    seed_step = int(repeat.get("seed_step", 1))
    expanded: list[ExperimentSpec] = []
    for replicate in range(1, count + 1):
        experiment_id = group_id if count == 1 else f"{group_id}__r{replicate:03d}"
        replicate_overrides = dict(base_overrides)
        if count > 1 or "seed_start" in repeat:
            replicate_overrides[seed_path] = seed_start + (replicate - 1) * seed_step
        expanded.append(
            ExperimentSpec(
                experiment_id=experiment_id,
                group_id=group_id,
                replicate_index=replicate,
                project_path=project_path,
                overrides=replicate_overrides,
            )
        )
    return expanded


def _load_batch(path: Path) -> tuple[str, str, int, list[ExperimentSpec]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BatchConfigError("Batch YAML root must be a mapping")
    metadata = raw.get("batch") or {}
    batch_id = str(metadata.get("id", path.stem))
    title = str(metadata.get("title", batch_id))
    workers = int(metadata.get("workers", 1))
    if workers < 1:
        raise BatchConfigError("batch.workers must be positive")
    raw_experiments = raw.get("experiments")
    if not isinstance(raw_experiments, list) or not raw_experiments:
        raise BatchConfigError("Batch requires a non-empty experiments list")
    experiments: list[ExperimentSpec] = []
    group_ids: list[str] = []
    for index, item in enumerate(raw_experiments, start=1):
        if not isinstance(item, dict):
            raise BatchConfigError(f"Experiment {index} must be a mapping")
        expanded = _expand_experiment(path, item, index)
        group_ids.append(expanded[0].group_id)
        experiments.extend(expanded)
    if len(group_ids) != len(set(group_ids)):
        raise BatchConfigError("Experiment group IDs must be unique")
    ids = [item.experiment_id for item in experiments]
    if len(ids) != len(set(ids)):
        raise BatchConfigError("Expanded experiment IDs must be unique")
    return batch_id, title, workers, experiments


def _resolved_project(experiment: ExperimentSpec, resolved_dir: Path) -> Path:
    if not experiment.project_path.exists():
        raise FileNotFoundError(experiment.project_path)
    raw = yaml.safe_load(experiment.project_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BatchConfigError(f"Project {experiment.project_path} root must be a mapping")
    for path, value in experiment.overrides.items():
        _set_path(raw, path, value)
    raw_datasets = raw.get("datasets") or {}
    if isinstance(raw_datasets, dict):
        for dataset in raw_datasets.values():
            if isinstance(dataset, dict) and dataset.get("path"):
                dataset_path = Path(str(dataset["path"]))
                if not dataset_path.is_absolute():
                    dataset["path"] = str((experiment.project_path.parent / dataset_path).resolve())
    resolved_dir.mkdir(parents=True, exist_ok=True)
    destination = resolved_dir / f"{experiment.experiment_id}.yaml"
    destination.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return destination


def _execute_resolved(
    experiment: ExperimentSpec,
    project_file: Path,
    experiment_output: Path,
    output: Path,
) -> ExperimentResult:
    started = time.perf_counter()
    try:
        run: ProjectRun = run_project(project_file, experiment_output)
        return ExperimentResult(
            experiment_id=experiment.experiment_id,
            group_id=experiment.group_id,
            replicate_index=experiment.replicate_index,
            success=True,
            passed=run.passed,
            output_dir=str(experiment_output.relative_to(output)),
            project_id=run.project.project_id,
            claims_passed=run.claims_passed,
            analyses_succeeded=run.analyses_succeeded,
            elapsed_seconds=time.perf_counter() - started,
        )
    except Exception as exc:
        return ExperimentResult(
            experiment_id=experiment.experiment_id,
            group_id=experiment.group_id,
            replicate_index=experiment.replicate_index,
            success=False,
            passed=False,
            output_dir=str(experiment_output.relative_to(output)),
            elapsed_seconds=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_batch(
    batch_file: str | Path,
    output_dir: str | Path,
    *,
    workers: int | None = None,
) -> BatchRun:
    source = Path(batch_file).resolve()
    batch_id, title, configured_workers, experiments = _load_batch(source)
    worker_count = configured_workers if workers is None else int(workers)
    if worker_count < 1:
        raise BatchConfigError("workers must be positive")
    worker_count = min(worker_count, len(experiments))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[ExperimentSpec, Path, Path, Path]] = []
    for experiment in experiments:
        project_file = _resolved_project(experiment, output / "resolved_projects")
        experiment_output = output / "experiments" / experiment.experiment_id
        jobs.append((experiment, project_file, experiment_output, output))

    if worker_count == 1:
        results = [_execute_resolved(*job) for job in jobs]
    else:
        with ProcessPoolExecutor(
            max_workers=worker_count, mp_context=get_context("spawn")
        ) as executor:
            futures = [executor.submit(_execute_resolved, *job) for job in jobs]
            results = [future.result() for future in futures]
    order = {experiment.experiment_id: index for index, experiment in enumerate(experiments)}
    results.sort(key=lambda result: order[result.experiment_id])

    run = BatchRun(
        batch_id=batch_id,
        title=title,
        experiments=results,
        output_dir=output,
        workers=worker_count,
    )
    _write_batch_reports(run)
    return run


def _aggregate_groups(run: BatchRun) -> list[dict[str, Any]]:
    groups: dict[str, list[ExperimentResult]] = {}
    for result in run.experiments:
        groups.setdefault(result.group_id, []).append(result)
    summaries: list[dict[str, Any]] = []
    for group_id, items in groups.items():
        repetitions = len(items)
        successes = sum(item.success for item in items)
        passes = sum(item.success and item.passed for item in items)
        elapsed = [item.elapsed_seconds for item in items if item.elapsed_seconds is not None]
        summaries.append(
            {
                "group_id": group_id,
                "repetitions": repetitions,
                "execution_successes": successes,
                "passes": passes,
                "success_rate": successes / repetitions,
                "pass_rate": passes / repetitions,
                "mean_elapsed_seconds": sum(elapsed) / len(elapsed) if elapsed else None,
            }
        )
    return summaries


def _write_batch_reports(run: BatchRun) -> None:
    aggregates = _aggregate_groups(run)
    payload = {
        "batch": {"id": run.batch_id, "title": run.title},
        "created_at": run.created_at,
        "passed": run.passed,
        "workers": run.workers,
        "experiments": [result.__dict__ for result in run.experiments],
        "groups": aggregates,
    }
    (run.output_dir / "batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with (run.output_dir / "batch_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(ExperimentResult.__dataclass_fields__)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in run.experiments:
            writer.writerow(result.__dict__)

    with (run.output_dir / "replicate_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fieldnames = list(aggregates[0]) if aggregates else ["group_id"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(aggregates)

    lines = [
        f"# FELRA Batch Report — {run.title}",
        "",
        f"- Batch ID: `{run.batch_id}`",
        f"- Result: **{'PASS' if run.passed else 'ATTENTION REQUIRED'}**",
        f"- Generated at: `{run.created_at}`",
        f"- Expanded experiments: `{len(run.experiments)}`",
        f"- Parallel workers: `{run.workers}`",
        "",
        "## Replicate groups",
        "",
        "| Group | Repetitions | Success rate | Pass rate | Mean seconds |",
        "|---|---:|---:|---:|---:|",
    ]
    for summary in aggregates:
        mean_seconds = summary["mean_elapsed_seconds"]
        lines.append(
            f"| `{summary['group_id']}` | {summary['repetitions']} | "
            f"{summary['success_rate']:.3f} | {summary['pass_rate']:.3f} | "
            f"{mean_seconds:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Experiments",
            "",
            "| Experiment | Group | Replicate | Execution | Result | Claims | Analyses | Seconds | Output |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for result in run.experiments:
        elapsed = result.elapsed_seconds if result.elapsed_seconds is not None else float("nan")
        lines.append(
            f"| `{result.experiment_id}` | `{result.group_id}` | {result.replicate_index} | "
            f"{'PASS' if result.success else 'FAIL'} | {'PASS' if result.passed else 'FAIL'} | "
            f"{result.claims_passed if result.claims_passed is not None else '—'} | "
            f"{result.analyses_succeeded if result.analyses_succeeded is not None else '—'} | "
            f"{elapsed:.3f} | `{result.output_dir}` |"
        )
        if result.error:
            lines.append(f"\n> `{result.experiment_id}` error: `{result.error}`\n")
    lines.append("")
    (run.output_dir / "batch_report.md").write_text("\n".join(lines), encoding="utf-8")
