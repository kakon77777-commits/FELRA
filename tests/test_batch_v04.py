import csv
from pathlib import Path

from felra.batch import run_batch


def test_repeated_parallel_batch_expands_and_aggregates(tmp_path: Path) -> None:
    output = tmp_path / "batch"
    run = run_batch("examples/repeated_batch/batch.yaml", output, workers=2)
    assert run.passed
    assert run.workers == 2
    assert len(run.experiments) == 3
    assert {item.replicate_index for item in run.experiments} == {1, 2, 3}
    with (output / "replicate_summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["group_id"] == "trial_replicates"
    assert rows[0]["repetitions"] == "3"
