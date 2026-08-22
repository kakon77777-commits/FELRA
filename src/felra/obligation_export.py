"""Proof-obligation export (addendum stage F, the last item on its list).

Every formal channel so far CHECKS an obligation somebody wrote. This one
GENERATES one from a FELRA claim, which is the direction the addendum names and
the direction with a failure mode of its own.

## The failure mode, and the guard

An exporter that emits a trivially unsatisfiable obligation — contradictory domain
constraints, a mistranslated connective that collapses to `false` — will be
reported `unsat` by any solver, forever, for every claim. It would look like a
verifier that proves everything.

So an export is checked **twice**: once as written, and once with the claim's
conclusion negated.

    obligation   twin     verdict
    unsat        sat      verified   no counterexample, and the domain is non-empty
    sat          unsat    refuted    the claim fails everywhere on the domain
    sat          sat      refuted    it holds at some points and fails at others
    unsat        unsat    unknown    the domain is EMPTY — never `verified`

Only the last row indicates a broken export: an unsatisfiable domain makes every
obligation over it vacuously unsat, so the solver would "prove" any claim at all.
The third row is worth stating because the first version of this guard got it
wrong — it refused whenever the pair *agreed*, which turned a perfectly good
refutation into `unknown`. That check costs one extra solver call and is the only
thing standing between this module and a machine that agrees with anything.

## Faithfulness over coverage

The translator refuses whatever it cannot render exactly. Real division stays
division and is not approximated; `**` becomes repeated multiplication only for
literal non-negative integer exponents; a function call, a boolean coercion of a
number, anything else — refused with a reason. An obligation that is *nearly* the
claim is an obligation about a different claim, and a solver's verdict on it is
worth nothing.

Only SMT-LIB2 is emitted. Lean and Coq are named in stage F, and generating a
proof script that both typechecks and states the intended thing is a different
problem from translating an expression — attempting it would produce artifacts
that mostly fail to compile and occasionally compile while meaning something else.
That is recorded here rather than papered over.
"""

from __future__ import annotations

import ast
from typing import Any

__all__ = [
    "ObligationExportError",
    "export_smtlib",
    "SMT_LOGIC",
]


class ObligationExportError(ValueError):
    """A claim cannot be rendered as an obligation without changing its meaning."""


#: Nonlinear real/integer arithmetic. Declared rather than inferred, so a solver
#: that cannot take it says so instead of guessing.
SMT_LOGIC = "AUFNIRA"

_COMPARISONS = {
    ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<=",
    ast.Eq: "=", ast.NotEq: "distinct",
}

_ARITH = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}


def _num(value: Any) -> str:
    if isinstance(value, bool):
        raise ObligationExportError("a bare boolean literal is not an arithmetic term")
    if isinstance(value, int):
        return "(- %d)" % -value if value < 0 else str(value)
    if isinstance(value, float):
        # A float literal in a claim is already rounded; emitting it as a decimal
        # keeps the obligation faithful to what the claim actually says rather
        # than to what its author may have meant.
        return "(- %s)" % repr(-value) if value < 0 else repr(value)
    raise ObligationExportError("unsupported literal %r" % (value,))


def _term(node: ast.AST, names: set[str]) -> str:
    """An arithmetic term."""
    if isinstance(node, ast.Constant):
        return _num(node.value)
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise ObligationExportError("unbound name %r" % node.id)
        return node.id
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return "(- %s)" % _term(node.operand, names)
        if isinstance(node.op, ast.UAdd):
            return _term(node.operand, names)
        raise ObligationExportError("unsupported unary operator in a term")
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            if not isinstance(node.right, ast.Constant) or \
                    not isinstance(node.right.value, int) or node.right.value < 0:
                raise ObligationExportError(
                    "only a literal non-negative integer exponent can be rendered "
                    "exactly; %s cannot" % ast.unparse(node)
                )
            base = _term(node.left, names)
            if node.right.value == 0:
                return "1"
            return "(* %s)" % " ".join([base] * node.right.value)
        op = _ARITH.get(type(node.op))
        if op is None:
            raise ObligationExportError(
                "operator %s has no exact rendering" % type(node.op).__name__)
        return "(%s %s %s)" % (op, _term(node.left, names), _term(node.right, names))
    raise ObligationExportError(
        "%s cannot appear in an arithmetic term" % type(node).__name__)


