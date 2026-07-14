from pathlib import Path

from felra.batch import run_batch


def test_batch_runs_with_overrides(tmp_path: Path) -> None:
    output = tmp_path / "batch"
    run = run_batch("examples/batch/batch.yaml", output)
    assert run.passed
    assert len(run.experiments) == 2
    assert (output / "batch_manifest.json").exists()
    assert (output / "batch_summary.csv").exists()
    assert (output / "resolved_projects/low_budget.yaml").exists()
