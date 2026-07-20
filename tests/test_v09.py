from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from felra.config import NumericalSoundnessAnalysisSpec, ProjectConfigError, load_project
from felra.runner import run_project


def _by_id(results, analysis_id: str):
    return next(item for item in results if item.analysis_id == analysis_id)


def _write_project_with_analysis(
    tmp_path: Path, analysis: dict[str, object], parameters: dict[str, object]
) -> Path:
    payload = {
        "project": {"id": "v09-test", "title": "v0.9 test", "language": "en"},
        "parameters": parameters,
        "analyses": [analysis],
    }
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_numerical_soundness_example_project_runs_end_to_end(tmp_path: Path) -> None:
    run = run_project("examples/numerical_soundness/project.yaml", tmp_path / "run")

    well_behaved = _by_id(run.analyses, "well_behaved")
    assert well_behaved.success is True
    assert well_behaved.metrics["nonfinite_count"] == 0
    assert well_behaved.metrics["ill_conditioned_count"] == 0
    assert well_behaved.metrics["precision_loss_count"] == 0

    near_singularity = _by_id(run.analyses, "near_singularity")
    assert near_singularity.success is False
    assert near_singularity.metrics["nonfinite_count"] >= 1
    assert near_singularity.metrics["ill_conditioned_count"] > 0
    assert near_singularity.metrics["max_condition_number"] > 1e6

    cancellation = _by_id(run.analyses, "cancellation")
    assert cancellation.success is False
    assert cancellation.metrics["singular_count"] >= 1
    assert cancellation.metrics["precision_loss_count"] >= 1
    assert cancellation.metrics["max_relative_error"] > 1e-6


def test_numerical_soundness_config_requires_expression_and_parameters(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "missing_parameters",
                    "type": "numerical_soundness",
                    "expression": "x ** 2",
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "empty_parameters",
                    "type": "numerical_soundness",
                    "expression": "x ** 2",
                    "parameters": [],
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )


def test_numerical_soundness_config_rejects_undeclared_parameter(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "unknown_param",
                    "type": "numerical_soundness",
                    "expression": "y ** 2",
                    "parameters": ["y"],
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )


def test_numerical_soundness_config_rejects_bad_thresholds(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_precision",
                    "type": "numerical_soundness",
                    "expression": "x ** 2",
                    "parameters": ["x"],
                    "precision_digits": 5,
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_condition_threshold",
                    "type": "numerical_soundness",
                    "expression": "x ** 2",
                    "parameters": ["x"],
                    "condition_threshold": -1,
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )


def test_numerical_soundness_spec_parses_with_valid_payload(tmp_path: Path) -> None:
    project = load_project(
        _write_project_with_analysis(
            tmp_path,
            {
                "id": "ok",
                "type": "numerical_soundness",
                "expression": "x ** 2 + 1",
                "parameters": ["x"],
            },
            {"x": {"type": "float", "range": [-1, 1], "samples": 21}},
        )
    )
    spec = project.analyses[0]
    assert isinstance(spec, NumericalSoundnessAnalysisSpec)
    assert spec.parameters == ("x",)
    assert spec.precision_digits == 30
    assert spec.condition_threshold == 1e6
