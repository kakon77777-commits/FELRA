"""v1.8.0 — proof-obligation export (addendum stage F, its last item).

The translator tests below are pure. The verdict tests are not: they run a real
solver on a real export, because the thing being checked is whether FELRA reads a
solver's answer correctly, and a mock of z3 would be a mock of the answer.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from felra.config import ProjectConfigError, load_project
from felra.formal import identify_checker, resolve_env_path
from felra.obligation_export import ObligationExportError, export_smtlib

REAL_X = {"x": {"type": "float", "range": [-2, 3]}}


def _z3() -> str:
    """The declared z3, or a skip. Never a stub: see the module docstring."""
    declared = os.environ.get("Z3_EXE")
    path = resolve_env_path(declared) if declared else None
    if not identify_checker("z3", path=path).available:
        pytest.skip("z3 is not available; set Z3_EXE to run the verdict tests")
    return declared or "z3"


def _project(tmp_path: pathlib.Path, expression: str, *, expect: str,
             domain: str = "range: [-2, 3]") -> pathlib.Path:
    path = tmp_path / "project.yaml"
    path.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    " + domain + "\n    samples: 5\n"
        "claims:\n  - id: c\n    statement: s\n    expression: " + expression + "\n"
        "    status: hypothesis\n"
        "analyses:\n"
        "  - id: a\n    type: obligation_export\n    title: t\n    claim_id: c\n"
        "    backend: z3\n    path: ${Z3_EXE}\n    expect: " + expect + "\n",
        encoding="utf-8",
    )
    return path


def _run(tmp_path: pathlib.Path, expression: str, *, expect: str):
    from felra.analysis.obligation_export import run_obligation_export

    _z3()
    spec = load_project(_project(tmp_path, expression, expect=expect))
    return run_obligation_export(spec.analyses[0], spec,
                                 output_dir=tmp_path / "out")


# --------------------------------------------------------------------------
# the translator
# --------------------------------------------------------------------------

def test_the_obligation_asserts_the_NEGATION_of_the_claim():
    """`unsat` has to mean "no counterexample exists". If the obligation asserted
    the claim itself, `unsat` would mean the claim is unsatisfiable — the opposite
    reading, and one no solver can distinguish for you."""
    text = export_smtlib("c", "x >= 1", REAL_X)
    assert "(assert (not (>= x 1)))" in text
    assert "(check-sat)" in text
    assert "(declare-const x Real)" in text
    assert "(assert (and (>= x (- 2)) (<= x 3)))" in text


def test_the_twin_flips_only_the_conclusion():
    primary = export_smtlib("c", "x >= 1", REAL_X)
    twin = export_smtlib("c", "x >= 1", REAL_X, negate_conclusion=True)
    assert "(assert (not (>= x 1)))" in primary
    assert "(assert (>= x 1))" in twin
    domain = "(assert (and (>= x (- 2)) (<= x 3)))"
    assert domain in primary and domain in twin, \
        "the pair is only comparable if the domain is identical in both"


def test_integer_powers_become_repeated_multiplication():
    assert "(* x x x)" in export_smtlib("c", "x ** 3 >= 0", REAL_X)
    assert "(assert (not (>= 1 0)))" in export_smtlib("c", "x ** 0 >= 0", REAL_X)


def test_a_finite_value_list_is_a_disjunction_not_a_range():
    """Widening an explicit value list to [min, max] would make the obligation
    cover points the claim never spoke about. A proof of the wider statement is
    not a proof of this one, and a counterexample in the gap is not a
    counterexample to it."""
    text = export_smtlib("c", "n > 0", {"n": {"type": "int", "values": [1, 2, 5]}})
    assert "(assert (or (= n 1) (= n 2) (= n 5)))" in text
    assert ">=" not in text.split("(assert (or")[1]


def test_an_empty_value_list_is_refused():
    with pytest.raises(ObligationExportError) as exc:
        export_smtlib("c", "n > 0", {"n": {"type": "int", "values": []}})
    assert "vacuously unsat" in str(exc.value)


def test_whatever_cannot_be_rendered_exactly_is_refused():
    """An obligation that is NEARLY the claim is an obligation about a different
    claim, and a solver's verdict on it is worth nothing."""
    for expression in (
        "sin(x) >= 0",          # a function call
        "x ** 0.5 >= 0",        # a non-integer exponent
        "x ** n >= 0",          # a symbolic exponent
        "x",                    # a number used as a truth value
        "x // 2 >= 0",          # floor division has no exact rendering here
    ):
        with pytest.raises(ObligationExportError):
            export_smtlib("c", expression,
                          {"x": {"type": "float", "range": [-2, 3]},
                           "n": {"type": "int", "range": [1, 3]}})


