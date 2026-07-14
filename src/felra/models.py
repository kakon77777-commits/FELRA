from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Claim:
    """A research claim that can be tested within an explicit computational domain."""

    claim_id: str
    statement: str
    status: str = "hypothesis"
    domain_description: str = "unspecified"


@dataclass(frozen=True)
class ValidationResult:
    """Result of one validation channel."""

    check_name: str
    passed: bool
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    counterexamples: tuple[dict[str, Any], ...] = ()


@dataclass
class EvidenceBundle:
    """Traceable evidence produced for a claim."""

    claim: Claim
    results: list[ValidationResult] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(result.passed for result in self.results)
