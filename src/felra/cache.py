from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from importlib.metadata import PackageNotFoundError, version
from felra.analysis.models import AnalysisResult
from felra.config import AnalysisSpec, ProjectSpec
from felra.data import Dataset


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def analysis_fingerprint(
    spec: AnalysisSpec,
    project: ProjectSpec,
    datasets: dict[str, Dataset],
) -> str:
    dataset_hashes = {
        dataset_id: dataset.quality.source_sha256 for dataset_id, dataset in sorted(datasets.items())
    }
    try:
        felra_version = version("felra")
    except PackageNotFoundError:
        felra_version = "0.6.0"
    payload = {
        "felra_version": felra_version,
        "analysis": asdict(spec),
        "project": project.raw,
        "dataset_hashes": dataset_hashes,
        "execution_seed": project.execution.seed,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AnalysisCache:
    def __init__(self, root: Path, *, refresh: bool = False) -> None:
        self.root = root
        self.refresh = refresh
        self.root.mkdir(parents=True, exist_ok=True)

    def entry(self, fingerprint: str) -> Path:
        return self.root / fingerprint

    def restore(self, fingerprint: str, output_dir: Path) -> AnalysisResult | None:
        source = self.entry(fingerprint)
        metrics_path = source / "metrics.json"
        if self.refresh or not metrics_path.exists():
            return None
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(source, output_dir)
        payload = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
        metrics = dict(payload.get("metrics", {}))
        metrics["cache_hit"] = True
        metrics["cache_fingerprint"] = fingerprint
        return AnalysisResult(
            analysis_id=str(payload["id"]),
            kind=str(payload["type"]),
            title=str(payload["title"]),
            success=bool(payload["success"]),
            summary=str(payload["summary"]),
            metrics=metrics,
            artifacts=list(payload.get("artifacts", [])),
            figures=list(payload.get("figures", [])),
            warnings=list(payload.get("warnings", [])),
            claim_id=payload.get("claim_id"),
            created_at=str(payload.get("created_at", "")),
        )

    def store(self, fingerprint: str, output_dir: Path) -> None:
        target = self.entry(fingerprint)
        temporary = target.with_name(f"{target.name}.tmp")
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(output_dir, temporary)
        if target.exists():
            shutil.rmtree(target)
        temporary.replace(target)