def test_a_chained_comparison_becomes_a_conjunction():
    assert "(and (<= 0 x) (<= x 3))" in export_smtlib("c", "0 <= x <= 3", REAL_X)


def test_an_unsupported_parameter_type_is_refused():
    with pytest.raises(ObligationExportError) as exc:
        export_smtlib("c", "x >= 0", {"x": {"type": "str"}})
    assert "no SMT sort" in str(exc.value)


def test_an_unbounded_parameter_is_noted_rather_than_invented():
    text = export_smtlib("c", "x >= 0", {"x": {"type": "float"}})
    assert "unbounded" in text
    assert "(declare-const x Real)" in text


# --------------------------------------------------------------------------
# the verdicts, against a real solver
# --------------------------------------------------------------------------

def test_a_claim_true_on_the_whole_domain_is_verified(tmp_path):
    result = _run(tmp_path, "x ** 2 >= 0", expect="verified")
    assert result.metrics["formal_status"] == "verified"
    assert result.metrics["primary"]["formal_status"] == "verified"
    assert result.metrics["twin"]["formal_status"] == "refuted", \
        "the twin must be SAT, or the domain could be empty and the proof vacuous"
    assert result.metrics["domain_is_nonempty"] is True
    assert result.metrics["discriminates"] is True
    assert result.metrics["certificates"], "a proof should leave a certificate"
    assert result.success is True


def test_a_claim_false_everywhere_on_the_domain_is_refuted(tmp_path):
    result = _run(tmp_path, "x ** 2 < 0", expect="refuted")
    assert result.metrics["formal_status"] == "refuted"
    assert result.metrics["primary"]["formal_status"] == "refuted"
    assert result.metrics["twin"]["formal_status"] == "verified"
    assert "certificates" not in result.metrics
    assert result.success is True


def test_a_claim_true_at_some_points_and_false_at_others_is_refuted(tmp_path):
    """The case that exposed the first version of the guard.

    `x >= 1` on [-2, 3] holds at some points and fails at others, so BOTH the
    obligation and its twin are satisfiable. A guard that refused whenever the
    pair agreed turned this perfectly good refutation into `unknown`.
    """
    result = _run(tmp_path, "x >= 1", expect="refuted")
    assert result.metrics["primary"]["formal_status"] == "refuted"
    assert result.metrics["twin"]["formal_status"] == "refuted"
    assert result.metrics["formal_status"] == "refuted"
    assert result.metrics["domain_is_nonempty"] is True
    assert "holds at some points" in result.metrics["detail"]


def test_an_empty_domain_is_reported_unknown_rather_than_proved(tmp_path,
                                                                monkeypatch):
    """The guard, exercised by injecting the defect it exists for.

    A well-formed project cannot declare an empty domain — `load_project` refuses
    an inverted range — so the vacuous case is only reachable through a defect in
    the exporter itself. That is exactly what this plants: an export whose domain
    constraints contradict. Real z3 then answers `unsat` to the obligation AND to
    its twin, and a FELRA without this guard would report the claim proved.

    Nothing here mocks the solver. The planted defect is in FELRA's own output.
    """
    from felra.analysis import obligation_export as module

    real = module.export_smtlib

    def contradictory(claim_id, expression, parameters, **kwargs):
        text = real(claim_id, expression, parameters, **kwargs)
        # a domain no point satisfies, inserted before the conclusion
        return text.replace("(check-sat)",
                            "(assert (> x 100))\n(assert (< x 0))\n(check-sat)")

    monkeypatch.setattr(module, "export_smtlib", contradictory)
    result = _run(tmp_path, "x ** 2 >= 0", expect="verified")

    assert result.metrics["primary"]["formal_status"] == "verified", \
        "the planted defect should make the obligation vacuously unsat"
    assert result.metrics["twin"]["formal_status"] == "verified"
    assert result.metrics["formal_status"] == "unknown", \
        "both unsat means the domain is empty; a claim is not proved by vacuity"
    assert result.metrics["domain_is_nonempty"] is False
    assert result.metrics["discriminates"] is False
    assert "certificates" not in result.metrics, \
        "no certificate may be issued for a vacuous proof"
    assert any("empty" in w for w in result.warnings)
    assert result.success is False, "expect: verified, and it was not verified"


