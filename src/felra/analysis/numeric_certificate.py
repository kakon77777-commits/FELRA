"""Issue strict envelopes over a declared box (addendum stage E, §10).

The difference from every sampling channel in this package: a `parameter_sweep`
or a counterexample search says *no counterexample was found among the points
tried*. An interval evaluation says *this expression's range over the whole box is
contained in [L, U]* — a statement about uncountably many points, established by
arithmetic rather than by trying them.

That is what makes `inf F(X) > 0` a proof of `f(x) > 0` on the box, and it is why
this channel can raise the evidence ladder's `numerically_certified` rung when no
amount of sampling could.

The enclosure is not tight, and saying so matters. Interval arithmetic
overestimates whenever a variable occurs more than once — the dependency problem —
so a certificate that fails to establish a bound has not refuted it. The result
records the width so a reader can see how much slack the enclosure carries.
"""

from __future__ import annotations

import ast
from fractions import Fraction
from pathlib import Path
from typing import Any

from felra.analysis.models import AnalysisResult
from felra.certificates import (
    CertificateError,
    Interval,
    issue_inequality_certificate,
    issue_interval_certificate,
    verify_certificate,
)
from felra.config import NumericCertificateAnalysisSpec
from felra.numeric_backends import exact_parse

_ALLOWED = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd,
)


def _interval_eval(node: ast.AST, env: dict[str, Interval]) -> Interval:
    if isinstance(node, ast.Expression):
        return _interval_eval(node.body, env)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CertificateError("only numeric literals are allowed")
        value = Fraction(node.value)
        return Interval(value, value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise CertificateError("unbound name %r" % node.id)
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        operand = _interval_eval(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        raise CertificateError("unsupported unary operator")
    if isinstance(node, ast.BinOp):
        left = _interval_eval(node.left, env)
        if isinstance(node.op, ast.Pow):
            right = _interval_eval(node.right, env)
            if right.lo != right.hi or right.lo.denominator != 1:
                raise CertificateError(
                    "only a constant integer exponent has a rigorous enclosure here"
                )
            return left ** int(right.lo)
        right = _interval_eval(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        raise CertificateError("unsupported binary operator")
    raise CertificateError("unsupported syntax %s" % type(node).__name__)


def run_numeric_certificate(
    spec: NumericCertificateAnalysisSpec,
    *,
    output_dir: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    tree = ast.parse(spec.expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            return AnalysisResult(
                analysis_id=spec.analysis_id, kind="numeric_certificate",
                title=spec.title, success=False,
                summary="the expression uses %s, which has no rigorous interval "
                        "enclosure here" % type(node).__name__,
                claim_id=spec.claim_id,
                metrics={"expression": spec.expression, "certificates": []},
                warnings=["expression outside the certified fragment"],
            )

    env = {}
    for name, bounds in spec.box.items():
        lo = exact_parse(bounds["lo"]).value
        hi = exact_parse(bounds["hi"]).value
        env[name] = Interval(lo, hi)

    try:
        enclosure = _interval_eval(tree, env)
    except CertificateError as exc:
        return AnalysisResult(
            analysis_id=spec.analysis_id, kind="numeric_certificate",
            title=spec.title, success=False,
            summary="no enclosure could be computed: %s" % exc,
            claim_id=spec.claim_id,
            metrics={"expression": spec.expression, "certificates": []},
            warnings=[str(exc)],
        )

    certificates: list[dict[str, Any]] = []
    failed: list[str] = []

    interval_cert = issue_interval_certificate(
        "%s over the declared box" % spec.expression,
        # the midpoint is inside the enclosure by construction; the certificate is
        # about the enclosure, and the value it names is a witness inside it
        (enclosure.lo + enclosure.hi) / 2,
        enclosure,
    )
    certificates.append(interval_cert.as_dict())

    if spec.establish is not None:
        try:
            certificates.append(
                issue_inequality_certificate(
                    "%s %s 0 over the declared box" % (spec.expression, spec.establish),
                    enclosure,
                    spec.establish,
                ).as_dict()
            )
        except CertificateError as exc:
            failed.append(str(exc))
            warnings.append(
                "the enclosure did not establish `%s 0`: %s. Interval arithmetic "
                "overestimates when a variable occurs more than once, so this is "
                "not a refutation of the bound." % (spec.establish, exc)
            )

    # Every certificate is re-verified here, from its own recorded data, before it
    # is allowed into the manifest. A certificate nobody has re-checked is a claim
    # with a hash on it.
    verifications = []
    for cert in certificates:
        ok, detail = verify_certificate(cert)
        verifications.append({"certificate_sha256": cert["certificate_sha256"],
                              "kind": cert["kind"], "verified": ok, "detail": detail})
        if not ok:
            failed.append("%s: %s" % (cert["kind"], detail))

    success = not failed
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind="numeric_certificate",
        title=spec.title,
        success=success,
        summary="enclosure [%s, %s] over %d variable(s); %d certificate(s), all "
                "re-verified" % (
                    float(enclosure.lo), float(enclosure.hi), len(env),
                    len(certificates)) if success else
                "enclosure computed but %d certificate obligation(s) unmet"
                % len(failed),
        claim_id=spec.claim_id,
        metrics={
            "expression": spec.expression,
            "box": {name: iv.as_dict() for name, iv in env.items()},
            "enclosure": enclosure.as_dict(),
            "certificates": certificates,
            "verifications": verifications,
            "unmet": failed,
            "note": (
                "an interval enclosure is a statement about the whole box, not "
                "about sampled points; it is also not tight, so failing to "
                "establish a bound is not refuting it"
            ),
        },
        warnings=warnings,
    )
