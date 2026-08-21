"""Export a FELRA claim as a proof obligation, and prove it is discriminating.

Stage F's last item. Every other formal channel checks an obligation somebody
wrote; this one writes it.

The result is deliberately paired. The obligation asserts the declared domain and
the **negation** of the claim, so `unsat` is a proof over that domain. Its twin
asserts the same domain with the conclusion flipped. A faithful export makes
exactly one of the pair unsat — and if both come back the same, the obligation is
not discriminating and the verdict is `unknown`.

Without that pairing an exporter that emits something trivially unsatisfiable
would be reported as proving every claim it was given. The extra solver call is
the difference between a prover and a rubber stamp.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from felra.analysis.models import AnalysisResult
from felra.certificates import CertificateError, issue_external_formal_certificate
from felra.config import ObligationExportAnalysisSpec
from felra.formal import resolve_env_path, run_backend
from felra.obligation_export import ObligationExportError, export_smtlib


def run_obligation_export(
    spec: ObligationExportAnalysisSpec,
    project: Any,
    *,
    output_dir: Path,
) -> AnalysisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    claim = next((c for c in project.claims if c.claim_id == spec.claim_id), None)
    if claim is None:
        return AnalysisResult(
            analysis_id=spec.analysis_id, kind="obligation_export", title=spec.title,
            success=False,
            summary="no claim %r to export" % spec.claim_id,
            claim_id=spec.claim_id,
            metrics={"exported": False},
            warnings=["claim not found"],
        )

    parameters: dict[str, Any] = {}
    for name, p in project.parameters.items():
        entry: dict[str, Any] = {"type": p.kind}
        if p.minimum is not None and p.maximum is not None:
            entry["range"] = [p.minimum, p.maximum]
        elif p.values:
            # An explicit value list is a finite domain, and rendering it as a
            # range would widen the obligation to points the claim never covered.
            entry["values"] = list(p.values)
        parameters[name] = entry

    try:
        primary = export_smtlib(claim.claim_id, claim.expression, parameters)
        twin = export_smtlib(claim.claim_id, claim.expression, parameters,
                             negate_conclusion=True)
    except ObligationExportError as exc:
        return AnalysisResult(
            analysis_id=spec.analysis_id, kind="obligation_export", title=spec.title,
            success=False,
            summary="the claim cannot be rendered exactly: %s" % exc,
            claim_id=spec.claim_id,
            metrics={"exported": False, "expression": claim.expression,
                     "refusal": str(exc)},
            warnings=[
                "refused rather than approximated: an obligation that is nearly "
                "the claim is an obligation about a different claim"
            ],
        )

    primary_path = output_dir / "obligation.smt2"
    twin_path = output_dir / "obligation_twin.smt2"
    primary_path.write_text(primary, encoding="utf-8")
    twin_path.write_text(twin, encoding="utf-8")

    metrics: dict[str, Any] = {
        "exported": True,
        "expression": claim.expression,
        "parameters": parameters,
        # Where the files are, and — separately — what is in them. Only the second
        # belongs in `result_sha256`: a path changes when the output directory
        # changes, which is not a different result, while the content hash pins the
        # exact obligation the solver was asked about. `_NOT_PART_OF_THE_RESULT`
        # in `reproducibility.py` excludes the `_file` keys for that reason.
        "obligation_file": str(primary_path),
        "twin_file": str(twin_path),
        "obligation_sha256": hashlib.sha256(primary.encode("utf-8")).hexdigest(),
        "twin_sha256": hashlib.sha256(twin.encode("utf-8")).hexdigest(),
        "format": "smt-lib2",
        "note": (
            "the obligation asserts the domain and the NEGATION of the claim, so "
            "`unsat` is a proof over that domain and `sat` is a counterexample"
        ),
    }

    if spec.backend is None:
        return AnalysisResult(
            analysis_id=spec.analysis_id, kind="obligation_export", title=spec.title,
            success=True,
            summary="exported %s to SMT-LIB2; no backend declared, so nothing was "
                    "proved" % claim.claim_id,
            claim_id=spec.claim_id, metrics=metrics,
            warnings=["export only: an obligation nobody checked is a file"],
        )

    exe = resolve_env_path(spec.path)
    primary_outcome = run_backend(spec.backend, primary_path, path=exe,
                                  timeout=spec.timeout_seconds)
    twin_outcome = run_backend(spec.backend, twin_path, path=exe,
                               timeout=spec.timeout_seconds)
    metrics["primary"] = primary_outcome.as_dict()
    metrics["twin"] = twin_outcome.as_dict()

    a, b = primary_outcome.formal_status, twin_outcome.formal_status
    if "unavailable" in (a, b):
        status = "unavailable"
        detail = "the prover is not available, so the export was not checked"
    elif a == "verified" and b == "verified":
        # THE GUARD, and it took running a false claim to state it correctly.
        #
        # A first version refused whenever the pair AGREED, which turned a
        # perfectly good refutation into `unknown`: for a claim that holds at some
        # points and fails at others, both the obligation and its twin are
        # satisfiable, and that is the correct mathematical situation rather than a
        # broken export.
        #
        # What actually indicates a broken export is both coming back UNSAT: the
        # declared domain is itself unsatisfiable, so every obligation over it is
        # vacuously unsat and the solver would "prove" any claim at all.
        status = "unknown"
        detail = (
            "both the obligation and its twin are unsatisfiable, which means the "
            "declared domain is empty; every obligation over an empty domain is "
            "vacuously unsat, so no verdict is recorded"
        )
        warnings.append(detail)
    elif a == "verified":
        status = "verified"
        detail = ("no counterexample exists on the declared domain, and the twin "
                  "is satisfiable, so the domain is non-empty and the obligation "
                  "discriminates")
    else:
        status = "refuted"
        detail = ("the solver found a counterexample on the declared domain"
                  if b == "verified" else
                  "the solver found a counterexample; the twin is satisfiable too, "
                  "so the claim holds at some points of the domain and fails at "
                  "others")

    metrics["formal_status"] = status
    metrics["detail"] = detail
    # the domain is non-empty exactly when at least one of the pair is sat
    metrics["domain_is_nonempty"] = not (a == "verified" and b == "verified")
    metrics["discriminates"] = (
        "unavailable" not in (a, b) and metrics["domain_is_nonempty"])

    if status == "verified":
        try:
            metrics["certificates"] = [
                issue_external_formal_certificate(
                    "%s over its declared domain" % claim.claim_id,
                    primary_outcome.as_dict(),
                ).as_dict()
            ]
        except CertificateError as exc:            # pragma: no cover - defensive
            warnings.append("no certificate issued: %s" % exc)

    return AnalysisResult(
        analysis_id=spec.analysis_id,
        kind="obligation_export",
        title=spec.title,
        success=status == spec.expect,
        summary="%s → %s (expected %s): %s" % (spec.backend, status, spec.expect,
                                               detail),
        claim_id=spec.claim_id,
        metrics=metrics,
        warnings=warnings,
    )
