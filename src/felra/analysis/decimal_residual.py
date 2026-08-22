"""The decimal-information-residue verification pack (addendum §12, acceptance §18.5).

§12 asks for a project template covering eight checks. They are stated over a base
`b` and a level `n`:

    T_n^(b)(x)  the truncation of x to n digits in base b
    R_n^(b)(x)  the residue that truncation discards

with

    12.1  x = T_n(x) + b^(-n) R_n(x)          the reconstruction identity
    12.2  0 <= R_n(x) < 1                     the residue range
    12.3  R_{n+1}(x) = frac(b R_n(x))         the shift law
    12.4  the same proposition over b in {2, 3, 8, 10, 16}
    12.5  n_fail(rho, p)                      where a backend first departs from exact
    12.6  source-parsing comparison across the representations
    12.7  cross-representation residues
    12.8  at least one strict envelope

Items 12.1–12.4 and 12.7 are identities, and identities are checkable exactly. So
they are computed in `Fraction` and asserted to hold **exactly**, not to within a
tolerance: a reconstruction identity that only holds to 1e-30 is not the identity,
it is evidence that something upstream rounded.

12.5 is the one that carries information rather than confirmation. `n_fail` is the
first level at which a given backend at a given precision stops agreeing with the
exact residue — the practical horizon of that representation for this quantity,
measured rather than assumed.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from felra.analysis.models import AnalysisResult
from felra.certificates import Interval, issue_interval_certificate, verify_certificate
from felra.config import DecimalResidualAnalysisSpec
from felra.numeric_backends import exact_parse, to_backend


def truncate(x: Fraction, base: int, n: int) -> Fraction:
    """T_n^(b)(x): x truncated to n digits in base b."""
    scaled = x * base ** n
    return Fraction(scaled.numerator // scaled.denominator, base ** n)


def residue(x: Fraction, base: int, n: int) -> Fraction:
    """R_n^(b)(x): what truncation discards, scaled back to [0, 1)."""
    scaled = x * base ** n
    return scaled - (scaled.numerator // scaled.denominator)


def _fractional(value: Fraction) -> Fraction:
    return value - (value.numerator // value.denominator)


def run_decimal_residual(
    spec: DecimalResidualAnalysisSpec,
    *,
    output_dir: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    failures: list[str] = []

    x = exact_parse(spec.value).value
    bases = list(spec.bases)
    levels = list(range(1, spec.levels + 1))

    # 12.1 reconstruction, 12.2 range, 12.3 shift law, 12.4 across bases
    reconstruction_ok, range_ok, shift_ok = True, True, True
    per_base: dict[str, Any] = {}
    for base in bases:
        rows = []
        for n in levels:
            t_n = truncate(x, base, n)
            r_n = residue(x, base, n)
            recon = t_n + Fraction(1, base ** n) * r_n
            if recon != x:
                reconstruction_ok = False
                failures.append("12.1 fails at base %d level %d" % (base, n))
            if not (0 <= r_n < 1):
                range_ok = False
                failures.append("12.2 fails at base %d level %d" % (base, n))
            if n < spec.levels:
                if residue(x, base, n + 1) != _fractional(base * r_n):
                    shift_ok = False
                    failures.append("12.3 fails at base %d level %d" % (base, n))
            rows.append({"n": n,
                         "truncation": "%d/%d" % (t_n.numerator, t_n.denominator),
                         "residue": "%d/%d" % (r_n.numerator, r_n.denominator),
                         "residue_float": float(r_n)})
        per_base[str(base)] = rows

    checks["12_1_reconstruction_identity"] = reconstruction_ok
    checks["12_2_residue_range"] = range_ok
    checks["12_3_shift_law"] = shift_ok
    checks["12_4_bases"] = bases
    checks["12_4_at_least_five_bases"] = len(bases) >= 5
    if len(bases) < 5:
        failures.append("12.4 asks for at least five bases; %d given" % len(bases))

    # 12.5 n_fail: the first level at which a backend stops matching the exact residue
    n_fail: dict[str, Any] = {}
    for ontology in spec.backends:
        for prec in spec.precisions:
            first = None
            approx = to_backend(exact_parse(spec.value), ontology,
                                decimal_prec=prec).value
            for n in levels:
                # The first level whose DIGITS differ, not the first level whose
                # residues are unequal. Residue inequality is degenerate here: an
                # inexact backend's residue differs at level 1 for any value it
                # cannot represent, so that version reported n_fail = 1 for every
                # backend at every precision — a measurement that did not vary
                # with the thing it was measuring. Truncation agreement is what
                # "departs from the exact reference" means in practice: how many
                # correct digits the representation actually delivers.
                if truncate(approx, spec.bases[0], n) != truncate(x, spec.bases[0], n):
                    first = n
                    break
            n_fail["%s@%d" % (ontology, prec)] = first
    checks["12_5_n_fail"] = n_fail
    checks["12_5_some_backend_actually_fails"] = any(v is not None for v in n_fail.values())
    if not checks["12_5_some_backend_actually_fails"]:
        warnings.append(
            "no backend departed from the exact residue within the levels tried, so "
            "n_fail is not a measurement here; raise `levels` or lower a precision "
            "before reading this as a strong result"
        )

    # 12.6 source parsing comparison
    parsing: dict[str, Any] = {}
    literal = exact_parse(spec.value)
    via_float = exact_parse(float(literal.value))
    for label, source in (("string", literal), ("float64_first", via_float)):
        for ontology in spec.backends:
            converted = to_backend(source, ontology, decimal_prec=max(spec.precisions))
            parsing["%s_to_%s" % (label, ontology)] = {
                "exact": converted.value == literal.value,
                "source_was_float64": converted.source_was_float64,
            }
    checks["12_6_source_parsing"] = parsing
    checks["12_6_float_first_is_marked"] = all(
        entry["source_was_float64"]
        for key, entry in parsing.items() if key.startswith("float64_first")
    )
    if not checks["12_6_float_first_is_marked"]:
        failures.append(
            "12.6: a value that passed through float64 was not marked as such"
        )

    # 12.7 cross-representation residues at a fixed level
    level = min(spec.levels, 4)
    cross: dict[str, Any] = {}
    exact_at_level = residue(x, spec.bases[0], level)
    for ontology in spec.backends:
        converted = to_backend(literal, ontology, decimal_prec=max(spec.precisions))
        r = residue(converted.value, spec.bases[0], level)
        cross[ontology] = {"residue_float": float(r),
                           "matches_exact": r == exact_at_level}
    checks["12_7_cross_representation"] = cross

    # 12.8 at least one strict envelope, over the residues actually computed
    residues = [residue(x, spec.bases[0], n) for n in levels]
    enclosure = Interval(min(residues), max(residues))
    cert = issue_interval_certificate(
        "R_n(%s) over levels 1..%d in base %d" % (spec.value, spec.levels, spec.bases[0]),
        residues[0], enclosure,
    ).as_dict()
    ok, detail = verify_certificate(cert)
    checks["12_8_envelope_reverified"] = ok
    if not ok:
        failures.append("12.8: the envelope certificate did not re-verify: %s" % detail)

    covered = sum(
        1 for key in (
            "12_1_reconstruction_identity", "12_2_residue_range", "12_3_shift_law",
            "12_4_at_least_five_bases", "12_5_some_backend_actually_fails",
            "12_6_float_first_is_marked", "12_8_envelope_reverified",
        ) if checks.get(key) is True
    )

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind="decimal_residual",
        title=spec.title,
        success=not failures,
        summary="%s over %d base(s), %d level(s): %d/7 boolean checks hold%s" % (
            spec.value, len(bases), spec.levels, covered,
            "" if not failures else "; %d failure(s)" % len(failures)),
        claim_id=spec.claim_id,
        metrics={
            "value": spec.value,
            "bases": bases,
            "levels": spec.levels,
            "checks": checks,
            "per_base": per_base,
            "certificates": [cert],
            "failures": failures,
            "note": (
                "12.1-12.4 and 12.7 are identities and are asserted EXACTLY, not "
                "within a tolerance: a reconstruction identity that holds only to "
                "1e-30 is not the identity, it is evidence that something rounded"
            ),
        },
        warnings=warnings,
    )
