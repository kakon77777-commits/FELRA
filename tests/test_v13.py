"""v1.3.0 — native Decimal and Rational backends (addendum stage C)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from felra.config import ProjectConfigError, load_project
from felra.numeric_backends import (
    AGREEMENT_CLASSES,
    NumericBackendError,
    agreement_class,
    conversion_audit,
    evaluate_arithmetic,
    exact_parse,
    to_backend,
)
from felra.numeric_policy import IMPLEMENTED_BACKENDS


def test_exact_string_parsing_is_not_float_parsing():
    # The whole reason stage C needs an exact parser: by the time a value is a
    # Python float, the decimal the author wrote is gone and no later precision
    # recovers it (addendum §2.2).
    assert exact_parse("0.1").value == Fraction(1, 10)
    assert exact_parse(0.1).value != Fraction(1, 10)
    assert exact_parse("1/3").value == Fraction(1, 3)


def test_a_float_source_is_marked_and_the_mark_is_sticky():
    # §9: 避免把「高精度保存的低精度值」誤認為高準確度結果
    v = exact_parse(0.1)
    assert v.source_was_float64 is True
    promoted = to_backend(to_backend(v, "rational"), "decimal")
    assert promoted.source_was_float64 is True, "the flag must survive promotion"

    clean = exact_parse("0.1")
    assert clean.source_was_float64 is False
    assert to_backend(clean, "rational").source_was_float64 is False


def test_conversion_residual_is_exact_not_estimated():
    audit = conversion_audit("0.1")
    by_ontology = {row["ontology"]: row["conversion"] for row in audit["conversions"]}
    assert by_ontology["rational"]["exact"] is True
    assert by_ontology["decimal"]["exact"] is True
    assert by_ontology["float64"]["exact"] is False
    # the residual is a rational, so it is the true error rather than a rounded
    # estimate of the error
    residual = Fraction(by_ontology["float64"]["residual"])
    assert residual != 0
    assert Fraction(float(Fraction(1, 10))) - Fraction(1, 10) == residual


def test_the_three_ontologies_can_disagree():
    env = {"a": exact_parse("0.1"), "b": exact_parse("0.2"), "c": exact_parse("0.3")}
    f = evaluate_arithmetic("(a + b) - c", env, "float64")
    d = evaluate_arithmetic("(a + b) - c", env, "decimal")
    r = evaluate_arithmetic("(a + b) - c", env, "rational")
    assert d == 0 and r == 0
    assert f != 0, "float64 must actually differ, or the comparison tests nothing"


def test_agreement_is_three_valued():
    assert AGREEMENT_CLASSES == ("exact", "within_tolerance", "inconsistent")
    a, b = Fraction(1, 3), Fraction(33333, 100000)
    assert agreement_class(a, a, Fraction(0)) == "exact"
    assert agreement_class(a, b, Fraction(1, 1000)) == "within_tolerance"
    assert agreement_class(a, b, Fraction(0)) == "inconsistent"


def test_non_arithmetic_is_refused_rather_than_approximated():
    # An ontology that claims exactness must refuse what it cannot do exactly.
    # Falling back to float here is how three "backends" become three float runs.
    env = {"a": exact_parse("0.5")}
    for bad in ("sin(a)", "a ** 0.5", "a and a", "a if a else a"):
        with pytest.raises(NumericBackendError):
            evaluate_arithmetic(bad, env, "rational")


def test_stage_c_actually_implements_what_stage_a_only_recorded():
    assert set(IMPLEMENTED_BACKENDS) == {"float64", "decimal", "rational"}
    from felra.numeric_policy import NumericPolicy

    policy = NumericPolicy.from_mapping({"default_backend": "decimal"})
    assert policy is not None
    assert not any("decimal" in item for item in policy.declared_but_not_implemented())


def test_a_yaml_float_point_is_refused(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: cross_backend\n    title: t\n"
        "    expression: x\n    points:\n      - {x: 0.1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "already been rounded" in str(exc.value)


def test_quoted_points_are_accepted(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: cross_backend\n    title: t\n"
        '    expression: x\n    points:\n      - {x: "0.1"}\n',
        encoding="utf-8",
    )
    spec = load_project(project).analyses[0]
    assert spec.points == ({"x": "0.1"},)


def test_unknown_ontology_is_refused(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: cross_backend\n    title: t\n"
        '    expression: x\n    backends: [float64, posit]\n'
        '    points:\n      - {x: "0.1"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError):
        load_project(project)
