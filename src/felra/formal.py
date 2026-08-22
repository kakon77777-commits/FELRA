"""External formal-verification backends (whitepaper stage 4, first slice).

FELRA is a Python-first *evidence* workbench. This module is the seam where an
external formal checker may be invoked, and it is written around one rule taken
from the whitepaper's own stage-4 list:

    將 Python 證據狀態與正式證明狀態分開標記
    (mark Python evidence status and formal proof status separately)

So nothing here ever upgrades a Python result. A ``formal_check`` analysis carries
its own ``formal_status`` field, disjoint from the ``success`` flag every other
analysis type uses, and the two are reported side by side and never combined.
`AGENTS.md` §11 lists "changing the meaning of pass or proof" as requiring
approval; adding a *separate* status alongside is what keeps this addition from
being that change.

Three further rules, all of which exist because a formal result is only as good as
its provenance:

* **No dependency is added.** FELRA does not ship or require a solver. Each
  backend is an adapter over a program that may or may not be installed. When the
  program is absent the result is ``unavailable`` — never ``verified``, and never
  silently skipped.
* **The program is identified.** Every run records the checker's name, the exact
  command, its version string, its resolved path, and the SHA-256 of the
  executable or archive that ran. "A prover said yes" is not evidence; "this
  binary, with this hash, said yes" is.
* **The backend list is closed.** An unknown backend is refused rather than
  guessed at, and no command from a project file is ever executed directly. A
  project declares *which adapter* and *what obligation*, not *what to run*.

Backends are registered in `docs/FORMAL_BACKENDS.md`, which records for each one
what program it invokes, when it was added, and what real artifact it was
validated against. That register is the answer to "what program, and what
history" — it is a file rather than a memory on purpose.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "FORMAL_STATUSES",
    "BACKENDS",
    "CheckerIdentity",
    "FormalOutcome",
    "identify_checker",
    "run_backend",
]

#: The four outcomes a formal check may report. They are deliberately not
#: booleans: ``unknown`` (the checker ran and did not decide) and ``unavailable``
#: (the checker did not run) are different facts, and collapsing them is how a
#: missing tool becomes an implicit pass.
FORMAL_STATUSES = ("verified", "refuted", "unknown", "unavailable")

#: Closed set of adapters. Adding one is a documented act, not a config change.
BACKENDS = ("lean", "tlc", "z3")

_TIMEOUT_DEFAULT = 900


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


@dataclass
class CheckerIdentity:
    """Who actually ran. Recorded whether or not the check succeeded."""

    backend: str
    available: bool
    command: list[str] = field(default_factory=list)
    executable_path: str | None = None
    executable_sha256: str | None = None
    version_string: str | None = None
    note: str | None = None

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "available": self.available,
            "command": list(self.command),
            "executable_path": self.executable_path,
            "executable_sha256": self.executable_sha256,
            "version_string": self.version_string,
            "note": self.note,
        }


@dataclass
class FormalOutcome:
    """The verdict, plus everything needed to disbelieve it."""

    formal_status: str
    checker: CheckerIdentity
    obligation_path: str | None = None
    obligation_sha256: str | None = None
    obligation_bytes: int | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    detail: str = ""
    stdout_tail: str = ""
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    theorems_audited: int | None = None
    axioms_seen: list[str] | None = None

    def as_dict(self) -> dict:
        return {
            "formal_status": self.formal_status,
            "checker": self.checker.as_dict(),
            "obligation": {
                "path": self.obligation_path,
                "sha256": self.obligation_sha256,
                "bytes": self.obligation_bytes,
            },
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "detail": self.detail,
            "stdout_tail": self.stdout_tail,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
            "theorems_audited": self.theorems_audited,
            "axioms_seen": list(self.axioms_seen) if self.axioms_seen else None,
        }


def _run(command: list[str], cwd: Path | None, timeout: int) -> tuple[int, str, float]:
    import time

    started = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), time.monotonic() - started


# --------------------------------------------------------------------------
# adapters


def _identify_lean(project_dir: Path | None, path: Path | None = None) -> CheckerIdentity:
    exe = str(path) if path and path.exists() else shutil.which("lake")
    if exe is None:
        return CheckerIdentity(
            backend="lean",
            available=False,
            note="`lake` is not on PATH; Lean was not invoked",
        )
    try:
        _rc, out, _d = _run([exe, "--version"], project_dir, 120)
        version = out.strip().splitlines()[0] if out.strip() else None
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return CheckerIdentity(backend="lean", available=False, note=str(exc))
    return CheckerIdentity(
        backend="lean",
        available=True,
        command=[exe],
        executable_path=exe,
        executable_sha256=_sha256_file(Path(exe)),
        version_string=version,
    )


def _identify_tlc(jar: Path | None) -> CheckerIdentity:
    java = shutil.which("java")
    if java is None:
        return CheckerIdentity(
            backend="tlc", available=False, note="`java` is not on PATH"
        )
    if jar is None or not jar.exists():
        return CheckerIdentity(
            backend="tlc",
            available=False,
            executable_path=str(jar) if jar else None,
            note="tla2tools.jar not found at the declared `jar` path; TLC was "
            "not invoked. FELRA does not ship or download it.",
        )
    try:
        _rc, out, _d = _run([java, "-version"], None, 120)
        version = out.strip().splitlines()[0] if out.strip() else None
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return CheckerIdentity(backend="tlc", available=False, note=str(exc))
    return CheckerIdentity(
        backend="tlc",
        available=True,
        command=[java, "-jar", str(jar)],
        executable_path=str(jar),
        # the JAR is what decides, so the JAR is what gets hashed
        executable_sha256=_sha256_file(jar),
        version_string=version,
    )


def _identify_z3(path: Path | None = None) -> CheckerIdentity:
    # A declared path is honoured before PATH, so a project can name a locally
    # installed solver without it being on PATH and without FELRA depending on
    # one. Same shape as the `jar` field the TLC adapter already required.
    exe = str(path) if path and path.exists() else shutil.which("z3")
    if exe is None:
        return CheckerIdentity(
            backend="z3",
            available=False,
            executable_path=str(path) if path else None,
            note="`z3` was not found at the declared `path` nor on PATH; FELRA "
                 "does not depend on it",
        )
    try:
        _rc, out, _d = _run([exe, "--version"], None, 120)
        version = out.strip().splitlines()[0] if out.strip() else None
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return CheckerIdentity(backend="z3", available=False, note=str(exc))
    return CheckerIdentity(
        backend="z3",
        available=True,
        command=[exe],
        executable_path=exe,
        executable_sha256=_sha256_file(Path(exe)),
        version_string=version,
    )


def identify_checker(backend: str, *, project_dir: Path | None = None,
                     jar: Path | None = None,
                     path: Path | None = None) -> CheckerIdentity:
    """Resolve which program would run, without running the obligation."""
    if backend == "lean":
        return _identify_lean(project_dir, path)
    if backend == "tlc":
        return _identify_tlc(jar)
    if backend == "z3":
        return _identify_z3(path)
    raise ValueError(
        "unknown formal backend %r; known backends are %s. Backends are a closed "
        "set on purpose — see docs/FORMAL_BACKENDS.md." % (backend, ", ".join(BACKENDS))
    )


#: Lean's own three. A development whose theorems need nothing else is what
#: "machine-checked" is usually taken to mean, so the set is named rather than
#: assumed and a project must declare it.
LEAN_STANDARD_AXIOMS = ("propext", "Classical.choice", "Quot.sound")

_AXIOM_LINE = re.compile(r"'([^']+)' depends on axioms: \[([^\]]*)\]")
_AXIOM_FREE = re.compile(r"'([^']+)' does not depend on any axioms")


def parse_lean_axioms(out: str) -> dict[str, list[str]]:
    """Every theorem Lean reported on, and what it rests on.

    `#print axioms` has TWO output forms and a theorem depending on nothing prints
    the second one. Reading only the first silently drops the cleanest theorems in
    a development from the audit.
    """
    found: dict[str, list[str]] = {}
    for name, axioms in _AXIOM_LINE.findall(out):
        found[name] = sorted({a.strip() for a in axioms.split(",") if a.strip()})
    for name in _AXIOM_FREE.findall(out):
        found.setdefault(name, [])
    return found


def _verdict_lean(exit_code: int, out: str,
                  axioms_within: tuple[str, ...] | None = None) -> tuple[str, str]:
    if exit_code != 0:
        return "refuted", "the Lean file did not compile (exit %d)" % exit_code
    if "error:" in out:
        return "refuted", "Lean reported an error while elaborating the file"
    if "sorry" in out.lower():
        return "unknown", "Lean reported a `sorry`, so the obligation is incomplete"

    if axioms_within is None:
        return "verified", "Lean elaborated the obligation with no error"

    # An axiom claim about a file that audits nothing is the vacuous pass this
    # whole package exists to refuse. `verified` here would mean "no theorem
    # exceeded the allowed axioms" of an empty set of theorems.
    reported = parse_lean_axioms(out)
    if not reported:
        return "unknown", (
            "the obligation declared `axioms_within` but produced no `#print "
            "axioms` output, so no theorem was audited; an axiom claim about "
            "nothing is not a verified one"
        )
    allowed = set(axioms_within)
    exceeded = {name: axioms for name, axioms in reported.items()
                if not set(axioms) <= allowed}
    if exceeded:
        first = sorted(exceeded)[:3]
        return "refuted", (
            "%d of %d theorem(s) depend on an axiom outside the declared set, "
            "e.g. %s" % (len(exceeded), len(reported),
                         ", ".join("%s → %r" % (n, exceeded[n]) for n in first))
        )
    return "verified", (
        "%d theorem(s) audited; every one depends only on the declared axioms (%s)"
        % (len(reported), ", ".join(sorted(allowed)))
    )


def _verdict_tlc(exit_code: int, out: str) -> tuple[str, str]:
    """TLC's OUTPUT is the authority, not its exit code.

    Found by running the real tool: a first version returned `refuted` on exit
    255 for a model TLC had in fact checked cleanly — the non-zero code came from
    a path this adapter had mangled, not from the model. Trusting the exit code
    alone would have reported a good model as refuted; trusting the text alone
    would hide a genuine crash. So the two are compared, and a disagreement is
    reported as `unknown` rather than resolved in either direction.
    """
    clean = out.count("Model checking completed. No error has been found.")
    violated = "Error:" in out
    if violated:
        return "refuted", "TLC reported an error (exit %d)" % exit_code
    if clean == 0:
        return "unknown", (
            "TLC produced no completion line; the run was inconclusive (exit %d)"
            % exit_code
        )
    if exit_code != 0:
        return "unknown", (
            "TLC reported %d clean completion(s) but exited %d; the transcript and "
            "the exit code disagree, so no verdict is recorded" % (clean, exit_code)
        )
    return "verified", "TLC completed with no error (%d clean completion(s))" % clean


def _verdict_z3(exit_code: int, out: str) -> tuple[str, str]:
    text = out.strip().lower()
    if exit_code != 0 and not text:
        return "unknown", "z3 exited %d with no output" % exit_code
    if "unsat" in text:
        return "verified", "z3 reported unsat, so the negated obligation has no model"
    if text.startswith("sat") or "\nsat" in text:
        return "refuted", "z3 reported sat, so a counter-model exists"
    return "unknown", "z3 reported neither sat nor unsat"


def run_backend(
    backend: str,
    obligation: Path,
    *,
    project_dir: Path | None = None,
    jar: Path | None = None,
    config: Path | None = None,
    path: Path | None = None,
    timeout: int = _TIMEOUT_DEFAULT,
    assumptions: list[str] | None = None,
    limitations: list[str] | None = None,
    axioms_within: tuple[str, ...] | None = None,
) -> FormalOutcome:
    """Invoke `backend` on `obligation` and report a status plus its provenance.

    Never raises on a checker's verdict; raises only when the request itself is
    malformed (unknown backend, missing obligation file), because a malformed
    request must not be reported as a formal outcome at all.
    """
    identity = identify_checker(backend, project_dir=project_dir, jar=jar,
                                path=path)
    assumptions = list(assumptions or [])
    limitations = list(limitations or [])

    # Absolute from here on. The subprocess runs with its cwd set to the
    # obligation's directory, so a relative path would be resolved a second time
    # and vanish — which is exactly what happened the first time this adapter met
    # a real checker, and TLC's "file not found" exit was nearly recorded as a
    # refutation of the model.
    obligation = obligation.resolve()
    if config is not None:
        config = config.resolve()
    if not obligation.exists():
        raise FileNotFoundError(
            "formal obligation not found: %s" % obligation
        )
    ob_sha = _sha256_file(obligation)
    ob_bytes = obligation.stat().st_size

    if not identity.available:
        return FormalOutcome(
            formal_status="unavailable",
            checker=identity,
            obligation_path=str(obligation),
            obligation_sha256=ob_sha,
            obligation_bytes=ob_bytes,
            detail=identity.note or "the checker is not available on this machine",
            assumptions=assumptions,
            limitations=limitations + [
                "the obligation was not checked; `unavailable` is not a negative "
                "result and must not be reported as one"
            ],
        )

    if backend == "lean":
        command = identity.command + ["env", "lean", str(obligation)]
        cwd = project_dir
    elif backend == "tlc":
        command = identity.command + ["-config", str(config), str(obligation)] \
            if config else identity.command + [str(obligation)]
        cwd = obligation.parent
    else:  # z3
        command = identity.command + [str(obligation)]
        cwd = obligation.parent

    try:
        exit_code, out, duration = _run(command, cwd, timeout)
    except subprocess.TimeoutExpired:
        return FormalOutcome(
            formal_status="unknown",
            checker=identity,
            obligation_path=str(obligation),
            obligation_sha256=ob_sha,
            obligation_bytes=ob_bytes,
            detail="the checker exceeded the declared timeout of %ds" % timeout,
            assumptions=assumptions,
            limitations=limitations + ["timed out; no verdict was reached"],
        )

    if backend == "lean":
        verdict, detail = _verdict_lean(exit_code, out, axioms_within)
    elif backend == "tlc":
        verdict, detail = _verdict_tlc(exit_code, out)
    else:
        verdict, detail = _verdict_z3(exit_code, out)

    audited: dict[str, list[str]] = {}
    if backend == "lean" and axioms_within is not None:
        audited = parse_lean_axioms(out)

    return FormalOutcome(
        formal_status=verdict,
        checker=identity,
        obligation_path=str(obligation),
        obligation_sha256=ob_sha,
        obligation_bytes=ob_bytes,
        exit_code=exit_code,
        duration_seconds=round(duration, 3),
        detail=detail,
        stdout_tail=out[-2000:],
        assumptions=assumptions,
        limitations=limitations + [
            "a formal verdict is relative to the obligation as written; it says "
            "nothing about whether the obligation states the intended claim"
        ] + ([
            "the audit covers the theorems this file prints axioms for; a theorem "
            "the file never mentions is outside it"
        ] if audited else []),
        theorems_audited=len(audited) or None,
        axioms_seen=sorted({a for axioms in audited.values() for a in axioms}) or None,
    )


def resolve_env_path(value: str | None) -> Path | None:
    """Expand `${VAR}` and `~` in a declared path. Kept here so that project
    files can point at a locally installed tool without hardcoding a machine
    path into a public repository."""
    if not value:
        return None
    return Path(os.path.expandvars(os.path.expanduser(value)))
