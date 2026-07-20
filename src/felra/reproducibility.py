from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in sorted(value.items())
            if key not in {"created_at", "cache_hit", "cache_fingerprint", "output_dir", "registry"}
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def result_payload(run: Any) -> dict[str, Any]:
    return {
        "project_id": run.project.project_id,
        "datasets": [
            {
                "id": dataset.spec.dataset_id,
                "rows": dataset.row_count,
                "normalized_sha256": hashlib.sha256(
                    (run.output_dir / "datasets" / dataset.spec.dataset_id / "normalized.csv").read_bytes()
                ).hexdigest(),
            }
            for dataset in run.datasets.values()
        ],
        "claims": [
            {
                "id": bundle.claim.claim_id,
                "passed": bundle.passed,
                "results": [
                    {
                        "check_name": result.check_name,
                        "passed": result.passed,
                        "metrics": _sanitize(result.metrics),
                        "counterexamples": _sanitize(list(result.counterexamples)),
                    }
                    for result in bundle.results
                ],
            }
            for bundle in run.bundles
        ],
        "analyses": [
            {
                "id": analysis.analysis_id,
                "type": analysis.kind,
                "success": analysis.success,
                "metrics": _sanitize(analysis.metrics),
                "warnings": list(analysis.warnings),
            }
            for analysis in run.analyses
        ],
    }


def result_sha256(run: Any) -> str:
    payload = json.dumps(result_payload(run), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_replay_project(run: Any) -> Path:
    raw = json.loads(json.dumps(run.project.raw, ensure_ascii=False))
    for dataset_id, dataset_config in (raw.get("datasets") or {}).items():
        dataset_config["path"] = f"datasets/{dataset_id}/normalized.csv"
        dataset_config["format"] = "csv"
        dataset_config["encoding"] = "utf-8"
        dataset_config["delimiter"] = ","
        dataset_config["on_error"] = "error"
    raw["registry"] = {"enabled": False}
    raw["preregistration"] = {"enabled": False}
    execution = raw.setdefault("execution", {})
    execution["cache"] = False
    execution["refresh_cache"] = False
    path = run.output_dir / "replay_project.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def compare_manifests(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_digest = expected.get("result_sha256")
    actual_digest = actual.get("result_sha256")
    return {
        "matched": bool(expected_digest and expected_digest == actual_digest),
        "expected_result_sha256": expected_digest,
        "actual_result_sha256": actual_digest,
        "expected_project_id": (expected.get("project") or {}).get("id"),
        "actual_project_id": (actual.get("project") or {}).get("id"),
    }


def replay_run(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    from felra.runner import run_project

    manifest_path = run_dir / "manifest.json"
    replay_project_path = run_dir / "replay_project.yaml"
    if not manifest_path.exists() or not replay_project_path.exists():
        raise FileNotFoundError("Run directory requires manifest.json and replay_project.yaml")
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    if output_dir.exists():
        shutil.rmtree(output_dir)
    run_project(replay_project_path, output_dir)
    actual = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    result = compare_manifests(expected, actual)
    result["source_run"] = str(run_dir.resolve())
    result["replay_run"] = str(output_dir.resolve())
    (output_dir / "replay_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result
