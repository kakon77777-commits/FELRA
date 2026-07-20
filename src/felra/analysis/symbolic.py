from __future__ import annotations

from pathlib import Path

import sympy as sp

from felra.analysis.models import AnalysisResult
from felra.config import SymbolicAnalysisSpec
from felra.symbolic import make_symbols, parse_symbolic_expression


def run_symbolic(spec: SymbolicAnalysisSpec, output_dir: Path, output_root: Path) -> AnalysisResult:
    """V2 symbolic verification: exact algebraic equivalence and derivative checks.

    Complements the sampling-based residual/sensitivity/counterexample channels
    (which detect mismatches at sampled points within a declared domain) with an
    exact check over the whole declared domain via SymPy simplification —
    "no counterexample found in N samples" and "provably equal everywhere the
    declared assumptions hold" are different claims, and this module only ever
    makes the latter, narrower one.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    symbols = make_symbols(spec.variables, spec.assumptions)
    assumptions_payload = {name: list(keywords) for name, keywords in spec.assumptions.items()}

    if spec.check == "equivalence":
        lhs = parse_symbolic_expression(spec.lhs, symbols)
        rhs = parse_symbolic_expression(spec.rhs, symbols)
        difference = sp.simplify(lhs - rhs)
        equivalent = bool(difference == 0)
        metrics = {
            "check": spec.check,
            "lhs": spec.lhs,
            "rhs": spec.rhs,
            "variables": list(spec.variables),
            "assumptions": assumptions_payload,
            "simplified_difference": str(difference),
            "equivalent": equivalent,
        }
        summary = (
            f"{spec.lhs} is symbolically equivalent to {spec.rhs} "
            f"under the declared assumptions."
            if equivalent
            else (
                f"{spec.lhs} is NOT symbolically equivalent to {spec.rhs} "
                f"under the declared assumptions (simplified difference: {difference})."
            )
        )
    else:
        base_expr = parse_symbolic_expression(spec.expression, symbols)
        wrt = symbols[spec.with_respect_to]
        computed = sp.diff(base_expr, wrt)
        expected = parse_symbolic_expression(spec.expected_derivative, symbols)
        difference = sp.simplify(computed - expected)
        equivalent = bool(difference == 0)
        metrics = {
            "check": spec.check,
            "expression": spec.expression,
            "with_respect_to": spec.with_respect_to,
            "expected_derivative": spec.expected_derivative,
            "computed_derivative": str(computed),
            "variables": list(spec.variables),
            "assumptions": assumptions_payload,
            "simplified_difference": str(difference),
            "equivalent": equivalent,
        }
        summary = (
            f"d/d{spec.with_respect_to}[{spec.expression}] = {computed}, "
            f"matches the declared derivative."
            if equivalent
            else (
                f"d/d{spec.with_respect_to}[{spec.expression}] = {computed}, "
                f"which does NOT match the declared derivative {spec.expected_derivative!r} "
                f"(simplified difference: {difference})."
            )
        )

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind=spec.kind,
        title=spec.title,
        success=equivalent,
        summary=summary,
        metrics=metrics,
        claim_id=spec.claim_id,
    )
