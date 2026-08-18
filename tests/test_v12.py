"""v1.2.0 — numeric governance layer (addendum stage A, 治理先行).

Stage A records and validates; it computes nothing. So these tests are mostly
about two things that are easy to get wrong in a governance layer: refusing
vocabulary it does not understand, and leaving existing runs alone.
"""

from __future__ import annotations

import pytest

from felra.numeric_policy import (
    EVIDENCE_LEVEL_ORDER,
    IMPLEMENTED_BACKENDS,
    NumericPolicy,
    NumericPolicyError,
    describe_numeric_environment,
    evidence_status,
)


def test_an_undeclared_policy_is_absent_not_defaulted():
    # This is what keeps addendum 17.1 and 17.3 true. A default object here would
    # give every legacy project a policy it never asked for, and its digest would
    # move every existing result_sha256.
    assert NumericPolicy.from_mapping(None) is None
    assert NumericPolicy.from_mapping({}) is None


def test_vocabulary_is_the_addendums_and_unknown_terms_are_refused():
    for bad in (
        {"default_backend": "posit"},
        {"source_parsing": "guess"},
        {"rounding_mode": "banker"},
        {"certification": {"mode": "vibes"}},
        {"escalation": {"strategy": "exponential-ish"}},
        {"cross_backend": {"backends": ["float128"]}},
    ):
        with pytest.raises(NumericPolicyError):
            NumericPolicy.from_mapping(bad)


def test_unknown_top_level_fields_are_refused():
    with pytest.raises(NumericPolicyError) as exc:
        NumericPolicy.from_mapping({"default_backend": "float64", "precision": 128})
    assert "unknown numeric_policy field" in str(exc.value)


def test_nonpositive_precision_is_refused():
    with pytest.raises(NumericPolicyError):
        NumericPolicy.from_mapping({"working_precision_bits": 0})


def test_a_declared_backend_is_not_silently_honoured():
    """The addendum permits naming a backend before it exists. What it must not do
    is let a manifest imply the computation used it.

    This test originally named `decimal`, which v1.3.0 then implemented — so it
    failed for the right reason and is rewritten to pin the INVARIANT rather than
    the set of backends that happened to exist when it was written. `binary_mp` is
    stage D and is the current example of a declared-but-absent backend.
    """
    policy = NumericPolicy.from_mapping({"default_backend": "binary_mp"})
    assert policy is not None
    pending = policy.declared_but_not_implemented()
    assert any("binary_mp" in item for item in pending)
    assert "float64" in IMPLEMENTED_BACKENDS
    assert "binary_mp" not in IMPLEMENTED_BACKENDS
    # and a backend that IS implemented must not be listed as pending
    implemented = NumericPolicy.from_mapping({"default_backend": "float64"})
    assert implemented is not None
    assert implemented.declared_but_not_implemented() == []


def test_float64_only_policy_has_nothing_pending():
    policy = NumericPolicy.from_mapping({"default_backend": "float64"})
    assert policy is not None
    assert policy.declared_but_not_implemented() == []


def test_policy_digest_separates_declarations():
    a = NumericPolicy.from_mapping({"default_backend": "float64"})
    b = NumericPolicy.from_mapping({"default_backend": "decimal"})
    c = NumericPolicy.from_mapping({"default_backend": "float64"})
    assert a is not None and b is not None and c is not None
    assert a.digest() != b.digest()          # 17.4: a change separates
    assert a.digest() == c.digest()          # and the digest is stable


def test_environment_records_what_actually_computed():
    env = describe_numeric_environment()
    assert env["computation_backend"] == "float64"
    assert env["float_mant_dig"] == 53
    assert env["python"] and env["platform"]
    # the hosts of the later backends are recorded even though unused, so a
    # stage-C run can be compared against a stage-A one
    assert "decimal_default_prec" in env


def test_evidence_ladder_is_cumulative():
    status = evidence_status(executed=True, reproduced=True)
    assert status["highest_level"] == "reproduced"
    assert status["levels"]["precision_stable"] == "not_run"


def test_a_gap_below_stops_the_climb():
    # A formal proof recorded above an unrun precision check must not raise the
    # level. Otherwise the ladder reports a rung nothing supports.
    status = evidence_status(
        executed=True,
        reproduced=True,
        formal_results=[{"formal_status": "verified"}],
    )
    assert status["levels"]["formally_proved"] == "pass"
    assert status["highest_level"] == "reproduced"


def test_formal_check_results_drive_the_top_rung():
    refuted = evidence_status(executed=True, formal_results=[{"formal_status": "refuted"}])
    assert refuted["levels"]["formally_proved"] == "fail"

    mixed = evidence_status(
        executed=True,
        formal_results=[{"formal_status": "verified"}, {"formal_status": "unavailable"}],
    )
    # a checker that did not run cannot be part of a proof
    assert mixed["levels"]["formally_proved"] == "partial"


def test_falsified_overrides_the_ladder():
    status = evidence_status(executed=True, reproduced=True, falsified=True)
    assert status["highest_level"] == "falsified"
    assert status["falsified"] is True


def test_unrun_rungs_are_not_run_rather_than_not_applicable():
    # `not_applicable` would be a judgement this version is not entitled to make.
    status = evidence_status(executed=True)
    for name in EVIDENCE_LEVEL_ORDER[1:]:
        assert status["levels"][name] in {"not_run", "pass", "fail", "partial"}
        assert status["levels"][name] != "not_applicable"


def test_declaring_or_changing_a_policy_separates_the_result_hash(monkeypatch):
    """Addendum 17.3 and 17.4 as one assertion.

    The natural implementation satisfies one and breaks the other: give every
    project a default policy and 17.4 works while every legacy result_sha256
    moves. `result_payload` is stubbed so this tests the separation itself rather
    than a whole project run.
    """
    from felra import reproducibility as repro

    monkeypatch.setattr(repro, "result_payload", lambda run: {"stub": 1})

    class _Project:
        numeric_policy = None

    class _Run:
        project = _Project()

    run = _Run()
    absent = repro.result_sha256(run)

    _Project.numeric_policy = NumericPolicy.from_mapping({"default_backend": "float64"})
    declared = repro.result_sha256(run)

    _Project.numeric_policy = NumericPolicy.from_mapping({"default_backend": "decimal"})
    changed = repro.result_sha256(run)

    assert absent != declared, "declaring a policy must separate the fingerprint"
    assert declared != changed, "changing a policy must separate it again"
    assert absent != changed

    # and the absent case must be byte-identical to the pre-v1.2 payload
    import hashlib
    import json

    legacy = hashlib.sha256(
        json.dumps({"stub": 1}, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert absent == legacy, "a project without a policy must hash exactly as before"


def test_falsified_means_a_counterexample_not_a_failed_expectation():
    """Section 11's F is 發現有效反例, not "an analysis did not meet its expectation".

    Briefly driven by `not run.passed`, which made a deliberate cross-backend
    disagreement report as though the claim had been refuted — a verdict on the
    mathematics that the run never reached. Caught by pointing FELRA at the
    Collatz anchor project.
    """
    # an analysis-level failure with no counterexample must not falsify
    not_refuted = evidence_status(executed=True, falsified=False)
    assert not_refuted["highest_level"] == "executed"
    assert "falsified" not in not_refuted

    refuted = evidence_status(executed=True, falsified=True)
    assert refuted["highest_level"] == "falsified"
