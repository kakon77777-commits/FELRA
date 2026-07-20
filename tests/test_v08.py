from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from felra.config import ProjectConfigError, SymbolicAnalysisSpec, load_project
from felra.expressions import UnsafeExpressionError
from felra.runner import run_project
from felra.symbolic import make_symbols, parse_symbolic_expression


def _by_id(results, analysis_id: str):
    return next(item for item in results if item.analysis_id == analysis_id)


def _write_project_with_analysis(tmp_path: Path, analysis: dict[str, object]) -> Path:
    payload = {
        "project": {"id": "v08-test", "title": "v0.8 test", "language": "en"},
        "analyses": [analysis],
    }
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_symbolic_example_project_runs_end_to_end(tmp_path: Path) -> None:
    run = run_project("examples/symbolic/project.yaml", tmp_path / "run")

    unconstrained = _by_id(run.analyses, "sqrt_square_unconstrained")
    assert unconstrained.success is False
    assert unconstrained.metrics["equivalent"] is False
    assert unconstrained.metrics["simplified_difference"] != "0"

    positive = _by_id(run.analyses, "sqrt_square_positive")
    assert positive.success is True
    assert positive.metrics["equivalent"] is True
    assert positive.metrics["simplified_difference"] == "0"

    derivative = _by_id(run.analyses, "cubic_derivative")
    assert derivative.success is True
    assert derivative.metrics["computed_derivative"] == "3*x**2 + 2"

    # The numeric claim (sampled, tolerance-based) and the unconstrained symbolic
    # check (exact) independently agree that sqrt(x**2) == x fails somewhere in
    # the declared real domain — the whole point of pairing V2 with V5/V6/V7.
    assert run.claims_passed is False


def test_symbolic_equivalence_respects_assumptions() -> None:
    symbols = make_symbols(("x",), {"x": ("positive",)})
    lhs = parse_symbolic_expression("sqrt(x ** 2)", symbols)
    rhs = parse_symbolic_expression("x", symbols)
    assert (lhs - rhs).simplify() == 0

    unconstrained = make_symbols(("x",), {})
    lhs2 = parse_symbolic_expression("sqrt(x ** 2)", unconstrained)
    rhs2 = parse_symbolic_expression("x", unconstrained)
    assert (lhs2 - rhs2).simplify() != 0


def test_symbolic_expression_rejects_unsafe_syntax() -> None:
    symbols = make_symbols(("x",), {})
    with pytest.raises(UnsafeExpressionError):
        parse_symbolic_expression("__import__('os')", symbols)
    with pytest.raises(UnsafeExpressionError):
        parse_symbolic_expression("x > 0", symbols)
    with pytest.raises(UnsafeExpressionError):
        parse_symbolic_expression("unknown_symbol", symbols)
    with pytest.raises(UnsafeExpressionError):
        parse_symbolic_expression("not_a_function(x)", symbols)


def test_symbolic_config_requires_check_specific_fields(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_equivalence",
                    "type": "symbolic",
                    "check": "equivalence",
                    "variables": ["x"],
                    "lhs": "x",
                    # missing rhs
                },
            )
        )
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_derivative",
                    "type": "symbolic",
                    "check": "derivative",
                    "variables": ["x"],
                    "expression": "x ** 2",
                    "with_respect_to": "x",
                    # missing expected_derivative
                },
            )
        )
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_check",
                    "type": "symbolic",
                    "check": "not_a_real_check",
                    "variables": ["x"],
                },
            )
        )


def test_symbolic_config_rejects_undeclared_variable_references(tmp_path: Path) -> None:
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_assumption",
                    "type": "symbolic",
                    "check": "equivalence",
                    "variables": ["x"],
                    "assumptions": {"y": ["positive"]},
                    "lhs": "x",
                    "rhs": "x",
                },
            )
        )
    with pytest.raises(ProjectConfigError):
        load_project(
            _write_project_with_analysis(
                tmp_path,
                {
                    "id": "bad_wrt",
                    "type": "symbolic",
                    "check": "derivative",
                    "variables": ["x"],
                    "expression": "x ** 2",
                    "with_respect_to": "y",
                    "expected_derivative": "2 * x",
                },
            )
        )


def test_symbolic_spec_parses_with_valid_payload(tmp_path: Path) -> None:
    project = load_project(
        _write_project_with_analysis(
            tmp_path,
            {
                "id": "ok",
                "type": "symbolic",
                "check": "derivative",
                "variables": ["x"],
                "expression": "x ** 2",
                "with_respect_to": "x",
                "expected_derivative": "2 * x",
            },
        )
    )
    spec = project.analyses[0]
    assert isinstance(spec, SymbolicAnalysisSpec)
    assert spec.with_respect_to == "x"


def test_v08_project_config_parses() -> None:
    project = load_project("examples/symbolic/project.yaml")
    assert any(isinstance(item, SymbolicAnalysisSpec) for item in project.analyses)
