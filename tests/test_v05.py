import json
from pathlib import Path

from felra.config import PowerAnalysisSpec, RobustnessAnalysisSpec, load_project
from felra.data import load_dataset
from felra.runner import run_project


def test_jsonl_dataset_and_v05_config_parse() -> None:
    project = load_project("examples/robustness/project.yaml")
    dataset = load_dataset(project.datasets["trial"])
    assert dataset.row_count == 48
    assert dataset.spec.format == "jsonl"
    assert any(isinstance(item, PowerAnalysisSpec) for item in project.analyses)
    assert any(isinstance(item, RobustnessAnalysisSpec) for item in project.analyses)


def test_power_and_robustness_outputs(tmp_path: Path) -> None:
    output = tmp_path / "v05"
    run = run_project("examples/robustness/project.yaml", output)
    assert run.passed
    power = json.loads(
        (output / "analyses/independent_t_power/metrics.json").read_text(encoding="utf-8")
    )["metrics"]
    assert power["required_sample_size_group_1"] is not None
    assert power["achieved_power"] >= 0.8
    robustness = json.loads(
        (output / "analyses/treatment_effect_robustness/metrics.json").read_text(
            encoding="utf-8"
        )
    )["metrics"]
    assert robustness["repetitions_valid"] >= 900
    assert 0.0 <= robustness["sign_stability"] <= 1.0
    assert (output / "analyses/dose_score_robustness/robustness_distribution.csv").exists()


def test_analysis_cache_reuses_identical_run(tmp_path: Path) -> None:
    project_source = Path("examples/robustness/project.yaml").resolve()
    source_data = project_source.parent / "data/clinical_trial.jsonl"
    project_dir = tmp_path / "project"
    (project_dir / "data").mkdir(parents=True)
    (project_dir / "project.yaml").write_text(
        project_source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (project_dir / "data/clinical_trial.jsonl").write_bytes(source_data.read_bytes())

    first = tmp_path / "first"
    second = tmp_path / "second"
    run_project(project_dir / "project.yaml", first)
    second_run = run_project(project_dir / "project.yaml", second)
    assert second_run.passed
    metrics = json.loads(
        (second / "analyses/independent_t_power/metrics.json").read_text(encoding="utf-8")
    )["metrics"]
    assert metrics["cache_hit"] is True
    assert metrics["cache_fingerprint"]


def test_json_dataset_loads(tmp_path: Path) -> None:
    data = tmp_path / "records.json"
    data.write_text('[{"x": 1, "label": "a"}, {"x": 2, "label": "b"}]', encoding="utf-8")
    project = tmp_path / "project.yaml"
    project.write_text(
        """
project: {id: json_data}
datasets:
  d:
    path: records.json
    format: json
    columns: {x: int, label: str}
claims:
  - id: positive
    statement: x positive
    dataset: d
    expression: x > 0
""".strip(),
        encoding="utf-8",
    )
    loaded = load_project(project)
    dataset = load_dataset(loaded.datasets["d"])
    assert dataset.row_count == 2
    assert dataset.columns["x"].tolist() == [1, 2]


def test_gzipped_jsonl_dataset_loads(tmp_path: Path) -> None:
    import gzip

    data = tmp_path / "records.jsonl.gz"
    with gzip.open(data, "wt", encoding="utf-8") as handle:
        handle.write('{"x": 1}\n{"x": 2}\n')
    project = tmp_path / "project.yaml"
    project.write_text(
        """
project: {id: gz_data}
datasets:
  d:
    path: records.jsonl.gz
    format: jsonl
    columns: {x: int}
claims:
  - id: positive
    statement: x positive
    dataset: d
    expression: x > 0
""".strip(),
        encoding="utf-8",
    )
    loaded = load_project(project)
    dataset = load_dataset(loaded.datasets["d"])
    assert dataset.row_count == 2


def test_cli_version_is_v05() -> None:
    from felra import __version__

    assert __version__ == "0.7.0"
