"""Run an external formal checker and record the result *beside* the evidence.

The whitepaper's stage 4 asks for the Python evidence status and the formal proof
status to be marked separately. This runner is where that separation is enforced:

* ``AnalysisResult.success`` keeps its existing FELRA meaning — "this analysis ran
  and its declared expectation was met". It is **not** a claim that anything was
  proved.
* ``metrics["formal_status"]`` is the checker's verdict, one of
  ``verified`` / ``refuted`` / ``unknown`` / ``unavailable``.

The two can disagree, and when they do that is the reportable fact. A check whose
checker is absent reports ``success=True`` only when the project *declared*
``expect: unavailable``; otherwise a missing checker is a failed expectation, so a
machine without the tool cannot quietly turn into a machine that passed.

Provenance recorded on every run, per `AGENTS.md` §9.4:

* which program ran — name, command, resolved path, version string, SHA-256;
* what was checked — obligation path, its SHA-256, its size;
* what it rests on — declared assumptions and limitations;
* where it came from — ``derives_from``, the FELRA claim or analysis ids that
  produced the obligation.
"""

from __future__ import annotations

from pathlib import Path

from felra.analysis.models import AnalysisResult
from felra.config import FormalCheckAnalysisSpec
from felra.formal import resolve_env_path, run_backend


def run_formal_check(
    spec: FormalCheckAnalysisSpec,
    *,
    base_dir: Path,
    output_dir: Path,
) -> AnalysisResult:
    warnings: list[str] = []
    # Each runner owns its output directory on the success path; the engine only
    # creates one when an analysis raises.
    output_dir.mkdir(parents=True, exist_ok=True)

    obligation = resolve_env_path(spec.obligation)
    if obligation is not None and not obligation.is_absolute():
        obligation = (base_dir / obligation).resolve()
    project_dir = resolve_env_path(spec.project_dir)
    if project_dir is not None and not project_dir.is_absolute():
        project_dir = (base_dir / project_dir).resolve()
    jar = resolve_env_path(spec.jar)
    exe_path = resolve_env_path(spec.path)
    config_file = resolve_env_path(spec.config_file)
    if config_file is not None and not config_file.is_absolute():
        config_file = (base_dir / config_file).resolve()

    if obligation is None or not obligation.exists():
        # A missing obligation is a malformed request, not a formal verdict.
        return AnalysisResult(
            analysis_id=spec.analysis_id,
            kind="formal_check",
            title=spec.title,
            success=False,
            summary=(
                "the declared obligation does not exist: %s — no formal status is "
                "reported, because a request that cannot be made has no verdict"
                % spec.obligation
            ),
            claim_id=spec.claim_id,
            metrics={
                "backend": spec.backend,
                "formal_status": None,
                "obligation": {"declared": spec.obligation, "resolved": str(obligation)},
                "derives_from": list(spec.derives_from),
            },
            warnings=["obligation not found"],
        )

    outcome = run_backend(
        spec.backend,
        obligation,
        project_dir=project_dir,
        jar=jar,
        path=exe_path,
        config=config_file,
        timeout=spec.timeout_seconds,
        assumptions=list(spec.assumptions),
        limitations=list(spec.limitations),
        axioms_within=spec.axioms_within,
    )

    met = outcome.formal_status == spec.expect
    if outcome.formal_status == "unavailable" and spec.expect != "unavailable":
        warnings.append(
            "the checker is not installed on this machine, so the obligation was "
            "not checked; this is not evidence for or against the claim"
        )
    if outcome.formal_status == "unknown":
        warnings.append(
            "the checker ran without deciding; an undecided obligation is not a "
            "refutation"
        )
    if outcome.formal_status == "verified" and spec.expect == "verified":
        warnings.append(
            "a formal verdict is about the obligation as written; it does not "
            "establish that the obligation states the intended claim"
        )

    summary = "%s → formal_status=%s (expected %s): %s" % (
        spec.backend,
        outcome.formal_status,
        spec.expect,
        outcome.detail,
    )

    payload = outcome.as_dict()
    payload["expected_formal_status"] = spec.expect
    payload["expectation_met"] = met
    payload["derives_from"] = list(spec.derives_from)
    # Stated in the record itself rather than only in the docs, so an exported
    # bundle carries the distinction even when read out of context.
    payload["status_separation"] = (
        "`success` is FELRA's evidence-pipeline flag (the declared expectation was "
        "met); `formal_status` is the external checker's verdict. They are recorded "
        "separately and are never combined into a single notion of proof."
    )

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind="formal_check",
        title=spec.title,
        success=met,
        summary=summary,
        claim_id=spec.claim_id,
        metrics=payload,
        warnings=warnings,
    )
