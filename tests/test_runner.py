from pathlib import Path

from felra.runner import run_project


def test_run_declarative_project(tmp_path: Path) -> None:
    output = tmp_path / "artifacts"
    run = run_project("examples/basic/project.yaml", output)
    assert run.passed
    assert (output / "manifest.json").exists()
    assert (output / "project_report.md").exists()
    assert (output / "claims/claim_001/metrics.json").exists()
    assert len(run.figures) == 2


def test_counterexample_is_captured(tmp_path: Path) -> None:
    project = tmp_path / "project.yaml"
    project.write_text(
        """
project: {id: false_claim, title: False claim}
execution: {max_evaluations: 100, random_samples: 100, seed: 1}
parameters:
  x: {type: float, range: [-1, 1], samples: 11}
claims:
  - id: c1
    statement: x is always positive
    expression: x > 0
    required_checks: [numerical]
outputs: {figures: []}
""".strip(),
        encoding="utf-8",
    )
    run = run_project(project, tmp_path / "out")
    assert not run.passed
    assert run.bundles[0].results[0].counterexamples
