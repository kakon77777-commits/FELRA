from pathlib import Path

from felra.config import load_project
from felra.data import load_dataset
from felra.runner import run_project


def test_dataset_loads_with_declared_schema() -> None:
    project = load_project("examples/data/project.yaml")
    dataset = load_dataset(project.datasets["trial"])
    assert dataset.row_count == 48
    assert dataset.columns["age"].dtype.kind in {"i", "u"}
    assert dataset.quality.missing_by_column["note"] > 0


def test_data_project_runs_claims_and_statistics(tmp_path: Path) -> None:
    output = tmp_path / "data"
    run = run_project("examples/data/project.yaml", output)
    assert run.passed
    assert len(run.datasets) == 1
    assert len(run.analyses) == 5
    assert (output / "datasets/trial/normalized.csv").exists()
    assert (output / "datasets/trial/quality.json").exists()
    assert (output / "analyses/grouped_descriptives/descriptive_summary.csv").exists()
    assert (output / "analyses/score_bootstrap_ci/bootstrap_distribution.csv").exists()


def test_dataset_claim_records_bad_row(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x\n1\n-1\n", encoding="utf-8")
    project = tmp_path / "project.yaml"
    project.write_text(
        f"""
project: {{id: bad_data}}
datasets:
  d:
    path: {data.name}
    columns: {{x: float}}
claims:
  - id: c
    statement: x is positive
    dataset: d
    expression: x > 0
    required_checks: [dataset_rows]
""".strip(),
        encoding="utf-8",
    )
    run = run_project(project, tmp_path / "out")
    assert not run.passed
    assert run.bundles[0].results[0].counterexamples
