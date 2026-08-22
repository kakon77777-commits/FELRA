"""Precision ladder (addendum stage D, §7).

    其輸入為：分析規格；初始精度；精度增長策略；目標準確度；最大精度；比較度量。
    精度序列可為 p_k = p_0·2^k 或 p_k = p_0 + k·Δp。

§18.2's acceptance is three-valued — 能判定穩定、未穩定或資源耗盡 — and ends with
the line this module is built around:

    不把未穩定結果標記為通過。

So `unstable` and `exhausted` are outcomes, not degraded successes, and neither
can raise the evidence ladder's `precision_stable` rung.

## Why the stability test compares every pair, not consecutive ones

§7.1 is explicit:

    不應只比較一次 p 與 2p。
    建議要求尾端多層滿足 d(z^{p_i}, z^{p_j}) < ε 對所有 i,j ≥ k。

Consecutive-only agreement is a weaker condition than it looks. A quantity that
oscillates with period two agrees with the level before last while disagreeing
with the level before that, and a consecutive test cannot see it. Every pair in
the tail is compared here, which is what the addendum asks for and what makes the
verdict mean "settled" rather than "did not move this once".

## Where the accuracy estimate comes from

`estimated_accuracy` is the ladder's own successive difference, never a comparison
against a known answer. In real use there is no known answer, and a check that
only works when the result is already known is not a check. Where an exact value
*is* available it is reported separately, as a way of asking whether the ladder's
self-estimate tracks the truth — which is a different and much weaker claim than
using it.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations
from typing import Any, Callable

__all__ = [
    "LADDER_STATUSES",
    "GROWTH_STRATEGIES",
    "LadderLevel",
    "LadderResult",
    "run_ladder",
    "bits_to_digits",
]

#: §18.2: stable / unstable / exhausted. `exhausted` means the ladder hit its
#: declared ceiling without settling — a resource fact, not a mathematical one,
#: and distinct from having settled on a wrong answer.
LADDER_STATUSES = ("stable", "unstable", "exhausted")

GROWTH_STRATEGIES = ("doubling", "linear")

#: log10(2), to more digits than any sane precision request.
_LOG10_2 = Fraction(30102999566398119521373889, 10 ** 26)


def bits_to_digits(bits: int) -> int:
    """The addendum declares precision in BITS; the Decimal backend works in
    digits. Converting in one place, and recording both, keeps a project's
    declaration and the engine's unit from drifting apart silently."""
    return max(1, int(bits * _LOG10_2) + 1)


@dataclass
class LadderLevel:
    """One rung. The field list is the addendum's §7."""

    precision_bits: int
    precision_digits: int
    result: Fraction
    result_hash: str
    runtime_seconds: float
    difference_from_previous: Fraction | None
    estimated_accuracy: Fraction | None
    warning: str | None = None

    def as_dict(self) -> dict[str, Any]:
        def _frac(value: Fraction | None) -> dict[str, Any] | None:
            if value is None:
                return None
            return {"exact": "%d/%d" % (value.numerator, value.denominator),
                    "float": float(value)}

        return {
            "precision_bits": self.precision_bits,
            "precision_digits": self.precision_digits,
            "result": _frac(self.result),
            "result_hash": self.result_hash,
            "runtime_seconds": round(self.runtime_seconds, 6),
            "difference_from_previous": _frac(self.difference_from_previous),
            "estimated_accuracy": _frac(self.estimated_accuracy),
            "warning": self.warning,
        }


@dataclass
class LadderResult:
    status: str
    levels: list[LadderLevel] = field(default_factory=list)
    settled_at_bits: int | None = None
    detail: str = ""
    tail_compared: int = 0
    pairs_compared: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "settled_at_bits": self.settled_at_bits,
            "detail": self.detail,
            "levels": [level.as_dict() for level in self.levels],
            "tail_levels_required": self.tail_compared,
            "tail_pairs_compared": self.pairs_compared,
            "note": (
                "the tail is compared PAIRWISE, not consecutively: consecutive "
                "agreement is satisfied by a quantity that oscillates with period "
                "two, which is settled in neither sense (§7.1)"
            ),
        }


def _hash(value: Fraction) -> str:
    return hashlib.sha256(
        ("%d/%d" % (value.numerator, value.denominator)).encode("utf-8")
    ).hexdigest()