def test_without_the_guard_the_planted_defect_would_pass(tmp_path, monkeypatch):
    """The other half of the pair: that the injected defect is actually invisible
    to the primary check alone. If the obligation on its own already looked wrong,
    the guard above would be catching something the plain check catches too, and
    would not be evidence of anything."""
    from felra.analysis import obligation_export as module

    real = module.export_smtlib

    def contradictory(claim_id, expression, parameters, **kwargs):
        text = real(claim_id, expression, parameters, **kwargs)
        return text.replace("(check-sat)",
                            "(assert (> x 100))\n(assert (< x 0))\n(check-sat)")

    monkeypatch.setattr(module, "export_smtlib", contradictory)
    # a FALSE claim, which the defect makes look proved
    result = _run(tmp_path, "x >= 1", expect="refuted")
    assert result.metrics["primary"]["formal_status"] == "verified", \
        "z3 proves a false claim over the empty domain — this is the whole danger"
    assert result.metrics["formal_status"] == "unknown", \
        "and the twin is what stops FELRA from believing it"


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

def test_config_requires_a_claim_id(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "analyses:\n"
        "  - id: a\n    type: obligation_export\n    title: t\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "requires a claim_id" in str(exc.value)


def test_config_refuses_a_backend_that_cannot_read_smtlib(tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "claims:\n  - id: c\n    statement: s\n    expression: x >= 0\n"
        "    status: hypothesis\n"
        "analyses:\n"
        "  - id: a\n    type: obligation_export\n    title: t\n"
        "    claim_id: c\n    backend: lean\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError) as exc:
        load_project(project)
    assert "only the z3 backend" in str(exc.value)


def test_an_inverted_range_never_reaches_the_exporter(tmp_path):
    """Why the guard above had to plant its own defect."""
    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [3, -2]\n    samples: 3\n"
        "claims:\n  - id: c\n    statement: s\n    expression: x >= 0\n"
        "    status: hypothesis\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError):
        load_project(project)


def test_export_without_a_backend_proves_nothing_and_says_so(tmp_path):
    from felra.analysis.obligation_export import run_obligation_export

    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [-2, 3]\n    samples: 3\n"
        "claims:\n  - id: c\n    statement: s\n    expression: x ** 2 >= 0\n"
        "    status: hypothesis\n"
        "analyses:\n"
        "  - id: a\n    type: obligation_export\n    title: t\n    claim_id: c\n",
        encoding="utf-8",
    )
    spec = load_project(project)
    out = tmp_path / "out"
    result = run_obligation_export(spec.analyses[0], spec, output_dir=out)
    assert result.success is True
    assert "formal_status" not in result.metrics, \
        "no backend ran, so there is no formal verdict to record"
    assert any("nobody checked" in w for w in result.warnings)
    assert (out / "obligation.smt2").exists()
    assert (out / "obligation_twin.smt2").exists()


def test_an_unrenderable_claim_fails_the_analysis_rather_than_approximating(tmp_path):
    from felra.analysis.obligation_export import run_obligation_export

    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "claims:\n  - id: c\n    statement: s\n    expression: sin(x) >= 0\n"
        "    status: hypothesis\n"
        "analyses:\n"
        "  - id: a\n    type: obligation_export\n    title: t\n    claim_id: c\n",
        encoding="utf-8",
    )
    spec = load_project(project)
    result = run_obligation_export(spec.analyses[0], spec, output_dir=tmp_path / "o")
    assert result.success is False
    assert result.metrics["exported"] is False
    assert "refusal" in result.metrics
    assert not (tmp_path / "o" / "obligation.smt2").exists(), \
        "a refused claim must not leave an obligation file behind"


# --------------------------------------------------------------------------
# reproducibility — the guard that would have caught a seven-version-old defect
# --------------------------------------------------------------------------

REPRODUCIBLE_EXAMPLES = [
    "basic",              # no formal backend
    "formal_check",       # v1.1.0; unreproducible from v1.1.0 until v1.8.0
    "obligation_export",  # v1.8.0
]


@pytest.mark.parametrize("example", REPRODUCIBLE_EXAMPLES)
def test_fingerprints_are_stable_across_runs(example, tmp_path):
    """The same project, run twice, must produce the same `result_sha256`.

    This is not a new promise — it is what the fingerprint has always meant, and
    what `felra replay` compares against. It had simply never been checked by
    running anything twice.

    It should have been. `duration_seconds` entered the hashed payload with the
    formal backends in v1.1.0, and from that version until this one every formal
    analysis produced a different fingerprint on every run: `felra replay`
    reported MISMATCH on projects nobody had touched. The exclusion list is a
    denylist and denylists only know what someone remembered to add, which is
    precisely how a stopwatch reading stayed inside an identity for seven
    versions. THIS test is the guard — it needs no one to think of the key's name.
    """
    from felra.reproducibility import result_sha256
    from felra.runner import run_project

    project = pathlib.Path("examples") / example / "project.yaml"
    if not project.exists():
        pytest.skip("%s is not present" % example)
    if example != "basic":
        _z3()

    digests = [result_sha256(run_project(project, tmp_path / ("run%d" % i)))
               for i in (1, 2)]

    assert digests[0] == digests[1], (
        "%s produced two different fingerprints for the same inputs; something "
        "that is not a result (a wall-clock reading, an output path) is inside "
        "the identity" % example
    )


