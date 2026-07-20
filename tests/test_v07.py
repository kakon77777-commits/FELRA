from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from felra.config import load_project
from felra.export import export_paper_bundle
from felra.preregistration import PreregistrationError, verify_preregistration, write_preregistration
from felra.reproducibility import replay_run
from felra.runner import run_project


def _project_payload(*, strict: bool = False) -> dict[str, object]:
    return {
        "project": {"id": "v07-test", "title": "v0.7 test", "language": "en"},
        "execution": {"max_evaluations": 101, "random_samples": 100, "seed": 9},
        "preregistration": {
            "enabled": True,
            "path": "preregistration.json",
            "mode": "strict" if strict else "warn",
        },
        "parameters": {"x": {"type": "float", "range": [-2, 2], "samples": 101}},
        "claims": [
            {
                "id": "nonnegative",
                "statement": "x squared is non-negative",
                "expression": "x ** 2 >= 0",
                "required_checks": ["numerical", "boundaries", "counterexample_search"],
            }
        ],
        "outputs": {
            "figures": [
                {
                    "id": "curve",
                    "type": "line",
                    "x": "x",
                    "y": "x ** 2",
                    "title": "square",
                    "filename": "curve.png",
                }
            ]
        },
    }


def _write_project(tmp_path: Path, *, strict: bool = False) -> Path:
    path = tmp_path / "project.yaml"
    path.write_text(
        yaml.safe_dump(_project_payload(strict=strict), sort_keys=False), encoding="utf-8"
    )
    return path


def test_preregistration_matches_and_detects_plan_drift(tmp_path: Path) -> None:
    project_path = _write_project(tmp_path)
    project = load_project(project_path)
    record_path = tmp_path / "preregistration.json"
    record = write_preregistration(project, record_path)
    assert len(record["plan_sha256"]) == 64
    assert verify_preregistration(project, record_path).matched is True

    payload = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    payload["claims"][0]["expression"] = "x ** 2 > 0"
    project_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    drifted = load_project(project_path)
    verification = verify_preregistration(drifted, record_path)
    assert verification.status == "mismatch"
    assert verification.matched is False


def test_strict_preregistration_blocks_modified_plan(tmp_path: Path) -> None:
    project_path = _write_project(tmp_path, strict=True)
    project = load_project(project_path)
    write_preregistration(project, tmp_path / "preregistration.json")

    payload = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    payload["execution"]["seed"] = 10
    project_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(PreregistrationError):
        run_project(project_path, tmp_path / "run")


def test_run_writes_provenance_replay_and_paper_export(tmp_path: Path) -> None:
    project_path = _write_project(tmp_path, strict=True)
    project = load_project(project_path)
    write_preregistration(project, tmp_path / "preregistration.json")

    run_dir = tmp_path / "run"
    run = run_project(project_path, run_dir)
    assert run.passed is True
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["result_sha256"]) == 64
    assert manifest["preregistration"]["matched"] is True
    assert (run_dir / "replay_project.yaml").exists()
    assert (run_dir / "provenance" / "provenance.json").exists()
    assert (run_dir / "provenance" / "provenance.dot").exists()
    assert (run_dir / "provenance" / "provenance.svg").exists()

    replay_dir = tmp_path / "replay"
    replay = replay_run(run_dir, replay_dir)
    assert replay["matched"] is True

    paper_dir = tmp_path / "paper"
    exported = export_paper_bundle(run_dir, paper_dir)
    assert exported["result_sha256"] == manifest["result_sha256"]
    assert (paper_dir / "METHODS.md").exists()
    assert (paper_dir / "RESULTS.md").exists()
    assert (paper_dir / "LIMITATIONS.md").exists()
    assert (paper_dir / "CITATION.cff").exists()
    assert (paper_dir / "EXPORT_MANIFEST.json").exists()
