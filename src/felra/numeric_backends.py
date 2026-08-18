"""Native Decimal and Rational backends (addendum stage C).

From `FELRA_v1.0_未來數值表示與驗證升級附加計畫` §16, stage C:

    加入：exact string parser；Decimal backend；Rational backend；
    轉換殘差；精確恆等式驗證。

Stage A (v1.2.0) let a project *declare* `default_backend: decimal` and reported
it as declared-but-not-implemented. This module is what makes that declaration
mean something, so `IMPLEMENTED_BACKENDS` grows here and nowhere else.

## The two things that make this more than a type swap

**Exact parsing is a different act from exact arithmetic.** `0.1` written in a
project file is already a float64 by the time a naive loader has finished with it,
and no later precision can recover the decimal the author wrote. So the exact
string parser reads the *literal text* — `Fraction("0.1") == 1/10` exactly, where
`Fraction(0.1)` is `3602879701896397/36028797018963968`. §2.2 of the addendum is
about precisely this: 高精度型別不能修復早期損失.

**A high-precision value is not a high-accuracy value.** §9 requires that a
backend receiving a float64 keep `source_was_float64: true`, 「避免把『高精度保存
的低精度值』誤認為高準確度結果」. That flag is carried through every conversion
here, and it is *sticky*: once a value has been through float64 it can never be
reported as exact again, however many digits are later printed.

## Conversion residual

§9 defines, for a conversion `C` from representation ρ to σ,

    R_{ρ→σ}(x) = Decode_σ(C_{ρ→σ}(x)) − x

computed exactly, in rationals, so the residual of a float64 conversion is the
true error and not itself a rounded quantity.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, getcontext, localcontext
from fractions import Fraction
from typing import Any

__all__ = [
    "NUMERIC_ONTOLOGIES",
    "ExactValue",
    "NumericBackendError",
    "exact_parse",
    "to_backend",
    "conversion_audit",
    "agreement_class",
    "AGREEMENT_CLASSES",
]


class NumericBackendError(ValueError):
    """A value or expression cannot be represented in the requested ontology."""


#: The ontologies this version can actually compute in.
NUMERIC_ONTOLOGIES = ("float64", "decimal", "rational")

#: §18.3 asks a cross-backend comparison to distinguish three outcomes, not two.
AGREEMENT_CLASSES = ("exact", "within_tolerance", "inconsistent")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExactValue:
    """A number plus the history that says how much of it to believe.

    `value` is always an exact `Fraction`, whatever ontology produced it, so that
    residuals and comparisons are computed without a second rounding. The
    ontology and the provenance flags travel with it.
    """

    value: Fraction
    ontology: str
    source_text: str | None = None
    source_was_float64: bool = False
    conversions: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def as_float(self) -> float:
        return float(self.value)

    def as_decimal(self, prec: int = 50) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = prec
            return Decimal(self.value.numerator) / Decimal(self.value.denominator)

    def describe(self) -> dict[str, Any]:
        return {
            "ontology": self.ontology,
            "exact_rational": "%d/%d" % (self.value.numerator, self.value.denominator),
            "source_text": self.source_text,
            # sticky: once through float64, never reported as exact again
            "source_was_float64": self.source_was_float64,
            "conversions": [dict(c) for c in self.conversions],
        }


def exact_parse(text: str | int | float | Fraction | Decimal, ontology: str = "rational") -> ExactValue:
    """Parse a value into an exact rational, recording whether precision was lost.

    A *string* is read literally, which is the whole point of `source_parsing:
    exact_string`: `"0.1"` becomes exactly `1/10`. A Python `float` cannot be
    read literally, because the decimal the author typed is already gone — so it
    is converted exactly (`Fraction(0.1)` is the true binary value) and marked
    `source_was_float64`.
    """
    if ontology not in NUMERIC_ONTOLOGIES:
        raise NumericBackendError(
            "unknown numeric ontology %r; known are %s"
            % (ontology, ", ".join(NUMERIC_ONTOLOGIES))
        )

    if isinstance(text, ExactValue):  # pragma: no cover - defensive
        return text
    if isinstance(text, bool):
        raise NumericBackendError("a boolean is not a numeric value")

    was_float = False
    if isinstance(text, float):
        # exact conversion of the binary value that is actually there
        value = Fraction(text)
        source_text = repr(text)
        was_float = True
    elif isinstance(text, int):
        value = Fraction(text)
        source_text = str(text)
    elif isinstance(text, Fraction):
        value = text
        source_text = str(text)
    elif isinstance(text, Decimal):
        value = Fraction(text)
        source_text = str(text)
    else:
        source_text = str(text).strip()
        try:
            value = Fraction(source_text)
        except (ValueError, ZeroDivisionError) as exc:
            raise NumericBackendError(
                "cannot read %r as an exact value: %s" % (source_text, exc)
            ) from exc

    return ExactValue(
        value=value,
        ontology=ontology,
        source_text=source_text,
        source_was_float64=was_float,
    )


def to_backend(value: ExactValue, ontology: str, *, decimal_prec: int = 50,
               rounding_mode: str = "nearest_even") -> ExactValue:
    """Convert to another ontology, recording the conversion and its residual."""
    if ontology not in NUMERIC_ONTOLOGIES:
        raise NumericBackendError("unknown numeric ontology %r" % ontology)

    exact_before = value.value
    if ontology == "rational":
        after = exact_before
        exact = True
    elif ontology == "float64":
        after = Fraction(float(exact_before))
        exact = after == exact_before
    else:  # decimal
        with localcontext() as ctx:
            ctx.prec = decimal_prec
            as_dec = Decimal(exact_before.numerator) / Decimal(exact_before.denominator)
        after = Fraction(as_dec)
        exact = after == exact_before

    residual = after - exact_before          # §9: R = Decode(C(x)) − x, exactly
    record = {
        "from": value.ontology,
        "to": ontology,
        "rounding": rounding_mode,
        "exact": exact,
        "source_hash": _hash(str(exact_before)),
        "result_hash": _hash(str(after)),
        "residual": "%d/%d" % (residual.numerator, residual.denominator),
        "residual_float": float(residual),
        "error_lower": float(residual),
        "error_upper": float(residual),
    }
    if ontology == "decimal":
        record["decimal_prec"] = decimal_prec

    return ExactValue(
        value=after,
        ontology=ontology,
        source_text=value.source_text,
        # sticky, per §9: a high-precision copy of a float64 is not high accuracy
        source_was_float64=value.source_was_float64 or (ontology == "float64" and not exact)
        or (value.ontology == "float64"),
        conversions=value.conversions + (record,),
    )


def conversion_audit(source: str | int | float | Fraction,
                     ontologies: tuple[str, ...] = NUMERIC_ONTOLOGIES,
                     *, decimal_prec: int = 50) -> dict[str, Any]:
    """Round-trip one value through each ontology and report every residual."""
    origin = exact_parse(source)
    rows = []
    for ontology in ontologies:
        converted = to_backend(origin, ontology, decimal_prec=decimal_prec)
        rows.append(
            {
                "ontology": ontology,
                "value": converted.describe(),
                "conversion": converted.conversions[-1],
            }
        )
    return {
        "source": origin.describe(),
        "conversions": rows,
        "note": (
            "residuals are computed in exact rational arithmetic, so a float64 "
            "residual is the true error rather than a rounded estimate of it"
        ),
    }


def agreement_class(a: Fraction, b: Fraction, tolerance: Fraction) -> str:
    """§18.3's trichotomy: exact / within tolerance / inconsistent.

    Two outcomes would be the easy design and the wrong one: "agrees to 1e-9" and
    "is the same number" are different facts, and a comparison that cannot say
    which is being reported cannot support an `exact_verified` claim.
    """
    if a == b:
        return "exact"
    if abs(a - b) <= tolerance:
        return "within_tolerance"
    return "inconsistent"


# --------------------------------------------------------------------------
# arithmetic evaluation, one implementation per ontology

import ast as _ast

_ALLOWED_NODES = (
    _ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Constant, _ast.Name,
    _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Pow, _ast.USub, _ast.UAdd,
    # `Load` is the context every Name carries; it is not an operation. Omitting
    # it made the whitelist reject `a + b`, which is the failure mode a whitelist
    # is supposed to have — noisy rather than permissive.
    _ast.Load,
)


def _walk(node, env, kind, prec):
    """Arithmetic only, evaluated in the requested ontology.

    Deliberately narrow: `+ - * / **` with integer exponents, and nothing else.
    A transcendental function has no exact rational value, so an ontology that
    claims exactness must REFUSE it rather than quietly fall back to float — that
    fallback is how a `cross_backend_consistent` result would come to mean three
    float64 runs agreeing with each other.
    """
    if isinstance(node, _ast.Expression):
        return _walk(node.body, env, kind, prec)
    if isinstance(node, _ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise NumericBackendError("only numeric literals are allowed")
        # a float literal in the SOURCE is a float; that loss is real and recorded
        return _coerce(Fraction(node.value) if isinstance(node.value, int)
                       else Fraction(node.value), kind, prec)
    if isinstance(node, _ast.Name):
        if node.id not in env:
            raise NumericBackendError("unbound name %r" % node.id)
        return env[node.id]
    if isinstance(node, _ast.UnaryOp):
        operand = _walk(node.operand, env, kind, prec)
        if isinstance(node.op, _ast.USub):
            return -operand
        if isinstance(node.op, _ast.UAdd):
            return operand
        raise NumericBackendError("unsupported unary operator")
    if isinstance(node, _ast.BinOp):
        left = _walk(node.left, env, kind, prec)
        right = _walk(node.right, env, kind, prec)
        if isinstance(node.op, _ast.Add):
            return left + right
        if isinstance(node.op, _ast.Sub):
            return left - right
        if isinstance(node.op, _ast.Mult):
            return left * right
        if isinstance(node.op, _ast.Div):
            if right == 0:
                raise NumericBackendError("division by zero")
            return left / right
        if isinstance(node.op, _ast.Pow):
            exponent = right
            as_int = int(exponent) if exponent == int(exponent) else None
            if as_int is None:
                raise NumericBackendError(
                    "only integer exponents are exact in these ontologies; %r is not"
                    % float(exponent)
                )
            return left ** as_int
        raise NumericBackendError("unsupported binary operator")
    raise NumericBackendError("unsupported syntax %s" % type(node).__name__)


def _coerce(value: Fraction, kind: str, prec: int):
    if kind == "rational":
        return value
    if kind == "float64":
        return float(value)
    with localcontext() as ctx:
        ctx.prec = prec
        return Decimal(value.numerator) / Decimal(value.denominator)


def evaluate_arithmetic(expression: str, assignments: dict[str, ExactValue],
                        ontology: str, *, decimal_prec: int = 50) -> Fraction:
    """Evaluate `expression` in `ontology` and return the result as an exact
    Fraction, so that comparison across ontologies needs no further rounding."""
    if ontology not in NUMERIC_ONTOLOGIES:
        raise NumericBackendError("unknown numeric ontology %r" % ontology)
    for node in _ast.walk(_ast.parse(expression, mode="eval")):
        if not isinstance(node, _ALLOWED_NODES):
            raise NumericBackendError(
                "expression uses %s, which is not arithmetic; cross-backend "
                "comparison is defined for arithmetic only"
                % type(node).__name__
            )
    env = {
        name: _coerce(to_backend(value, ontology, decimal_prec=decimal_prec).value,
                      ontology, decimal_prec)
        for name, value in assignments.items()
    }
    result = _walk(_ast.parse(expression, mode="eval"), env, ontology, decimal_prec)
    return Fraction(result)
