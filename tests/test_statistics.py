import json
from pathlib import Path

from felra.runner import run_project


def test_hypothesis_results_are_recorded(tmp_path: Path) -> None:
    output = tmp_path / "stats"
    run_project("examples/data/project.yaml", output)
    metrics = json.loads(
        (output / "analyses/treatment_score_test/metrics.json").read_text(encoding="utf-8")
    )
    assert metrics["metrics"]["test"] == "independent_t"
    assert 0.0 <= metrics["metrics"]["p_value"] <= 1.0
    assert metrics["metrics"]["sample_sizes"] == {"control": 24, "treatment": 24}


def test_bootstrap_is_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_project("examples/data/project.yaml", first)
    run_project("examples/data/project.yaml", second)
    first_metrics = json.loads(
        (first / "analyses/score_bootstrap_ci/metrics.json").read_text(encoding="utf-8")
    )["metrics"]
    second_metrics = json.loads(
        (second / "analyses/score_bootstrap_ci/metrics.json").read_text(encoding="utf-8")
    )["metrics"]
    assert first_metrics["ci_lower"] == second_metrics["ci_lower"]
    assert first_metrics["ci_upper"] == second_metrics["ci_upper"]
