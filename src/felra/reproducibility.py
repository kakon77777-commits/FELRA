from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml


#: Keys excluded from the fingerprint because they record **when or where a run
#: happened**, not **what it computed**.
#:
#: `duration_seconds` and the path keys were added in v1.8.0, after measuring that
#: `felra replay` reported MISMATCH on an *unmodified* formal project. A solver
#: returning the same verdict in 24ms on one run and 25ms on the next is not
#: nondeterminism; the mismatch was manufactured here, by putting a stopwatch
#: reading inside an identity. Every formal analysis had been unreproducible since
#: v1.1.0 for that reason alone.
#:
#: Dropping the paths costs nothing, because what a path was for — saying *which*
#: obligation the solver read — is carried better by the `sha256` recorded beside
#: it. A content hash survives being moved; a path does not.
#:
#: This list is a denylist, and a denylist only knows what someone remembered to
#: add — which is exactly how `duration_seconds` slipped in for seven versions. So
#: it is not the guard. The guard is `test_fingerprints_are_stable_across_runs`,
#: which runs real projects twice and compares, and would have caught this on the
#: day it was introduced without anyone having to think of the key's name.
_NOT_PART_OF_THE_RESULT = frozenset({
    "created_at", "cache_hit", "cache_fingerprint", "output_dir", "registry",
    "duration_seconds",                     # wall clock
    "path", "executable_path", "obligation_file", "twin_file",  # location
})


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in sorted(value.items())
            if key not in _NOT_PART_OF_THE_RESULT
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


def _numeric_policy_digest(run: Any) -> str | None:
    """The declared policy's digest, or None when nothing was declared.

    This is the whole of addendum 17.3/17.4 in one function. A project with no
    `numeric_policy` contributes NOTHING to the payload, so its result_sha256 is
    byte-identical to what it was before this layer existed; a project that
    declares one, or changes one, gets a different digest and therefore a
    different result hash even when the numbers are unchanged. A run under a
    different declared policy is a different run.
    """
    policy = getattr(getattr(run, "project", None), "numeric_policy", None)
    return policy.digest() if policy is not None else None


def result_sha256(run: Any) -> str:
    body = result_payload(run)
    digest = _numeric_policy_digest(run)
    if digest is not None:
        body = dict(body)
        body["numeric_policy_sha256"] = digest
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _capture_obligations(run: Any, raw: dict[str, Any]) -> list[str]:
    """Copy each declared formal obligation into the run, the way datasets are.

    Datasets have always been captured: the replay project points at the run's own
    normalized copy, so a replay reproduces *that run* rather than whatever the
    source file happens to say later. Formal obligations were not, and the
    consequence was not a subtle drift — `felra replay` on an untouched
    `formal_check` project reported every analysis as "the declared obligation
    does not exist" and the project as MISMATCH. The obligation was never handed
    to the checker at all. That had been true since v1.1.0, and reads as "the
    result failed to reproduce" when what happened is that nothing was checked.

    The filename is preserved rather than normalized, because TLC requires a
    module's file name to match the module, and a `.cfg` travels with its `.tla`.

    A declared file that is missing at capture time is left alone. Replay will
    then report it missing, which is the truth about that run.
    """
    from felra.formal import resolve_env_path

    base_dir = run.project.source_path.parent if run.project.source_path else Path()
    captured: list[str] = []
    for analysis in raw.get("analyses") or []:
        if analysis.get("type") != "formal_check":
            continue
        analysis_id = str(analysis.get("id", "analysis"))
        for key in ("obligation", "config"):
            declared = analysis.get(key)
            if not declared:
                continue
            # `${VAR}` is expanded here to FIND the file, exactly as the runner
            # expands it. That does not pin an environment into the replay project
            # — it does the opposite: the declaration is rewritten to the run's own
            # captured copy, so the replay depends on neither the variable nor the
            # machine. An unset variable stays unexpanded, does not exist as a
            # path, and its declaration is left untouched.
            source = resolve_env_path(str(declared))
            if source is None:
                continue
            if not source.is_absolute():
                source = base_dir / source
            if not source.exists():
                continue
            target_dir = run.output_dir / "obligations" / analysis_id
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target_dir / source.name)
            analysis[key] = f"obligations/{analysis_id}/{source.name}"
            captured.append(analysis[key])
    return captured


def write_replay_project(run: Any) -> Path:
    raw = json.loads(json.dumps(run.project.raw, ensure_ascii=False))
    for dataset_id, dataset_config in (raw.get("datasets") or {}).items():
        dataset_config["path"] = f"datasets/{dataset_id}/normalized.csv"
        dataset_config["format"] = "csv"
        dataset_config["encoding"] = "utf-8"
        dataset_config["delimiter"] = ","
        dataset_config["on_error"] = "error"
    _capture_obligations(run, raw)
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
