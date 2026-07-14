from pathlib import Path

import pytest

from felra.config import ProjectConfigError, load_project


def test_load_basic_project() -> None:
    project = load_project(Path("examples/basic/project.yaml"))
    assert project.project_id == "nonnegative_square"
    assert project.claims[0].expression == "x ** 2 >= 0"
    assert len(project.figures) == 2


def test_missing_expression_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "project.yaml"
    path.write_text(
        "project: {id: bad}\nparameters: {x: {range: [0, 1]}}\n"
        "claims: [{id: c, statement: missing}]\n",
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError):
        load_project(path)
