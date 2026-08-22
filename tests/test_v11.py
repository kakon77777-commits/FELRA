"""v1.1.0 — external formal backends (whitepaper stage 4, first slice).

These tests are deliberately independent of whether any checker is installed.
The behaviour that matters most is what happens when a checker is *absent*, and
a suite that only passes on a machine with Lean and TLC would be testing the
machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from felra.analysis.formal_check import run_formal_check
from felra.config import FormalCheckAnalysisSpec, ProjectConfigError, load_project
from felra.formal import (
    BACKENDS,
    FORMAL_STATUSES,
    identify_checker,
    run_backend,
)


def _spec(**kwargs) -> FormalCheckAnalysisSpec:
    base = dict(
        analysis_id="fc",
        kind="formal_check",
        title="t",
        claim_id=None,
        backend="z3",
        obligation="obligation.smt2",
        expect="verified",
    )
    base.update(kwargs)
    return FormalCheckAnalysisSpec(**base)


def test_status_vocabulary_is_four_valued():
    # `unknown` (ran, undecided) and `unavailable` (did not run) are different
    # facts. Collapsing them is how a missing tool becomes an implicit pass.
    assert FORMAL_STATUSES == ("verified", "refuted", "unknown", "unavailable")
    assert "verified" in FORMAL_STATUSES and len(set(FORMAL_STATUSES)) == 4


def test_backend_list_is_closed():
    with pytest.raises(ValueError) as exc:
        identify_checker("definitely-not-a-checker")
    assert "unknown formal backend" in str(exc.value)
    for backend in BACKENDS:
        identity = identify_checker(backend)
        assert identity.backend == backend
        assert isinstance(identity.available, bool)


def test_identity_is_recorded_even_when_the_checker_is_absent():
    identity = identify_checker("tlc", jar=Path("no/such/tla2tools.jar"))
    assert identity.available is False
    assert identity.note and "not found" in identity.note
    # the declared path is kept, so the record says WHERE it looked
    assert identity.executable_path is not None


def test_missing_obligation_is_a_malformed_request_not_a_verdict(tmp_path):
    result = run_formal_check(
        _spec(obligation="nope.smt2"), base_dir=tmp_path, output_dir=tmp_path
    )
    assert result.success is False
    # crucially: no formal status at all, rather than a negative one
    assert result.metrics["formal_status"] is None


def test_absent_checker_never_reports_verified(tmp_path):
    obligation = tmp_path / "obligation.smt2"
    obligation.write_text("(check-sat)\n", encoding="utf-8")
    outcome = run_backend("z3", obligation)
    if outcome.checker.available:  # pragma: no cover - depends on the machine
        pytest.skip("z3 is installed on this machine; the absent path is untested here")
    assert outcome.formal_status == "unavailable"
    assert outcome.formal_status != "verified"
    assert any("not checked" in item for item in outcome.limitations)


def test_absent_checker_fails_the_expectation_unless_declared(tmp_path):
    obligation = tmp_path / "obligation.smt2"
    obligation.write_text("(check-sat)\n", encoding="utf-8")
    if identify_checker("z3").available:  # pragma: no cover
        pytest.skip("z3 is installed on this machine")

    strict = run_formal_check(
        _spec(obligation="obligation.smt2", expect="verified"),
        base_dir=tmp_path,
        output_dir=tmp_path,
    )
    assert strict.success is False, "a missing tool must not pass as a proof"
    assert strict.warnings

    declared = run_formal_check(
        _spec(obligation="obligation.smt2", expect="unavailable"),
        base_dir=tmp_path,
        output_dir=tmp_path,
    )
    assert declared.success is True
    assert declared.metrics["formal_status"] == "unavailable"


def test_evidence_status_and_formal_status_stay_separate(tmp_path):
    obligation = tmp_path / "obligation.smt2"
    obligation.write_text("(check-sat)\n", encoding="utf-8")
    result = run_formal_check(
        _spec(obligation="obligation.smt2", expect="unavailable"),
        base_dir=tmp_path,
        output_dir=tmp_path,
    )
    payload = result.metrics
    assert "formal_status" in payload
    assert "status_separation" in payload
    assert "never combined" in payload["status_separation"]
    # `success` is the pipeline flag; it is not the formal verdict
    assert result.success is not payload["formal_status"]


def test_provenance_fields_are_present(tmp_path):
    obligation = tmp_path / "obligation.smt2"
    obligation.write_text("(check-sat)\n", encoding="utf-8")
    result = run_formal_check(
        _spec(
            obligation="obligation.smt2",
            expect="unavailable",
            assumptions=("the encoding is faithful to the claim",),
            derives_from=("claim:demo", "analysis:demo-sweep"),
        ),
        base_dir=tmp_path,
        output_dir=tmp_path,
    )
    payload = result.metrics
    assert payload["obligation"]["sha256"]
    assert payload["obligation"]["bytes"] == obligation.stat().st_size
    assert payload["checker"]["backend"] == "z3"
    assert payload["assumptions"] == ["the encoding is faithful to the claim"]
    assert payload["derives_from"] == ["claim:demo", "analysis:demo-sweep"]


def test_config_rejects_unknown_backend(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: formal_check\n    title: t\n"
        "    backend: nonexistent\n    obligation: o.lean\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "backend must be one of" in str(exc.value)


def test_config_requires_a_jar_for_tlc(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: formal_check\n    title: t\n"
        "    backend: tlc\n    obligation: M.tla\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "requires a `jar` path" in str(exc.value)


def test_config_rejects_an_unknown_expectation(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: formal_check\n    title: t\n"
        "    backend: lean\n    obligation: o.lean\n    expect: proven\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "expect must be one of" in str(exc.value)


def test_tlc_verdict_refuses_to_resolve_a_transcript_exit_code_disagreement():
    from felra.formal import _verdict_tlc

    clean = "Model checking completed. No error has been found.\n"
    assert _verdict_tlc(0, clean)[0] == "verified"
    # the case that a real run produced: a clean transcript with a non-zero exit,
    # caused by a mangled path rather than by the model
    status, detail = _verdict_tlc(255, clean)
    assert status == "unknown"
    assert "disagree" in detail
    assert _verdict_tlc(12, "Error: Invariant Bounded is violated.")[0] == "refuted"


def test_a_declared_path_is_honoured_before_PATH(tmp_path):
    """A locally installed checker need not be on PATH.

    Added when z3 was installed under the shared tools directory: without this,
    the only way to reach a checker was to put it on PATH, which is a
    machine-wide change made for one project's benefit.
    """
    fake = tmp_path / "not-a-real-z3"
    identity = identify_checker("z3", path=fake)
    if identity.available:  # pragma: no cover - a real z3 is on PATH here
        pytest.skip("z3 is on PATH; the declared-path-absent case is untested here")
    assert identity.available is False
    # the declared path is reported, so the record says where it looked
    assert identity.executable_path == str(fake)
    assert identity.note and "declared `path`" in identity.note


def test_config_accepts_a_path_field(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: formal_check\n    title: t\n"
        "    backend: z3\n    obligation: o.smt2\n    path: /somewhere/z3\n",
        encoding="utf-8",
    )
    spec = load_project(project).analyses[0]
    assert spec.path == "/somewhere/z3"


def test_an_axiom_claim_about_nothing_is_not_verified():
    """The vacuity guard, and the reason `axioms_within` is safe to have.

    A file that prints no `#print axioms` audits no theorem. Reporting `verified`
    there would mean "no theorem exceeded the allowed axioms" of an empty set —
    the exact vacuous pass this package exists to refuse.
    """
    from felra.formal import _verdict_lean

    status, detail = _verdict_lean(0, "", axioms_within=("propext",))
    assert status == "unknown"
    assert "audited" in detail and "not a verified one" in detail

    # with no axiom claim declared, the same empty output is just a clean elaboration
    assert _verdict_lean(0, "")[0] == "verified"


def test_an_axiom_outside_the_declared_set_refutes():
    from felra.formal import _verdict_lean

    out = (
        "'Collatz.good' depends on axioms: [propext, Quot.sound]\n"
        "'Collatz.bad' depends on axioms: [propext, Collatz.myAxiom]\n"
    )
    status, detail = _verdict_lean(0, out, axioms_within=("propext", "Quot.sound"))
    assert status == "refuted"
    assert "Collatz.bad" in detail and "1 of 2" in detail


def test_both_print_axioms_output_forms_are_read():
    """A theorem depending on nothing prints the second form. Reading only the
    first silently drops the cleanest theorems in a development from the audit."""
    from felra.formal import parse_lean_axioms

    parsed = parse_lean_axioms(
        "'A' depends on axioms: [propext]\n"
        "'B' does not depend on any axioms\n"
    )
    assert parsed == {"A": ["propext"], "B": []}
    from felra.formal import _verdict_lean

    status, detail = _verdict_lean(
        0,
        "'A' depends on axioms: [propext]\n"
        "'B' does not depend on any axioms\n",
        axioms_within=("propext",),
    )
    assert status == "verified"
    assert "2 theorem(s)" in detail


def test_axioms_within_is_refused_on_a_backend_that_cannot_honour_it(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: formal_check\n    title: t\n"
        "    backend: z3\n    obligation: o.smt2\n"
        "    axioms_within: [propext]\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "only meaningful for the lean backend" in str(exc.value)