@pytest.mark.parametrize("example", ["formal_check", "obligation_export"])
def test_replay_matches_for_a_formal_project(example, tmp_path):
    """`felra replay` must reproduce a formal project, not report it missing.

    Until v1.8.0 it could not. Datasets were captured into the run directory and
    the replay project rewritten to point at those copies; formal obligations were
    not captured at all. So replaying an untouched `formal_check` project produced
    "the declared obligation does not exist" for every analysis and MISMATCH for
    the project — which reads as *the result did not reproduce*, when in fact the
    checker was never handed the file.

    `obligation_export` is here as the contrast: it generates its obligation from
    the claim, so there is no external file to lose, and it matched even before
    the capture existed. Two examples, one with an external dependency and one
    without, keep this test from passing for the wrong reason.
    """
    from felra.reproducibility import replay_run
    from felra.runner import run_project

    project = pathlib.Path("examples") / example / "project.yaml"
    if not project.exists():
        pytest.skip("%s is not present" % example)
    _z3()

    run_project(project, tmp_path / "original")
    verdict = replay_run(tmp_path / "original", tmp_path / "replay")
    assert verdict["matched"] is True, verdict

    for report in (tmp_path / "replay").rglob("analysis_report.md"):
        assert "does not exist" not in report.read_text(encoding="utf-8"), \
            "%s lost its obligation on replay" % report


def test_an_env_declared_obligation_is_captured_not_pinned(tmp_path, monkeypatch):
    """An obligation declared as `${VAR}` must end up captured into the run, and
    the replay project must name the run's own copy rather than either the
    variable or a machine path.

    A first version of the capture skipped anything containing `${`, on the theory
    that expanding it would pin one machine's environment into the replay project.
    That theory was wrong twice over. It pins nothing — the declaration is
    rewritten to a run-relative path, so the replay needs neither the variable nor
    the machine. And the guard was dead anyway: an unexpanded `${VAR}` is not a
    path that exists, so the existence check already skipped it. Removing the
    guard changed no behaviour at all, which is how the drill found it — the
    defect survived, and nothing went red.
    """
    from felra.reproducibility import write_replay_project
    from felra.runner import run_project

    obligation = tmp_path / "declared_elsewhere.smt2"
    obligation.write_text("(set-logic AUFNIRA)\n(assert false)\n(check-sat)\n",
                          encoding="utf-8")
    monkeypatch.setenv("FELRA_TEST_OBLIGATION", str(obligation))

    project = tmp_path / "project.yaml"
    project.write_text(
        "project:\n  id: p\n  title: t\n"
        "parameters:\n  x:\n    type: float\n    range: [0, 1]\n    samples: 3\n"
        "claims:\n  - id: c\n    statement: s\n    expression: x >= 0\n"
        "    status: hypothesis\n"
        "analyses:\n"
        "  - id: env_declared\n    type: formal_check\n    title: t\n"
        "    backend: z3\n    obligation: ${FELRA_TEST_OBLIGATION}\n"
        "    path: ${Z3_EXE}\n    expect: verified\n",
        encoding="utf-8",
    )
    _z3()

    run = run_project(project, tmp_path / "out")
    text = write_replay_project(run).read_text(encoding="utf-8")

    assert (tmp_path / "out" / "obligations" / "env_declared"
            / "declared_elsewhere.smt2").exists(), "the obligation was not captured"
    assert "obligations/env_declared/declared_elsewhere.smt2" in text
    assert "${FELRA_TEST_OBLIGATION}" not in text, \
        "the replay would still depend on the variable being set"
    assert str(tmp_path) not in text.replace(
        "obligations/env_declared/declared_elsewhere.smt2", ""), \
        "a machine path leaked into the replay project"


def test_an_unset_variable_leaves_the_declaration_alone(tmp_path, monkeypatch):
    """The other half: nothing is invented when the file cannot be found. Replay
    then reports it missing, which is the truth about that run."""
    from felra.reproducibility import _capture_obligations

    monkeypatch.delenv("FELRA_TEST_OBLIGATION", raising=False)
    raw = {"analyses": [{"id": "a", "type": "formal_check",
                         "obligation": "${FELRA_TEST_OBLIGATION}"}]}

    class _Run:
        output_dir = tmp_path
        project = type("P", (), {"source_path": None})()

    assert _capture_obligations(_Run(), raw) == []
    assert raw["analyses"][0]["obligation"] == "${FELRA_TEST_OBLIGATION}"
