import numpy as np

from felra.models import Claim
from felra.validation import VerificationOrchestrator, validate_predicate


def test_predicate_passes_on_declared_domain() -> None:
    result = validate_predicate(lambda x: x * x >= 0, np.linspace(-5, 5, 101))
    assert result.passed
    assert result.metrics["tested_count"] == 101
    assert not result.counterexamples


def test_predicate_records_counterexample() -> None:
    result = validate_predicate(lambda x: x > 0, [-1, 0, 1])
    assert not result.passed
    assert result.counterexamples


def test_orchestrator_collects_results() -> None:
    claim = Claim("claim_test", "x² is non-negative")
    bundle = (
        VerificationOrchestrator(claim)
        .add_check(lambda: validate_predicate(lambda x: x * x >= 0, [-1, 0, 1]))
        .run()
    )
    assert bundle.passed
    assert len(bundle.results) == 1
