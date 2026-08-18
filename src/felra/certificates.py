"""Strict envelopes and numeric certificates (addendum stage E, §10).

Five certificate kinds are named in §10, and the fifth is the one this package
already produces: an external formal verdict from SMT, Lean or a model checker.
So stage E and stage F's 證書回收與驗證 meet here rather than in two places.

§18.4's acceptance is four lines, and two of them are the whole design:

    證書可獨立重驗
    證書失效時重播不得標記為完整通過

**Independently re-verifiable** means a certificate must be checkable from what it
records, without re-running the analysis that issued it. A "certificate" that can
only be confirmed by repeating the computation is a log line. So every kind here
carries the data its own check needs, and `verify` never calls back into the
analysis engine.

**An invalid certificate must break the pass.** A certificate that no longer holds
is worse than an absent one, because a manifest carrying it says a claim was
enclosed when it was not.

## Rigour, and where outward rounding actually matters

Interval endpoints are exact `Fraction`s, so arithmetic on them is exact and the
enclosure is rigorous with no rounding at all. That is not a dodge — for the
rational expressions this package evaluates it is the right representation, and an
interval library that rounds where it need not is adding error to advertise
rigour.

Outward rounding matters at the boundary where a certificate is *reported* in a
finite representation. `Interval.to_decimal` rounds the lower endpoint **down** and
the upper endpoint **up**, so a certificate narrowed by display is impossible: the
printed interval always contains the exact one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from fractions import Fraction
from typing import Any

__all__ = [
    "CERTIFICATE_KINDS",
    "Interval",
    "Certificate",
    "CertificateError",
    "issue_interval_certificate",
    "issue_inequality_certificate",
    "issue_exact_identity_certificate",
    "issue_external_formal_certificate",
    "verify_certificate",
]


class CertificateError(ValueError):
    """A certificate cannot be issued or is malformed."""


#: §10.1–10.5, verbatim.
CERTIFICATE_KINDS = (
    "interval",
    "ball",
    "exact_identity",
    "inequality",
    "external_formal",
)


@dataclass(frozen=True)
class Interval:
    """`[lo, hi]` with exact rational endpoints."""

    lo: Fraction
    hi: Fraction

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise CertificateError("interval endpoints are inverted: %s > %s"
                                   % (self.lo, self.hi))

    def contains(self, value: Fraction) -> bool:
        return self.lo <= value <= self.hi

    def width(self) -> Fraction:
        return self.hi - self.lo

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(self.lo + other.lo, self.hi + other.hi)

    def __sub__(self, other: "Interval") -> "Interval":
        return Interval(self.lo - other.hi, self.hi - other.lo)

    def __mul__(self, other: "Interval") -> "Interval":
        corners = (self.lo * other.lo, self.lo * other.hi,
                   self.hi * other.lo, self.hi * other.hi)
        return Interval(min(corners), max(corners))

    def __truediv__(self, other: "Interval") -> "Interval":
        if other.contains(Fraction(0)):
            raise CertificateError(
                "division by an interval containing zero has no finite enclosure; "
                "refusing rather than returning one that is not an enclosure"
            )
        corners = (self.lo / other.lo, self.lo / other.hi,
                   self.hi / other.lo, self.hi / other.hi)
        return Interval(min(corners), max(corners))

    def __neg__(self) -> "Interval":
        return Interval(-self.hi, -self.lo)

    def __pow__(self, n: int) -> "Interval":
        if n < 0:
            return Interval(Fraction(1), Fraction(1)) / (self ** (-n))
        if n == 0:
            return Interval(Fraction(1), Fraction(1))
        if n % 2 == 1:
            return Interval(self.lo ** n, self.hi ** n)
        # even powers are not monotone across zero
        if self.lo >= 0:
            return Interval(self.lo ** n, self.hi ** n)
        if self.hi <= 0:
            return Interval(self.hi ** n, self.lo ** n)
        return Interval(Fraction(0), max(self.lo ** n, self.hi ** n))

    def to_decimal(self, prec: int = 30) -> tuple[Decimal, Decimal]:
        """Report the enclosure in decimal with **outward** rounding.

        The lower endpoint rounds down and the upper rounds up, so the printed
        interval always contains the exact one. A certificate narrowed by the act
        of displaying it would be a certificate of something else.
        """
        with localcontext() as ctx:
            # The context precision counts SIGNIFICANT digits while `prec` here is
            # decimal places, so quantising a value with an integer part needs
            # headroom or `quantize` raises InvalidOperation. Found the first time
            # this met an enclosure like [2, 6] rather than a fraction below one.
            ctx.prec = prec + 40
            lo = (Decimal(self.lo.numerator) / Decimal(self.lo.denominator)).quantize(
                Decimal(1).scaleb(-prec), rounding=ROUND_FLOOR)
            hi = (Decimal(self.hi.numerator) / Decimal(self.hi.denominator)).quantize(
                Decimal(1).scaleb(-prec), rounding=ROUND_CEILING)
        return lo, hi

    def as_dict(self) -> dict[str, Any]:
        lo, hi = self.to_decimal()
        return {
            "lo": "%d/%d" % (self.lo.numerator, self.lo.denominator),
            "hi": "%d/%d" % (self.hi.numerator, self.hi.denominator),
            "lo_decimal_rounded_down": str(lo),
            "hi_decimal_rounded_up": str(hi),
            "width_float": float(self.width()),
        }


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


@dataclass(frozen=True)
class Certificate:
    """A statement, the data needed to re-check it, and its hash.

    `subject` is human-readable; `data` is what `verify_certificate` reads. The
    hash covers both, so a certificate edited after issue no longer matches the
    hash recorded in the manifest.
    """

    kind: str
    subject: str
    data: dict[str, Any] = field(default_factory=dict)
    issuer: str = "felra"

    def digest(self) -> str:
        return hashlib.sha256(
            _canonical({"kind": self.kind, "subject": self.subject,
                        "data": self.data, "issuer": self.issuer}).encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "data": self.data,
            "issuer": self.issuer,
            "certificate_sha256": self.digest(),
        }


# ---------------------------------------------------------------- issuing


def issue_interval_certificate(subject: str, value: Fraction,
                               enclosure: Interval) -> Certificate:
    """§10.1: `x ∈ [L, U]`."""
    if not enclosure.contains(value):
        raise CertificateError(
            "refusing to issue an interval certificate that does not enclose its "
            "own subject: %s is outside [%s, %s]" % (value, enclosure.lo, enclosure.hi)
        )
    return Certificate(
        kind="interval",
        subject=subject,
        data={"value": "%d/%d" % (value.numerator, value.denominator),
              "interval": enclosure.as_dict()},
    )


def issue_inequality_certificate(subject: str, enclosure: Interval,
                                 relation: str = ">") -> Certificate:
    """§10.4: `f(x) > 0` **from** `inf F(X) > 0`.

    The certificate records the enclosure, not the conclusion alone, because the
    conclusion is only as good as the enclosure it came from and a reader must be
    able to see which.
    """
    if relation not in (">", ">=", "<", "<="):
        raise CertificateError("unsupported relation %r" % relation)
    holds = {
        ">": enclosure.lo > 0,
        ">=": enclosure.lo >= 0,
        "<": enclosure.hi < 0,
        "<=": enclosure.hi <= 0,
    }[relation]
    if not holds:
        raise CertificateError(
            "the enclosure does not establish `%s 0`: it is [%s, %s], which "
            "straddles or fails the bound"
            % (relation, enclosure.lo, enclosure.hi)
        )
    return Certificate(
        kind="inequality",
        subject=subject,
        data={"relation": relation, "interval": enclosure.as_dict()},
    )


def issue_exact_identity_certificate(subject: str, lhs: Fraction,
                                     rhs: Fraction) -> Certificate:
    """§10.3: `a = b`, established by exact rational arithmetic."""
    if lhs != rhs:
        raise CertificateError(
            "refusing to certify an identity that does not hold: %s != %s"
            % (lhs, rhs)
        )
    return Certificate(
        kind="exact_identity",
        subject=subject,
        data={"lhs": "%d/%d" % (lhs.numerator, lhs.denominator),
              "rhs": "%d/%d" % (rhs.numerator, rhs.denominator)},
    )


def issue_external_formal_certificate(subject: str, outcome: dict[str, Any]) -> Certificate:
    """§10.5: a verdict recovered from an external prover.

    This is stage F's 證書回收與驗證: a `formal_check` result becomes a certificate
    carrying the checker's identity and the obligation's hash, so a later reader
    can ask *which binary checked what* rather than being told that something was
    proved.
    """
    status = outcome.get("formal_status")
    if status != "verified":
        raise CertificateError(
            "only a `verified` formal outcome yields a certificate; this one is %r"
            % status
        )
    checker = outcome.get("checker") or {}
    obligation = outcome.get("obligation") or {}
    if not obligation.get("sha256"):
        raise CertificateError(
            "a formal certificate needs the obligation's hash; without it the "
            "certificate names no particular artifact"
        )
    return Certificate(
        kind="external_formal",
        subject=subject,
        issuer=str(checker.get("backend") or "unknown"),
        data={
            "checker": {k: checker.get(k) for k in
                        ("backend", "version_string", "executable_sha256")},
            "obligation_sha256": obligation.get("sha256"),
            "theorems_audited": outcome.get("theorems_audited"),
            "axioms_seen": outcome.get("axioms_seen"),
        },
    )


# ---------------------------------------------------------------- verifying


def verify_certificate(cert: dict[str, Any]) -> tuple[bool, str]:
    """Re-check a certificate from its own recorded data.

    Never calls back into the analysis engine, because a certificate that can only
    be confirmed by repeating the computation is a log line (§18.4:
    證書可獨立重驗).
    """
    kind = cert.get("kind")
    data = cert.get("data") or {}

    recorded = cert.get("certificate_sha256")
    if recorded:
        rebuilt = Certificate(
            kind=str(kind), subject=str(cert.get("subject", "")),
            data=data, issuer=str(cert.get("issuer", "felra")),
        ).digest()
        if rebuilt != recorded:
            return False, "the certificate's contents do not match its recorded hash"

    if kind == "interval":
        value = Fraction(data["value"])
        lo = Fraction(data["interval"]["lo"])
        hi = Fraction(data["interval"]["hi"])
        if lo > hi:
            return False, "endpoints are inverted"
        if not lo <= value <= hi:
            return False, "the value is outside the certified interval"
        return True, "the value lies within the certified interval"

    if kind == "inequality":
        lo = Fraction(data["interval"]["lo"])
        hi = Fraction(data["interval"]["hi"])
        relation = data["relation"]
        holds = {">": lo > 0, ">=": lo >= 0, "<": hi < 0, "<=": hi <= 0}[relation]
        if not holds:
            return False, "the recorded enclosure does not establish the relation"
        return True, "the enclosure establishes `%s 0`" % relation

    if kind == "exact_identity":
        if Fraction(data["lhs"]) != Fraction(data["rhs"]):
            return False, "the certified identity does not hold"
        return True, "the two sides are the same rational number"

    if kind == "external_formal":
        # What can be re-checked here is the certificate's OWN integrity, not the
        # proof: re-running the prover is not independent re-verification, it is
        # the original check again. Saying so is the honest boundary.
        if not data.get("obligation_sha256"):
            return False, "no obligation hash, so the certificate names no artifact"
        checker = data.get("checker") or {}
        if not checker.get("backend"):
            return False, "no checker identity recorded"
        return True, (
            "the certificate is internally complete: it names %s and the "
            "obligation it checked. Re-running that prover is the original check "
            "again, not an independent re-verification of it."
            % checker.get("backend")
        )

    return False, "unknown certificate kind %r" % kind
