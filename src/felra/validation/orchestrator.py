from __future__ import annotations

from collections.abc import Callable, Iterable

from felra.models import Claim, EvidenceBundle, ValidationResult

Check = Callable[[], ValidationResult]


class VerificationOrchestrator:
    """Run multiple verification channels and collect them into one evidence bundle."""

    def __init__(self, claim: Claim) -> None:
        self.claim = claim
        self._checks: list[Check] = []

    def add_check(self, check: Check) -> "VerificationOrchestrator":
        self._checks.append(check)
        return self

    def add_checks(self, checks: Iterable[Check]) -> "VerificationOrchestrator":
        self._checks.extend(checks)
        return self

    def run(self) -> EvidenceBundle:
        if not self._checks:
            raise RuntimeError("At least one validation check is required")
        return EvidenceBundle(claim=self.claim, results=[check() for check in self._checks])
