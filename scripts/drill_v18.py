#!/usr/bin/env python
"""Drill the v1.8.0 proof-obligation export by planting defects in it.

A green test suite is evidence that the code passes its tests. It is not evidence
that the tests would notice if the code broke. For a module whose entire job is
to decide whether a solver proved something, that distinction is the whole point:
the failure mode being guarded against — an exporter that emits a trivially
unsatisfiable obligation and is therefore reported as proving everything — looks
exactly like success from the inside.

So each defect below is planted in the real source, the real suite is run against
it with a real solver, and the run is required to fail **by the check named for
that defect**. A defect caught only by some other test is recorded as a miss: it
means the named check is not aimed at the thing it claims to cover, and the next
refactor can un-aim it without anyone noticing.

Every anchor is required to match exactly once. An anchor that matches zero times
(the code moved) or twice (the anchor is ambiguous) is a broken drill, not a
passing one, and is reported as such rather than skipped.

    python scripts/drill_v18.py

Exits non-zero if any defect survives, is caught by the wrong check, or has an
anchor that no longer matches. Requires `Z3_EXE`; without a solver the verdict
defects cannot be planted at all and the drill refuses to report a score.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNNER = ROOT / "src" / "felra" / "analysis" / "obligation_export.py"
TRANSLATOR = ROOT / "src" / "felra" / "obligation_export.py"
REPRO = ROOT / "src" / "felra" / "reproducibility.py"
SUITE = "tests/test_v18.py"

# (label, file, anchor, replacement, the check that must go red)
DEFECTS = [
    (
        "D1  the vacuity guard is deleted",
        RUNNER,
        'elif a == "verified" and b == "verified":',
        "elif False:",
        "test_an_empty_domain_is_reported_unknown_rather_than_proved",
    ),
    (
        "D2  domain_is_nonempty is hardcoded true",
        RUNNER,
        'metrics["domain_is_nonempty"] = not (a == "verified" and b == "verified")',
        'metrics["domain_is_nonempty"] = True',
        "test_an_empty_domain_is_reported_unknown_rather_than_proved",
    ),
    (
        "D3  the twin is not negated, so the pair is identical",
        RUNNER,
        "twin = export_smtlib(claim.claim_id, claim.expression, parameters,\n"
        "                             negate_conclusion=True)",
        "twin = export_smtlib(claim.claim_id, claim.expression, parameters)",
        "test_a_claim_true_on_the_whole_domain_is_verified",
    ),
    (
        "D4  the obligation asserts the claim instead of its negation",
        TRANSLATOR,
        'conclusion = body if negate_conclusion else "(not %s)" % body',
        'conclusion = "(not %s)" % body if negate_conclusion else body',
        "test_the_obligation_asserts_the_NEGATION_of_the_claim",
    ),
    (
        "D5  a finite value list is widened to a range",
        TRANSLATOR,
        'lines.append("(assert (or %s))" % " ".join(\n'
        '                "(= %s %s)" % (name, _num(v)) for v in options))',
        'lines.append("(assert (and (>= %s %s) (<= %s %s)))"\n'
        "                         % (name, _num(min(options)), name, "
        "_num(max(options))))",
        "test_a_finite_value_list_is_a_disjunction_not_a_range",
    ),
    (
        "D6  a non-integer exponent is approximated instead of refused",
        TRANSLATOR,
        "raise ObligationExportError(\n"
        '                    "only a literal non-negative integer exponent can be '
        'rendered "\n'
        '                    "exactly; %s cannot" % ast.unparse(node)\n'
        "                )",
        'return "(^ %s %s)" % (_term(node.left, names), '
        "_term(node.right, names))",
        "test_whatever_cannot_be_rendered_exactly_is_refused",
    ),
    (
        "D7  an empty value list is allowed through",
        TRANSLATOR,
        "raise ObligationExportError(\n"
        '                    "parameter %r has an empty value list, so its domain '
        'is empty "\n'
        '                    "and every obligation over it is vacuously unsat" % '
        "name)",
        'lines.append("; empty value list"); continue',
        "test_an_empty_value_list_is_refused",
    ),
    (
        "D8  a certificate is issued for an undecided verdict",
        RUNNER,
        'if status == "verified":',
        'if status in ("verified", "unknown"):',
        "test_an_empty_domain_is_reported_unknown_rather_than_proved",
    ),
    # The three below cover the reproducibility defects v1.8.0 found in code that
    # had shipped since v1.1.0. They are drilled here because a fix nobody can
    # break on purpose is a fix nobody has tested.
    (
        "D9  the wall clock is back inside the fingerprint",
        REPRO,
        '    "duration_seconds",                     # wall clock\n',
        "",
        "test_fingerprints_are_stable_across_runs[formal_check]",
    ),
    (
        "D10 formal obligations are no longer captured into the run",
        REPRO,
        "    _capture_obligations(run, raw)\n",
        "",
        "test_replay_matches_for_a_formal_project[formal_check]",
    ),
    (
        "D11 an obligation declared as ${VAR} is never found, so never captured",
        REPRO,
        "source = resolve_env_path(str(declared))",
        "source = Path(str(declared))",
        "test_an_env_declared_obligation_is_captured_not_pinned",
    ),
    (
        "D12 a declaration that resolves to nothing is copied anyway",
        REPRO,
        "            if not source.exists():\n                continue\n",
        "",
        "test_an_unset_variable_leaves_the_declaration_alone",
    ),
]


def _run_suite(env: dict) -> tuple[bool, set[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header", "--tb=no", "-rf"],
        capture_output=True, text=True, cwd=ROOT, env=env,
    )
    red = set(re.findall(r"(?:FAILED|ERROR) tests/test_v18\.py::(\S+)", proc.stdout))
    skipped = " skipped" in proc.stdout
    return skipped, red


def main() -> int:
    env = dict(os.environ)
    if not env.get("Z3_EXE"):
        print("Z3_EXE is not set. The verdict defects cannot be planted without a\n"
              "solver, and a drill that silently skips half its table is worse than\n"
              "no drill. Set Z3_EXE and run again.", file=sys.stderr)
        return 2

    originals = {p: p.read_text(encoding="utf-8") for p in (RUNNER, TRANSLATOR, REPRO)}

    skipped, red = _run_suite(env)
    if red:
        print("the suite is not green before planting anything: %s" % sorted(red),
              file=sys.stderr)
        return 2
    if skipped:
        print("the suite skipped a test; z3 is probably not resolving from Z3_EXE",
              file=sys.stderr)
        return 2
    print("baseline green, nothing skipped\n")

    misses = 0
    try:
        for label, path, anchor, replacement, expected in DEFECTS:
            source = originals[path]
            hits = source.count(anchor)
            if hits != 1:
                print("BROKEN  %s\n        its anchor matches %d times; the drill is "
                      "not aimed at anything" % (label, hits))
                misses += 1
                continue

            path.write_text(source.replace(anchor, replacement), encoding="utf-8")
            try:
                _, red = _run_suite(env)
            finally:
                path.write_text(source, encoding="utf-8")

            if expected in red:
                extra = sorted(red - {expected})
                print("CAUGHT  %s\n        by %s%s"
                      % (label, expected,
                         "  (also red: %s)" % ", ".join(extra) if extra else ""))
            else:
                misses += 1
                print("MISSED  %s\n        %s stayed green; red instead: %s"
                      % (label, expected, sorted(red) or "NOTHING — it survived"))
    finally:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")

    caught = len(DEFECTS) - misses
    print("\n%d/%d planted defects caught by the check named for them"
          % (caught, len(DEFECTS)))
    return 0 if misses == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
