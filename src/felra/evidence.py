from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from felra.models import EvidenceBundle


def _jsonable(bundle: EvidenceBundle) -> dict[str, Any]:
    return {
        "claim": {
            "id": bundle.claim.claim_id,
            "statement": bundle.claim.statement,
            "status": bundle.claim.status,
            "domain_description": bundle.claim.domain_description,
        },
        "created_at": bundle.created_at,
        "passed": bundle.passed,
        "metadata": bundle.metadata,
        "results": [
            {
                "check_name": result.check_name,
                "passed": result.passed,
                "summary": result.summary,
                "metrics": result.metrics,
                "counterexamples": list(result.counterexamples),
            }
            for result in bundle.results
        ],
        "figures": bundle.figures,
    }


def write_evidence_bundle(bundle: EvidenceBundle, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    payload = _jsonable(bundle)
    (output / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    status = "SUPPORTED IN DECLARED DOMAIN" if bundle.passed else "NOT SUPPORTED"
    lines = [
        "# FELRA Validation Report",
        "",
        f"- Claim ID: `{bundle.claim.claim_id}`",
        f"- Statement: {bundle.claim.statement}",
        f"- Declared domain: {bundle.claim.domain_description}",
        f"- Result: **{status}**",
        f"- Generated at: `{bundle.created_at}`",
        "",
        "> This report records finite-budget machine validation. It is not a universal proof.",
        "",
        "## Reproducibility metadata",
        "",
    ]
    lines.extend(
        f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`"
        for key, value in bundle.metadata.items()
    )
    lines.extend(["", "## Validation channels", ""])

    for result in bundle.results:
        lines.extend(
            [
                f"### {result.check_name}",
                "",
                f"- Passed: `{result.passed}`",
                f"- Summary: {result.summary}",
                f"- Metrics: `{json.dumps(result.metrics, ensure_ascii=False)}`",
                "",
            ]
        )
        if result.counterexamples:
            lines.append("Counterexamples:")
            lines.append("")
            for item in result.counterexamples:
                lines.append(f"- `{json.dumps(item, ensure_ascii=False)}`")
            lines.append("")

    if bundle.figures:
        lines.extend(["## Figures", ""])
        lines.extend(f"- `{path}`" for path in bundle.figures)
        lines.append("")

    (output / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
