"""v1.4.0 — precision ladder (addendum stage D, sections 7 and 18.2)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from felra.config import ProjectConfigError, load_project
from felra.numeric_backends import evaluate_arithmetic, exact_parse
from felra.precision_ladder import (
    GROWTH_STRATEGIES,
    LADDER_STATUSES,
    bits_to_digits,
    run_ladder,
)

TIGHT = dict(absolute_tolerance=Fraction(1, 10 ** 80),
             relative_tolerance=Fraction(1, 10 ** 70))


def _anchor_evaluator(m: str):
    env = {"two": exact_parse("2"), "three": exact_parse("3"), "m": exact_parse(m)}

    def evaluate(bits: int) -> Fraction:
        return evaluate_arithmetic(
            "1 - (two / three) ** m", env, "decimal", decimal_prec=bits_to_digits(bits)
        )

    return evaluate


def test_two_tail_levels_give_a_FALSE_stable_on_a_real_quantity():
    """Section 7.1's warning, on real numbers rather than a synthetic sequence.

        不應只比較一次 p 與 2p。

    `1 - (2/3)^150` is about `1 - 1.4e-27`. At 32 and 64 bits — 10 and 20 decimal
    digits — Decimal rounds it to EXACTLY 1 at both. Two tail levels therefore
    agree perfectly and the ladder would report `stable` at the bottom rung with
    the wrong answer. Three levels reach 128 bits, where the value moves, and the
    false settle does not happen.
    """
    evaluate = _anchor_evaluator("150")
    assert evaluate(32) == 1 and evaluate(64) == 1, "the trap must actually be there"

    two_levels = run_ladder(evaluate, initial_bits=32, max_bits=2048,
                            consecutive_levels=2, **TIGHT)
    assert two_levels.status == "stable"
    assert two_levels.levels[-1].result == 1, "and it settles on the wrong value"

    three_levels = run_ladder(evaluate, initial_bits=32, max_bits=2048,
                              consecutive_levels=3, **TIGHT)
    assert three_levels.status == "stable"
    assert three_levels.levels[-1].result != 1
    assert three_levels.settled_at_bits > two_levels.settled_at_bits


def test_all_three_statuses_are_reachable():
    """A status no run can produce is a word in the vocabulary and nothing else.

    The first version of this module returned only `stable` and `exhausted`.
    """
    assert LADDER_STATUSES == ("stable", "unstable", "exhausted")

    converging = run_ladder(lambda b: Fraction(1, 3) + Fraction(1, 10 ** b),
                            initial_bits=32, max_bits=2048, **TIGHT)
    alternating = run_ladder(lambda b: Fraction((-1) ** (b // 32), 10 ** 6),
                             initial_bits=32, strategy="linear", step_bits=32,
                             max_bits=256, **TIGHT)
    slow = run_ladder(lambda b: Fraction(1, 10 ** 6) + Fraction(1, 10 ** (b // 32)),
                      initial_bits=32, strategy="linear", step_bits=32,
                      max_bits=192, **TIGHT)

    assert converging.status == "stable"
    assert alternating.status == "unstable"
    assert slow.status == "exhausted"
    assert {converging.status, alternating.status, slow.status} == set(LADDER_STATUSES)


def test_an_unsettled_ladder_is_never_a_pass():
    # 不把未穩定結果標記為通過
    for result in (
        run_ladder(lambda b: Fraction((-1) ** (b // 32), 10 ** 6), initial_bits=32,
                   strategy="linear", step_bits=32, max_bits=256, **TIGHT),
        run_ladder(lambda b: Fraction(1, 10 ** 6) + Fraction(1, 10 ** (b // 32)),
                   initial_bits=32, strategy="linear", step_bits=32, max_bits=192,
                   **TIGHT),
    ):
        assert result.status != "stable"
        assert result.settled_at_bits is None


def test_the_tail_is_compared_pairwise():
    result = run_ladder(_anchor_evaluator("150"), initial_bits=32, max_bits=2048,
                        consecutive_levels=4, **TIGHT)
    # 4 levels -> 6 pairs, not the 3 a consecutive comparison would make
    assert result.pairs_compared == 6


def test_one_tail_level_is_refused():
    with pytest.raises(ValueError) as exc:
        run_ladder(lambda b: Fraction(1), consecutive_levels=1)
    assert "compared with itself" in str(exc.value)


def test_bits_and_digits_are_both_recorded():
    result = run_ladder(_anchor_evaluator("150"), initial_bits=64, max_bits=1024,
                        **TIGHT)
    for level in result.levels:
        assert level.precision_digits == bits_to_digits(level.precision_bits)
        assert level.precision_digits < level.precision_bits  # digits < bits
        assert level.result_hash


def test_config_refuses_a_float_tolerance(tmp_path):
    """YAML reads `1e-80` as a STRING but `1.0e-80` as a float, so the same
    tolerance is safe written one way and lossy the other. The guard has to fire
    on the form that actually loses precision, and the error message says which
    is which because a user has no reason to know."""
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: precision_ladder\n    title: t\n"
        '    expression: x\n    points:\n      - {x: "1"}\n'
        "    absolute_tolerance: 1.0e-80\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "quoted string" in str(exc.value)


def test_config_refuses_a_single_tail_level(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: precision_ladder\n    title: t\n"
        '    expression: x\n    points:\n      - {x: "1"}\n'
        "    consecutive_levels: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError):
        load_project(project)


def test_growth_strategies_are_a_closed_set():
    assert GROWTH_STRATEGIES == ("doubling", "linear")
    with pytest.raises(ValueError):
        run_ladder(lambda b: Fraction(1), strategy="fibonacci")