def _formula(node: ast.AST, names: set[str]) -> str:
    """A boolean formula."""
    if isinstance(node, ast.BoolOp):
        op = "and" if isinstance(node.op, ast.And) else "or"
        return "(%s %s)" % (op, " ".join(_formula(v, names) for v in node.values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return "(not %s)" % _formula(node.operand, names)
    if isinstance(node, ast.Compare):
        if len(node.ops) == 1:
            symbol = _COMPARISONS.get(type(node.ops[0]))
            if symbol is None:
                raise ObligationExportError(
                    "comparison %s has no exact rendering"
                    % type(node.ops[0]).__name__)
            return "(%s %s %s)" % (symbol, _term(node.left, names),
                                   _term(node.comparators[0], names))
        # a < b < c means (a < b) and (b < c); rendering it as anything else
        # would be a different claim
        parts, left = [], node.left
        for op, right in zip(node.ops, node.comparators):
            symbol = _COMPARISONS.get(type(op))
            if symbol is None:
                raise ObligationExportError("chained comparison has no rendering")
            parts.append("(%s %s %s)" % (symbol, _term(left, names),
                                         _term(right, names)))
            left = right
        return "(and %s)" % " ".join(parts)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return "true" if node.value else "false"
    raise ObligationExportError(
        "%s is not a boolean formula; a numeric expression used as a truth value "
        "would silently become a different claim" % type(node).__name__
    )


def export_smtlib(
    claim_id: str,
    expression: str,
    parameters: dict[str, dict[str, Any]],
    *,
    negate_conclusion: bool = False,
) -> str:
    """Render one claim as an SMT-LIB2 obligation.

    The claim asserts that `expression` holds everywhere on the declared domain.
    The obligation asserts the domain and the **negation** of the expression, so
    `unsat` means no counterexample exists — which is what a proof of the claim is.

    `negate_conclusion=True` emits the discriminating twin: the same domain with
    the conclusion flipped. A faithful export makes exactly one of the pair unsat.
    """
    tree = ast.parse(expression, mode="eval")
    names = set(parameters)

    lines = [
        "; FELRA proof obligation",
        "; claim: %s" % claim_id,
        "; expression: %s" % expression,
        ";",
        "; The DOMAIN and the NEGATION of the claim are asserted, so `unsat` means",
        "; no counterexample exists on that domain. `sat` is a counterexample.",
    ]
    if negate_conclusion:
        lines.append(
            "; This is the DISCRIMINATING TWIN: the conclusion is flipped. A "
            "faithful export makes exactly one of the pair unsat."
        )
    lines.append("(set-logic %s)" % SMT_LOGIC)

    for name, spec in sorted(parameters.items()):
        kind = str(spec.get("type", "float"))
        sort = {"float": "Real", "int": "Int"}.get(kind)
        if sort is None:
            raise ObligationExportError(
                "parameter %r has type %r, which has no SMT sort here; only float "
                "and int are rendered, because guessing a sort changes the claim"
                % (name, kind)
            )
        lines.append("(declare-const %s %s)" % (name, sort))

    for name, spec in sorted(parameters.items()):
        if "values" in spec:
            # A finite value list is a disjunction, not a range. Widening it to
            # [min, max] would make the obligation cover points the claim never
            # spoke about, and a proof of the wider thing is not a proof of this
            # one — nor is a counterexample in the gap a counterexample to it.
            options = spec["values"]
            if not options:
                raise ObligationExportError(
                    "parameter %r has an empty value list, so its domain is empty "
                    "and every obligation over it is vacuously unsat" % name)
            lines.append("(assert (or %s))" % " ".join(
                "(= %s %s)" % (name, _num(v)) for v in options))
            continue
        bounds = spec.get("range")
        if bounds is None:
            lines.append("; NOTE: %s is unbounded; the obligation quantifies over "
                         "its whole sort" % name)
            continue
        lo, hi = bounds
        lines.append("(assert (and (>= %s %s) (<= %s %s)))"
                     % (name, _num(lo), name, _num(hi)))

    body = _formula(tree.body, names)
    conclusion = body if negate_conclusion else "(not %s)" % body
    lines.append("(assert %s)" % conclusion)
    lines.append("(check-sat)")
    return "\n".join(lines) + "\n"
