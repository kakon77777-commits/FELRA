from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from importlib.metadata import PackageNotFoundError, version

from felra.reproducibility import result_sha256


def resolve_registry_path(configured_path: str, project_path: Path | None) -> Path:
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        base = project_path.parent if project_path is not None else Path.cwd()
        path = (base / path).resolve()
    return path


def append_registry_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_registry_record(run: Any, config_sha256: str) -> dict[str, Any]:
    try:
        felra_version = version("felra")
    except PackageNotFoundError:
        felra_version = "0.7.0"
    identity = f"{run.project.project_id}|{config_sha256}|{run.created_at}".encode("utf-8")
    run_id = hashlib.sha256(identity).hexdigest()[:20]
    return {
        "registry_version": 1,
        "run_id": run_id,
        "created_at": run.created_at,
        "felra_version": felra_version,
        "project_id": run.project.project_id,
        "project_title": run.project.title,
        "config_sha256": config_sha256,
        "result_sha256": result_sha256(run),
        "preregistration": run.preregistration,
        "source_path": str(run.project.source_path) if run.project.source_path else None,
        "output_dir": str(run.output_dir.resolve()),
        "passed": run.passed,
        "claims_passed": run.claims_passed,
        "analyses_succeeded": run.analyses_succeeded,
        "tags": list(run.project.registry.tags),
        "notes": run.project.registry.notes,
        "datasets": [
            {
                "id": dataset.spec.dataset_id,
                "rows": dataset.row_count,
                "source_sha256": dataset.quality.source_sha256,
            }
            for dataset in run.datasets.values()
        ],
        "analyses": [
            {
                "id": analysis.analysis_id,
                "type": analysis.kind,
                "success": analysis.success,
                "cache_hit": bool(analysis.metrics.get("cache_hit", False)),
            }
            for analysis in run.analyses
        ],
        "warnings": list(run.warnings),
    }


def load_registry_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid registry JSON on line {line_number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Registry line {line_number} must contain a JSON object")
        records.append(payload)
    return records


def filter_registry_records(
    records: Iterable[dict[str, Any]],
    *,
    project_id: str | None = None,
    passed: bool | None = None,
) -> list[dict[str, Any]]:
    result = []
    for record in records:
        if project_id is not None and record.get("project_id") != project_id:
            continue
        if passed is not None and bool(record.get("passed")) is not passed:
            continue
        result.append(record)
    return result
