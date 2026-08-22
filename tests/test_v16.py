"""v1.6.0 — binary_mp backend and the decimal-residue pack (§12, acceptance §18.5)."""

from __future__ import annotations

import pathlib
import tempfile
from fractions import Fraction

import pytest

from felra.analysis.decimal_residual import residue, run_decimal_residual, truncate
from felra.config import DecimalResidualAnalysisSpec, ProjectConfigError, load_project
from felra.numeric_backends import (
    NUMERIC_ONTOLOGIES,
    evaluate_arithmetic,
    exact_parse,
    to_backend,
)
from felra.numeric_policy import IMPLEMENTED_BACKENDS


def _spec(**kw) -> DecimalResidualAnalysisSpec:
    base = dict(analysis_id="dr", kind="decimal_residual", title="t", claim_id=None,
                value="1/7", bases=(10, 2, 3, 8, 16), levels=60,
                backends=("float64", "decimal", "binary_mp"), precisions=(16, 40))
    base.update(kw)
    return DecimalResidualAnalysisSpec(**base)


def _run(**kw):
    return run_decimal_residual(_spec(**kw),
                                output_dir=pathlib.Path(tempfile.mkdtemp()))


def test_binary_mp_is_now_a_real_backend():
    assert "binary_mp" in NUMERIC_ONTOLOGIES
    assert "binary_mp" in IMPLEMENTED_BACKENDS
    env = {"two": exact_parse("2"), "three": exact_parse("3"), "m": exact_parse("150")}
    exact = evaluate_arithmetic("1 - (two / three) ** m", env, "rational")
    errors = {
        p: abs(evaluate_arithmetic("1 - (two / three) ** m", env, "binary_mp",
                                   decimal_prec=p) - exact)
        for p in (40, 80, 160)
    }
    assert errors[40] > errors[80] > errors[160], (
        "declaring more digits must buy accuracy in binary_mp too; got %r" % errors)


def test_an_mpf_is_converted_exactly_not_through_float():
    # `float(mpf)` would round to double first, and every residual downstream
    # would then measure that rounding rather than the backend.
    value = to_backend(exact_parse("1/3"), "binary_mp", decimal_prec=60)
    assert value.value != Fraction(1, 3)                      # not exact, as expected
    assert abs(value.value - Fraction(1, 3)) < Fraction(1, 10 ** 55)
    assert abs(value.value - Fraction(1, 3)) > 0
    # a float64 round-trip would only be good to ~1e-17
    assert abs(value.value - Fraction(1, 3)) < Fraction(1, 10 ** 20)


def test_the_reconstruction_identity_holds_exactly():
    # 12.1, and it is an identity, so it is asserted exactly rather than to a
    # tolerance: one that holds only to 1e-30 is not the identity.
    x = Fraction(1, 7)
    for base in (2, 3, 8, 10, 16):
        for n in range(1, 12):
            assert truncate(x, base, n) + Fraction(1, base ** n) * residue(x, base, n) == x


def test_the_residue_range_and_shift_law():
    x = Fraction(1, 7)
    for base in (2, 10, 16):
        for n in range(1, 12):
            r = residue(x, base, n)
            assert 0 <= r < 1                                  # 12.2
            nxt = base * r
            assert residue(x, base, n + 1) == nxt - (nxt.numerator // nxt.denominator)


def test_all_seven_boolean_checks_hold_on_a_repeating_fraction():
    result = _run()
    checks = result.metrics["checks"]
    for key in ("12_1_reconstruction_identity", "12_2_residue_range",
                "12_3_shift_law", "12_4_at_least_five_bases",
                "12_5_some_backend_actually_fails", "12_6_float_first_is_marked",
                "12_8_envelope_reverified"):
        assert checks[key] is True, key
    assert result.success
    assert result.metrics["failures"] == []


def test_n_fail_actually_varies_with_precision():
    """12.5 has to be a measurement, not a constant.

    The first version compared RESIDUES for equality, and an inexact backend's
    residue differs at level 1 for any value it cannot represent — so it reported
    n_fail = 1 for every backend at every precision, a number that did not move
    with the thing it was measuring. Comparing TRUNCATIONS asks how many correct
    digits the representation delivers, which is what the addendum means.
    """
    n_fail = _run().metrics["checks"]["12_5_n_fail"]
    assert n_fail["decimal@40"] > n_fail["decimal@16"], (
        "more declared digits must survive further into the expansion; got %r" % n_fail)
    assert n_fail["binary_mp@40"] > n_fail["binary_mp@16"]
    # float64 has no precision knob, so its horizon must NOT move with the
    # declared precision — and that is itself informative
    assert n_fail["float64@16"] == n_fail["float64@40"]
    assert len(set(n_fail.values())) > 1


def test_a_value_that_passed_through_float64_is_marked_everywhere():
    parsing = _run().metrics["checks"]["12_6_source_parsing"]
    for key, entry in parsing.items():
        if key.startswith("float64_first"):
            assert entry["source_was_float64"] is True
            assert entry["exact"] is False


def test_fewer_than_five_bases_is_refused(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: decimal_residual\n    title: t\n"
        '    value: "1/7"\n    bases: [10, 2]\n',
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "at least five bases" in str(exc.value)


def test_a_float_value_is_refused(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: decimal_residual\n    title: t\n"
        "    value: 0.1\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "already rounded before any residue" in str(exc.value)
