from pathlib import Path

import numpy as np

from felra.analysis.pareto import _pareto_mask_two_objectives
from felra.config import load_project
from felra.runner import run_project


def test_v03_analysis_config_parses() -> None:
    project = load_project("examples/advanced/project.yaml")
    assert len(project.analyses) == 4
    assert {analysis.kind for analysis in project.analyses} == {
        "sensitivity",
        "residual",
        "parameter_sweep",
        "pareto",
    }


def test_advanced_project_produces_analysis_evidence(tmp_path: Path) -> None:
    output = tmp_path / "advanced"
    run = run_project("examples/advanced/project.yaml", output)
    assert run.passed
    assert len(run.analyses) == 4
    assert all(result.success for result in run.analyses)
    assert (output / "analyses/local_sensitivity/sensitivity.csv").exists()
    assert (output / "analyses/taylor_residual/residuals.csv").exists()
    assert (output / "analyses/parameter_landscape/best_points.json").exists()
    assert (output / "analyses/accuracy_complexity_tradeoff/pareto_frontier.csv").exists()


def test_pareto_mask_respects_strict_dominance_and_duplicates() -> None:
    values = np.asarray(
        [
            [1.0, 4.0],
            [2.0, 2.0],
            [3.0, 1.0],
            [2.0, 3.0],
            [2.0, 2.0],
        ]
    )
    mask = _pareto_mask_two_objectives(values, ("minimize", "minimize"))
    assert mask.tolist() == [True, True, True, False, True]