def _within(a: Fraction, b: Fraction, abs_tol: Fraction, rel_tol: Fraction) -> bool:
    diff = abs(a - b)
    if diff <= abs_tol:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and diff <= rel_tol * scale


def run_ladder(
    evaluate: Callable[[int], Fraction],
    *,
    initial_bits: int = 64,
    strategy: str = "doubling",
    step_bits: int = 64,
    max_bits: int = 4096,
    consecutive_levels: int = 3,
    absolute_tolerance: Fraction = Fraction(1, 10 ** 80),
    relative_tolerance: Fraction = Fraction(1, 10 ** 70),
) -> LadderResult:
    """Climb until the tail settles, or until the declared ceiling is reached.

    `evaluate` takes a precision in bits and returns an exact Fraction, so the
    comparison between rungs needs no further rounding of its own.
    """
    if strategy not in GROWTH_STRATEGIES:
        raise ValueError("unknown growth strategy %r; known are %s"
                         % (strategy, ", ".join(GROWTH_STRATEGIES)))
    if consecutive_levels < 2:
        raise ValueError(
            "stability needs at least two tail levels; one level compared with "
            "itself is not a stability test"
        )

    levels: list[LadderLevel] = []
    bits = initial_bits
    k = 0
    while True:
        started = time.monotonic()
        value = evaluate(bits)
        runtime = time.monotonic() - started

        previous = levels[-1].result if levels else None
        difference = None if previous is None else value - previous
        levels.append(
            LadderLevel(
                precision_bits=bits,
                precision_digits=bits_to_digits(bits),
                result=value,
                result_hash=_hash(value),
                runtime_seconds=runtime,
                difference_from_previous=difference,
                # the ladder's own estimate, from its own successive differences
                estimated_accuracy=None if difference is None else abs(difference),
            )
        )

        if len(levels) >= consecutive_levels:
            tail = [level.result for level in levels[-consecutive_levels:]]
            pairs = list(combinations(range(len(tail)), 2))
            if all(_within(tail[i], tail[j], absolute_tolerance, relative_tolerance)
                   for i, j in pairs):
                return LadderResult(
                    status="stable",
                    levels=levels,
                    settled_at_bits=levels[-consecutive_levels].precision_bits,
                    tail_compared=consecutive_levels,
                    pairs_compared=len(pairs),
                    detail=(
                        "every pair among the last %d levels agrees within the "
                        "declared tolerances; settled from %d bits"
                        % (consecutive_levels,
                           levels[-consecutive_levels].precision_bits)
                    ),
                )

        if bits >= max_bits:
            levels[-1].warning = "the declared maximum precision was reached"
            # §18.2 asks for THREE outcomes. A first version of this returned only
            # `stable` and `exhausted`, so `unstable` was unreachable — a status in
            # the vocabulary that no run could ever produce. The two are different
            # facts and the difference is visible in the tail: differences that are
            # still shrinking say more precision would plausibly help (a resource
            # outcome); differences that are not say the ladder saw evidence
            # against convergence.
            diffs = [abs(level.difference_from_previous)
                     for level in levels[1:]
                     if level.difference_from_previous is not None]
            tail_diffs = diffs[-(consecutive_levels - 1):] if diffs else []
            shrinking = (len(tail_diffs) >= 2
                         and all(b < a for a, b in zip(tail_diffs, tail_diffs[1:])))
            if tail_diffs and not shrinking:
                return LadderResult(
                    status="unstable",
                    levels=levels,
                    tail_compared=consecutive_levels,
                    detail=(
                        "the tail differences are not shrinking across %d level(s) "
                        "up to %d bits, so the ladder saw evidence against "
                        "convergence rather than merely running out of precision"
                        % (len(levels), max_bits)
                    ),
                )
            return LadderResult(
                status="exhausted",
                levels=levels,
                tail_compared=consecutive_levels,
                detail=(
                    "reached the declared ceiling of %d bits over %d level(s) with "
                    "the differences still shrinking; this is a resource outcome, "
                    "not a statement that the quantity does not converge"
                    % (max_bits, len(levels))
                ),
            )

        k += 1
        bits = initial_bits * (2 ** k) if strategy == "doubling" else bits + step_bits
        if bits > max_bits:
            bits = max_bits
