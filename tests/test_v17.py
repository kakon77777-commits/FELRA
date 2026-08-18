"""v1.7.0 — exact and interval dataset columns (addendum stage B)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from felra.certificates import Interval
from felra.config import DatasetColumnSpec, ProjectConfigError
from felra.data import _convert, _missing_value
from felra.numeric_backends import ExactValue


def test_an_exact_column_is_not_rounded_on_load():
    """Stage B's whole point. A column typed `float` discards the producer's
    precision before FELRA has seen it; one typed `str` keeps the text while
    losing that it is a number."""
    value = _convert("1/3", "exact")
    assert isinstance(value, ExactValue)
    assert value.value == Fraction(1, 3)
    assert value.source_was_float64 is False

    # and the same cell typed `float` cannot even be read: a producer writing an
    # exact rational has to be met with a column type that understands one
    with pytest.raises(ValueError):
        _convert("1/3", "float")


def test_a_decimal_literal_keeps_its_decimal_value():
    assert _convert("0.1", "exact").value == Fraction(1, 10)
    assert Fraction(_convert("0.1", "float")) != Fraction(1, 10)


def test_a_magnitude_float_cannot_hold_survives():
    tiny = _convert("1e-30", "exact")
    assert tiny.value == Fraction(1, 10 ** 30)
    assert Fraction(_convert("1e-30", "float")) != Fraction(1, 10 ** 30)


def test_interval_columns_parse_a_pair():
    iv = _convert("1/3|2/3", "interval")
    assert isinstance(iv, Interval)
    assert iv.lo == Fraction(1, 3) and iv.hi == Fraction(2, 3)
    for text in ("1/3..2/3", "1/3;2/3"):
        alt = _convert(text, "interval")
        assert (alt.lo, alt.hi) == (iv.lo, iv.hi)


def test_a_single_value_is_a_degenerate_interval_not_an_error():
    iv = _convert("5", "interval")
    assert iv.lo == iv.hi == 5
    assert iv.width() == 0


def test_garbage_is_refused_rather_than_coerced():
    for kind in ("exact", "interval"):
        with pytest.raises(ValueError):
            _convert("nonsense", kind)


def test_an_inverted_interval_is_refused():
    with pytest.raises(ValueError):
        _convert("2|1", "interval")


def test_a_missing_exact_value_is_absent_not_nan():
    """There is no exact NaN. Filling a missing exact value with a float sentinel
    would put a number where the producer recorded nothing, and later arithmetic
    would treat it as one."""
    assert _missing_value("exact") is None
    assert _missing_value("interval") is None


def test_the_column_kinds_are_declarable_and_the_list_is_closed(tmp_path):
    from felra.config import load_project

    (tmp_path / "d.csv").write_text("a,b\n1/3,1/3|2/3\n", encoding="utf-8")

    def _write(name: str, kind_a: str):
        path = tmp_path / name
        path.write_text(
            "project:\n  id: p\n  title: t\n"
            "datasets:\n  d:\n    path: d.csv\n    format: csv\n"
            "    columns:\n      a: " + kind_a + "\n      b: interval\n"
            "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
            "claims:\n  - id: c\n    statement: s\n    expression: x >= 0\n"
            "    status: hypothesis\n",
            encoding="utf-8",
        )
        return path

    spec = load_project(_write("good.yaml", "exact"))
    assert spec.datasets["d"].columns["a"].kind == "exact"
    assert spec.datasets["d"].columns["b"].kind == "interval"

    with pytest.raises(ProjectConfigError):
        load_project(_write("bad.yaml", "posit"))


def test_an_exact_column_survives_loading_a_real_file(tmp_path):
    from felra.config import load_project
    from felra.data import load_dataset

    (tmp_path / "d.csv").write_text(
        "exact_value,rounded_value\n1/3,0.3333333333333333\n", encoding="utf-8")
    project = tmp_path / "p.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "datasets:\n  d:\n    path: d.csv\n    format: csv\n"
        "    columns:\n      exact_value: exact\n      rounded_value: float\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "claims:\n  - id: c\n    statement: s\n    expression: x >= 0\n"
        "    status: hypothesis\n",
        encoding="utf-8",
    )
    dataset = load_dataset(load_project(project).datasets["d"])
    exact = dataset.columns["exact_value"][0]
    rounded = dataset.columns["rounded_value"][0]
    assert exact.value == Fraction(1, 3)
    assert Fraction(float(rounded)) != Fraction(1, 3)
