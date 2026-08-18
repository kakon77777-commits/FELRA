"""v1.5.0 — strict envelopes and numeric certificates (addendum stage E, §10, §18.4)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from felra.certificates import (
    CERTIFICATE_KINDS,
    CertificateError,
    Interval,
    issue_exact_identity_certificate,
    issue_external_formal_certificate,
    issue_inequality_certificate,
    issue_interval_certificate,
    verify_certificate,
)
from felra.config import ProjectConfigError, load_project

F = Fraction


def _unit(a, b) -> Interval:
    return Interval(F(a), F(b))


def test_the_five_kinds_are_the_addendums():
    assert CERTIFICATE_KINDS == (
        "interval", "ball", "exact_identity", "inequality", "external_formal")


def test_an_enclosure_is_about_the_whole_box_not_sampled_points():
    # (x-1)^2 + 2 over [0,3]: the range is [2,6], and that is a statement about
    # uncountably many x, established by arithmetic rather than by trying them.
    x = _unit(0, 3)
    enclosure = (x - _unit(1, 1)) ** 2 + _unit(2, 2)
    assert enclosure.lo == 2 and enclosure.hi == 6
    for probe in (F(0), F(1), F(3), F(7, 3)):
        value = (probe - 1) ** 2 + 2
        assert enclosure.contains(value)


def test_the_dependency_problem_causes_a_REFUSAL_not_a_bad_certificate():
    """Interval arithmetic overestimates when a variable occurs more than once.

    `x^2 - 2x + 3` is `(x-1)^2 + 2 > 0` everywhere, but evaluated in its
    unfactored form over [0,3] the enclosure is [-3, 12]. The right behaviour is to
    refuse the certificate, not to issue one the enclosure does not support — and
    a refusal here is NOT a refutation of the bound.
    """
    x = _unit(0, 3)
    naive = x ** 2 - _unit(2, 2) * x + _unit(3, 3)
    assert naive.lo < 0 < naive.hi

    with pytest.raises(CertificateError) as exc:
        issue_inequality_certificate("f > 0", naive, ">")
    assert "does not establish" in str(exc.value)

    factored = (x - _unit(1, 1)) ** 2 + _unit(2, 2)
    cert = issue_inequality_certificate("f > 0", factored, ">")
    assert verify_certificate(cert.as_dict())[0] is True


def test_a_certificate_is_reverifiable_from_its_own_data():
    # §18.4 證書可獨立重驗 — no call back into whatever produced it.
    cert = issue_interval_certificate("x", F(1, 2), _unit(0, 1)).as_dict()
    ok, detail = verify_certificate(cert)
    assert ok and "within the certified interval" in detail


def test_tampering_breaks_the_hash():
    cert = issue_inequality_certificate("f > 0", _unit(2, 6), ">").as_dict()
    tampered = dict(cert)
    tampered["data"] = dict(cert["data"])
    tampered["data"]["relation"] = "<"
    ok, detail = verify_certificate(tampered)
    assert ok is False
    assert "do not match its recorded hash" in detail


def test_a_certificate_that_no_longer_holds_fails_reverification():
    cert = issue_interval_certificate("x", F(1, 2), _unit(0, 1)).as_dict()
    broken = dict(cert)
    broken["data"] = {"value": "5", "interval": dict(cert["data"]["interval"])}
    broken.pop("certificate_sha256")          # as if re-issued around a new value
    ok, detail = verify_certificate(broken)
    assert ok is False
    assert "outside the certified interval" in detail


def test_outward_rounding_never_narrows_an_enclosure():
    interval = Interval(F(1, 3), F(2, 3))
    lo, hi = interval.to_decimal(6)
    assert Fraction(lo) <= interval.lo, "the lower endpoint must round DOWN"
    assert Fraction(hi) >= interval.hi, "the upper endpoint must round UP"
    # and on an enclosure with an integer part, which is where quantize first broke
    lo2, hi2 = Interval(F(2), F(6)).to_decimal(30)
    assert Fraction(lo2) <= 2 and Fraction(hi2) >= 6


def test_division_by_an_interval_containing_zero_is_refused():
    with pytest.raises(CertificateError) as exc:
        _unit(1, 2) / _unit(-1, 1)
    assert "refusing" in str(exc.value)


def test_an_identity_that_does_not_hold_is_refused():
    issue_exact_identity_certificate("a = b", F(1, 3), F(1, 3))
    with pytest.raises(CertificateError):
        issue_exact_identity_certificate("a = b", F(1, 3), F(1, 4))


def test_only_a_verified_formal_outcome_becomes_a_certificate():
    good = {
        "formal_status": "verified",
        "checker": {"backend": "lean", "version_string": "Lean 4", "executable_sha256": "a" * 64},
        "obligation": {"sha256": "b" * 64},
        "theorems_audited": 184,
    }
    cert = issue_external_formal_certificate("collatz-lean", good)
    assert cert.issuer == "lean"
    assert cert.data["theorems_audited"] == 184
    ok, detail = verify_certificate(cert.as_dict())
    assert ok
    # the honest boundary: re-running the prover is the original check again
    assert "not an independent re-verification" in detail

    for bad in ({**good, "formal_status": "unavailable"},
                {**good, "obligation": {}}):
        with pytest.raises(CertificateError):
            issue_external_formal_certificate("x", bad)


def test_config_refuses_a_float_box_endpoint(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: numeric_certificate\n    title: t\n"
        "    expression: x\n    box:\n      x:\n        lo: 0.1\n        hi: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "already rounded before the enclosure" in str(exc.value)
