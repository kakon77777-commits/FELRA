from felra.config import BootstrapCIAnalysisSpec, DescriptiveAnalysisSpec, load_project


def test_v04_data_config_parses() -> None:
    project = load_project("examples/data/project.yaml")
    assert not project.parameters
    assert "trial" in project.datasets
    assert any(isinstance(item, DescriptiveAnalysisSpec) for item in project.analyses)
    assert any(isinstance(item, BootstrapCIAnalysisSpec) for item in project.analyses)
