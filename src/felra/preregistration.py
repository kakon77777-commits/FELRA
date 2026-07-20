from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from felra.config import ProjectSpec


class PreregistrationError(RuntimeError):
    """Raised when a strict preregistration contract is missing or violated."""


@dataclass(frozen=True)
class PreregistrationVerification:
    status: str
    matched: bool
    expected_sha256: str | None
    actual_sha256: str
    path: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "matched": self.matched,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "path": self.path,
            "message": self.message,
        }


def _canonical_plan(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the scientific plan while excluding operational output settings."""
    plan = copy.deepcopy(raw)
    plan.pop("registry", None)
    plan.pop("preregistration", None)

    execution = plan.get("execution")
    if isinstance(execution, dict):
        for key in ("cache", "cache_dir", "refresh_cache"):
            execution.pop(key, None)
        if not execution:
            plan.pop("execution", None)
    return plan


def canonical_plan_json(raw: dict[str, Any]) -> str:
    return json.dumps(_canonical_plan(raw), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def plan_sha256(raw: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_plan_json(raw).encode("utf-8")).hexdigest()


def _dataset_declarations(project: ProjectSpec) -> list[dict[str, Any]]:
    return [
        {
            "id": dataset.dataset_id,
            "path": str(dataset.path),
            "format": dataset.format,
            "columns": {
                name: {"type": column.kind, "required": column.required}
                for name, column in dataset.columns.items()
            },
        }
        for dataset in project.datasets.values()
    ]


def create_preregistration_record(project: ProjectSpec) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project.project_id,
        "project_title": project.title,
        "source_path": project.source_path.name if project.source_path else None,
        "plan_sha256": plan_sha256(project.raw),
        "canonical_plan": _canonical_plan(project.raw),
        "dataset_declarations": _dataset_declarations(project),
        "statement": (
            "This record locks the declared scientific plan. It does not prove that the plan is "
            "valid, unbiased, or sufficient."
        ),
    }


def write_preregistration(project: ProjectSpec, path: Path, *, replace: bool = False) -> dict[str, Any]:
    if path.exists() and not replace:
        raise FileExistsError(f"Preregistration already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = create_preregistration_record(project)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def load_preregistration(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Preregistration record must be a JSON object")
    if not isinstance(payload.get("plan_sha256"), str):
        raise ValueError("Preregistration record is missing plan_sha256")
    return payload


def verify_preregistration(project: ProjectSpec, path: Path) -> PreregistrationVerification:
    actual = plan_sha256(project.raw)
    if not path.exists():
        return PreregistrationVerification(
            status="missing",
            matched=False,
            expected_sha256=None,
            actual_sha256=actual,
            path=str(path),
            message="No preregistration record exists at the configured path.",
        )
    record = load_preregistration(path)
    expected = str(record["plan_sha256"])
    matched = expected == actual
    return PreregistrationVerification(
        status="matched" if matched else "mismatch",
        matched=matched,
        expected_sha256=expected,
        actual_sha256=actual,
        path=str(path),
        message=(
            "The current scientific plan matches the preregistered plan."
            if matched
            else "The current scientific plan differs from the preregistered plan."
        ),
    )
