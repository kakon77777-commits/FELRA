from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from felra.analysis.effect import adjust_pvalues, independent_effect_sizes
from felra.config import (
    CrossValidationAnalysisSpec,
    ModelComparisonAnalysisSpec,
    MultipleComparisonAnalysisSpec,
    load_project,
)
from felra.registry import filter_registry_records, load_registry_records
from felra.runner import run_project


ROOT = Path(__file__).resolve().parents[1]


def test_pvalue_corrections_are_monotone_and_bounded() -> None:
    raw = np.asarray([0.01, 0.04, 0.03, 0.2])
    bonferroni = adjust_pvalues(raw, "bonferroni")
    holm = adjust_pvalues(raw, "holm")
    fdr = adjust_pvalues(raw, "fdr_bh")
    assert np.all((0.0 <= bonferroni) & (bonferroni <= 1.0))
    assert np.all((0.0 <= holm) & (holm <= 1.0))
    assert np.all((0.0 <= fdr) & (fdr <= 1.0))
    assert bonferroni[0] == pytest.approx(0.04)
    assert holm[0] == pytest.approx(0.04)
    assert fdr[0] == pytest.approx(0.04)


def test_standardized_effect_sizes_include_hedges_g() -> None:
    x = np.asarray([3.0, 4.0, 5.0, 6.0])
    y = np.asarray([1.0, 2.0, 3.0, 4.0])
    effects = independent_effect_sizes(x, y)
    assert effects["cohen_d"] > 0
    assert effects["hedges_g"] > 0
    assert abs(effects["hedges_g"]) < abs(effects["cohen_d"])


def test_v06_config_loads_new_analysis_types() -> None:
    project = load_project(ROOT / "examples/research_registry/project.yaml")
    assert isinstance(project.analyses[0], MultipleComparisonAnalysisSpec)
    assert isinstance(project.analyses[1], CrossValidationAnalysisSpec)
    assert isinstance(project.analyses[2], ModelComparisonAnalysisSpec)
    assert project.registry.enabled is True


def test_v06_project_runs_and_registers(tmp_path: Path) -> None:
    source_project = ROOT / "examples/research_registry/project.yaml"
    raw = source_project.read_text(encoding="utf-8")
    raw = raw.replace(
        "path: .felra-registry/research_runs.jsonl",
        f"path: {str(tmp_path / 'registry.jsonl')}",
    )
    project_file = tmp_path / "project.yaml"
    project_file.write_text(raw, encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_dir.joinpath("synthetic_study.csv").write_bytes(
        (ROOT / "examples/research_registry/data/synthetic_study.csv").read_bytes()
    )

    output = tmp_path / "artifacts"
    run = run_project(project_file, output)
    assert run.passed
    assert run.registry_record is not None
    assert (output / "registry_record.json").exists()
    records = load_registry_records(tmp_path / "registry.jsonl")
    assert len(records) == 1
    assert records[0]["project_id"] == "v06_research_registry_demo"
    assert filter_registry_records(records, passed=True) == records

    comparison_metrics = json.loads(
        (output / "analyses/shared_fold_model_comparison/metrics.json").read_text(
            encoding="utf-8"
        )
    )["metrics"]
    assert comparison_metrics["best_model"] == "polynomial_degree_2"
    assert comparison_metrics["shared_fold_plan"] is True

    multiple_metrics = json.loads(
        (output / "analyses/corrected_group_comparisons/metrics.json").read_text(
            encoding="utf-8"
        )
    )["metrics"]
    assert multiple_metrics["family_size"] == 3
    assert all("adjusted_p" in row for row in multiple_metrics["comparisons"])
