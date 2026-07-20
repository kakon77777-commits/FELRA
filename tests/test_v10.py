from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from felra.config import CrossMethodAnalysisSpec, ProjectConfigError, load_project
from felra.runner import run_project


def _by_id(results, analysis_id: str):
    return next(item for item in results if item.analysis_id == analysis_id)


def _write_project_with_analysis(
    tmp_path: Path, analysis: dict[str, object], parameters: dict[str, object]
) -> Path:
    payload = {
        "project": {"id": "v1.0-test", "title": "v1.0 test", "language": "en"},
        "parameters": parameters,
        "analyses": [analysis],
    }
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_cross_method_example_project_runs_end_to_end(tmp_path: Path) -> None:
    run = run_project("examples/cross_method/project.yaml", tmp_path / "run")

    trig_identity = _by_id(run.analyses, "trig_identity")
    assert trig_identity.success is True
    for pair in trig_identity.metrics["pairs"]:
        assert pair["agree"] is True

    removable_singularity = _by_id(run.analyses, "removable_singularity")
    assert removable_singularity.success is False
    pairs_by_methods = {
        tuple(pair["methods"]): pair for pair in removable_singularity.metrics["pairs"]
    }
    # arbitrary precision does not rescue a literal 0/0 -- both naive
    # formulations agree with each other (both undefined at x=1)...
    assert pairs_by_methods[("naive_formula", "naive_formula_high_precision")]["agree"] is True
    # ...but disagree with the algebraically-simplified formulation, which
    # has no singularity there.
    assert pairs_by_methods[("naive_formula", "algebraically_simplified")]["agree"] is False
    assert (
        pairs_by_methods[("naive_formula", "algebraically_simplified")][
            "nonfinite_mismatch_count"
        ]
        >= 1
    )


def test_cross_method_config_requires_at_least_two_methods(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "one_method",
                    "type": "cross_method",
                    "parameters": ["x"],
                    "methods": [{"name": "only_one", "expression": "x ** 2"}],
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )


def test_cross_method_config_rejects_duplicate_method_names(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "dup_names",
                    "type": "cross_method",
                    "parameters": ["x"],
                    "methods": [
                        {"name": "same", "expression": "x ** 2"},
                        {"name": "same", "expression": "x * x"},
                    ],
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )


def test_cross_method_config_rejects_bad_backend(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_backend",
                    "type": "cross_method",
                    "parameters": ["x"],
                    "methods": [
                        {"name": "a", "expression": "x ** 2", "backend": "not_a_backend"},
                        {"name": "b", "expression": "x * x"},
                    ],
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )


def test_cross_method_config_rejects_undeclared_parameter(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "unknown_param",
                    "type": "cross_method",
                    "parameters": ["y"],
                    "methods": [
                        {"name": "a", "expression": "y ** 2"},
                        {"name": "b", "expression": "y * y"},
                    ],
                },
                {"x": {"type": "float", "range": [0, 1], "samples": 11}},
            )
        )


def test_cross_method_spec_parses_with_valid_payload(tmp_path: Path) -> None:
    project = load_project(
        _write_project_with_analysis(
            tmp_path,
            {
                "id": "ok",
                "type": "cross_method",
                "parameters": ["x"],
                "methods": [
                    {"name": "a", "expression": "x ** 2", "backend": "numeric"},
                    {"name": "b", "expression": "x * x", "backend": "symbolic"},
                ],
            },
            {"x": {"type": "float", "range": [-1, 1], "samples": 21}},
        )
    )
    spec = project.analyses[0]
    assert isinstance(spec, CrossMethodAnalysisSpec)
    assert len(spec.methods) == 2
    assert spec.methods[1].backend == "symbolic"
    assert spec.tolerance == 1e-9
