from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

import yaml


class ProjectConfigError(ValueError):
    """Raised when a FELRA project file is incomplete or inconsistent."""


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    kind: str = "float"
    minimum: float | int | None = None
    maximum: float | int | None = None
    samples: int = 101
    values: tuple[float | int, ...] = ()

    @classmethod
    def from_mapping(cls, name: str, data: dict[str, Any]) -> "ParameterSpec":
        kind = str(data.get("type", "float"))
        if kind not in {"float", "int"}:
            raise ProjectConfigError(f"Parameter {name!r} has unsupported type {kind!r}")
        explicit_values = tuple(data.get("values", ()))
        range_value = data.get("range")
        minimum: float | int | None = None
        maximum: float | int | None = None
        if range_value is not None:
            if not isinstance(range_value, (list, tuple)) or len(range_value) != 2:
                raise ProjectConfigError(f"Parameter {name!r} range must contain [min, max]")
            minimum, maximum = range_value
            if minimum > maximum:
                raise ProjectConfigError(f"Parameter {name!r} range minimum exceeds maximum")
        if not explicit_values and range_value is None:
            raise ProjectConfigError(
                f"Parameter {name!r} requires either explicit values or a numeric range"
            )
        samples = int(data.get("samples", len(explicit_values) or 101))
        if samples < 1:
            raise ProjectConfigError(f"Parameter {name!r} samples must be positive")
        return cls(
            name=name,
            kind=kind,
            minimum=minimum,
            maximum=maximum,
            samples=samples,
            values=explicit_values,
        )


@dataclass(frozen=True)
class DatasetColumnSpec:
    name: str
    kind: str = "float"
    required: bool = True

    @classmethod
    def from_mapping(cls, name: str, data: Any) -> "DatasetColumnSpec":
        if isinstance(data, str):
            kind = data
            required = True
        elif isinstance(data, dict):
            kind = str(data.get("type", "float"))
            required = bool(data.get("required", True))
        else:
            raise ProjectConfigError(f"Dataset column {name!r} must be a type string or mapping")
        if kind not in {"float", "int", "str", "bool"}:
            raise ProjectConfigError(f"Dataset column {name!r} has unsupported type {kind!r}")
        return cls(name=name, kind=kind, required=required)


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    path: Path
    format: str
    columns: dict[str, DatasetColumnSpec]
    delimiter: str = ","
    encoding: str = "utf-8"
    on_error: str = "drop"
    missing_values: tuple[str, ...] = ("", "na", "n/a", "null", "none", "nan")

    @classmethod
    def from_mapping(
        cls,
        dataset_id: str,
        data: dict[str, Any],
        *,
        base_dir: Path,
    ) -> "DatasetSpec":
        if "path" not in data:
            raise ProjectConfigError(f"Dataset {dataset_id!r} requires a path")
        format_name = str(data.get("format", "csv")).lower()
        if format_name != "csv":
            raise ProjectConfigError("v0.4 supports CSV datasets only")
        raw_columns = data.get("columns")
        if not isinstance(raw_columns, dict) or not raw_columns:
            raise ProjectConfigError(f"Dataset {dataset_id!r} requires a non-empty columns mapping")
        columns = {
            str(name): DatasetColumnSpec.from_mapping(str(name), column)
            for name, column in raw_columns.items()
        }
        delimiter = str(data.get("delimiter", ","))
        if len(delimiter) != 1:
            raise ProjectConfigError("Dataset delimiter must be exactly one character")
        on_error = str(data.get("on_error", "drop"))
        if on_error not in {"drop", "error", "keep"}:
            raise ProjectConfigError("Dataset on_error must be drop, error, or keep")
        raw_path = Path(str(data["path"])).expanduser()
        path = raw_path if raw_path.is_absolute() else (base_dir / raw_path).resolve()
        missing_values = tuple(str(item) for item in data.get("missing_values", cls.missing_values))
        return cls(
            dataset_id=dataset_id,
            path=path,
            format=format_name,
            columns=columns,
            delimiter=delimiter,
            encoding=str(data.get("encoding", "utf-8")),
            on_error=on_error,
            missing_values=missing_values,
        )


@dataclass(frozen=True)
class ClaimSpec:
    claim_id: str
    statement: str
    expression: str
    status: str = "hypothesis"
    required_checks: tuple[str, ...] = ("numerical",)
    max_counterexamples: int = 20
    dataset: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ClaimSpec":
        required = {"id", "statement", "expression"}
        missing = sorted(required.difference(data))
        if missing:
            raise ProjectConfigError(f"Claim is missing required fields: {', '.join(missing)}")
        dataset = str(data["dataset"]) if data.get("dataset") is not None else None
        default_checks = ("dataset_rows",) if dataset else ("numerical",)
        checks = tuple(str(item) for item in data.get("required_checks", default_checks))
        supported = {"dataset_rows"} if dataset else {
            "numerical",
            "boundaries",
            "counterexample_search",
        }
        unknown = sorted(set(checks).difference(supported))
        if unknown:
            raise ProjectConfigError(f"Unsupported validation checks: {', '.join(unknown)}")
        max_counterexamples = int(data.get("max_counterexamples", 20))
        if max_counterexamples < 0:
            raise ProjectConfigError("max_counterexamples must be non-negative")
        return cls(
            claim_id=str(data["id"]),
            statement=str(data["statement"]),
            expression=str(data["expression"]),
            status=str(data.get("status", "hypothesis")),
            required_checks=checks,
            max_counterexamples=max_counterexamples,
            dataset=dataset,
        )


@dataclass(frozen=True)
class FigureSpec:
    figure_id: str
    kind: str
    filename: str
    title: str
    x: str | None = None
    y: str | None = None
    z: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    bins: int = 40
    claim_id: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any], index: int) -> "FigureSpec":
        kind = str(data.get("type", "line"))
        supported = {"line", "scatter", "histogram", "heatmap", "contour", "phase_map"}
        if kind not in supported:
            raise ProjectConfigError(f"Unsupported figure type {kind!r}")
        figure_id = str(data.get("id", f"figure_{index:03d}"))
        filename = str(data.get("filename", f"{figure_id}.png"))
        if Path(filename).suffix.lower() not in {".png", ".svg", ".pdf"}:
            raise ProjectConfigError("Figure filename must end in .png, .svg, or .pdf")
        bins = int(data.get("bins", 40))
        if bins < 1:
            raise ProjectConfigError("Figure histogram bins must be positive")
        return cls(
            figure_id=figure_id,
            kind=kind,
            filename=filename,
            title=str(data.get("title", figure_id)),
            x=data.get("x"),
            y=data.get("y"),
            z=data.get("z"),
            xlabel=data.get("xlabel"),
            ylabel=data.get("ylabel"),
            bins=bins,
            claim_id=data.get("claim_id"),
        )


@dataclass(frozen=True)
class ExecutionSpec:
    max_evaluations: int = 200_000
    random_samples: int = 20_000
    seed: int = 42

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "ExecutionSpec":
        data = data or {}
        max_evaluations = int(data.get("max_evaluations", 200_000))
        random_samples = int(data.get("random_samples", 20_000))
        if max_evaluations < 1 or random_samples < 1:
            raise ProjectConfigError("Execution budgets must be positive")
        return cls(
            max_evaluations=max_evaluations,
            random_samples=random_samples,
            seed=int(data.get("seed", 42)),
        )


@dataclass(frozen=True)
class BaseAnalysisSpec:
    analysis_id: str
    kind: str
    title: str
    claim_id: str | None = None


@dataclass(frozen=True)
class SensitivityAnalysisSpec(BaseAnalysisSpec):
    expression: str = ""
    parameters: tuple[str, ...] = ()
    baseline: dict[str, float | int] = field(default_factory=dict)
    relative_step: float = 1e-4
    absolute_step: float | None = None


@dataclass(frozen=True)
class ResidualAnalysisSpec(BaseAnalysisSpec):
    reference: str = ""
    approximation: str = ""
    independent: str | None = None
    tolerance: float | None = None
    bins: int = 40


@dataclass(frozen=True)
class SweepAnalysisSpec(BaseAnalysisSpec):
    objective: str = ""
    parameters: tuple[str, ...] = ()
    goal: str = "minimize"
    fixed: dict[str, float | int] = field(default_factory=dict)
    top_k: int = 20


@dataclass(frozen=True)
class ParetoObjectiveSpec:
    name: str
    expression: str
    goal: str = "minimize"


@dataclass(frozen=True)
class ParetoAnalysisSpec(BaseAnalysisSpec):
    objectives: tuple[ParetoObjectiveSpec, ...] = ()
    parameters: tuple[str, ...] = ()
    fixed: dict[str, float | int] = field(default_factory=dict)


@dataclass(frozen=True)
class DescriptiveAnalysisSpec(BaseAnalysisSpec):
    dataset: str = ""
    columns: tuple[str, ...] = ()
    group_by: str | None = None
    confidence: float = 0.95
    bins: int = 30


@dataclass(frozen=True)
class HypothesisTestAnalysisSpec(BaseAnalysisSpec):
    dataset: str = ""
    test: str = ""
    columns: tuple[str, ...] = ()
    column: str | None = None
    group_by: str | None = None
    groups: tuple[str, ...] = ()
    mu: float = 0.0
    equal_var: bool = False
    alternative: str = "two-sided"
    alpha: float = 0.05


@dataclass(frozen=True)
class BootstrapCIAnalysisSpec(BaseAnalysisSpec):
    dataset: str = ""
    column: str = ""
    statistic: str = "mean"
    confidence: float = 0.95
    resamples: int = 5000
    seed: int | None = None


AnalysisSpec: TypeAlias = (
    SensitivityAnalysisSpec
    | ResidualAnalysisSpec
    | SweepAnalysisSpec
    | ParetoAnalysisSpec
    | DescriptiveAnalysisSpec
    | HypothesisTestAnalysisSpec
    | BootstrapCIAnalysisSpec
)


def _require_fields(data: dict[str, Any], fields: set[str], *, context: str) -> None:
    missing = sorted(fields.difference(data))
    if missing:
        raise ProjectConfigError(f"{context} is missing required fields: {', '.join(missing)}")


def _numeric_mapping(value: Any, *, field_name: str) -> dict[str, float | int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ProjectConfigError(f"{field_name} must be a mapping")
    output: dict[str, float | int] = {}
    for key, item in value.items():
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise ProjectConfigError(f"{field_name}.{key} must be numeric")
        output[str(key)] = item
    return output


def _probability(value: Any, *, field_name: str) -> float:
    result = float(value)
    if not 0.0 < result < 1.0:
        raise ProjectConfigError(f"{field_name} must be strictly between 0 and 1")
    return result


def _parse_analysis(data: dict[str, Any], index: int) -> AnalysisSpec:
    kind = str(data.get("type", "")).strip()
    analysis_id = str(data.get("id", f"analysis_{index:03d}"))
    title = str(data.get("title", analysis_id))
    claim_id = data.get("claim_id")
    base = {
        "analysis_id": analysis_id,
        "kind": kind,
        "title": title,
        "claim_id": str(claim_id) if claim_id is not None else None,
    }

    if kind == "sensitivity":
        _require_fields(data, {"expression"}, context=f"Analysis {analysis_id!r}")
        relative_step = float(data.get("relative_step", 1e-4))
        absolute_step_raw = data.get("absolute_step")
        absolute_step = None if absolute_step_raw is None else float(absolute_step_raw)
        if relative_step <= 0 or (absolute_step is not None and absolute_step <= 0):
            raise ProjectConfigError("Sensitivity step sizes must be positive")
        return SensitivityAnalysisSpec(
            **base,
            expression=str(data["expression"]),
            parameters=tuple(str(item) for item in data.get("parameters", ())),
            baseline=_numeric_mapping(data.get("baseline"), field_name="baseline"),
            relative_step=relative_step,
            absolute_step=absolute_step,
        )

    if kind == "residual":
        _require_fields(data, {"reference", "approximation"}, context=f"Analysis {analysis_id!r}")
        tolerance_raw = data.get("tolerance")
        tolerance = None if tolerance_raw is None else float(tolerance_raw)
        if tolerance is not None and tolerance < 0:
            raise ProjectConfigError("Residual tolerance must be non-negative")
        bins = int(data.get("bins", 40))
        if bins < 1:
            raise ProjectConfigError("Residual bins must be positive")
        return ResidualAnalysisSpec(
            **base,
            reference=str(data["reference"]),
            approximation=str(data["approximation"]),
            independent=str(data["independent"]) if data.get("independent") else None,
            tolerance=tolerance,
            bins=bins,
        )

    if kind == "parameter_sweep":
        _require_fields(data, {"objective"}, context=f"Analysis {analysis_id!r}")
        goal = str(data.get("goal", "minimize"))
        if goal not in {"minimize", "maximize"}:
            raise ProjectConfigError("Parameter sweep goal must be minimize or maximize")
        top_k = int(data.get("top_k", 20))
        if top_k < 1:
            raise ProjectConfigError("Parameter sweep top_k must be positive")
        return SweepAnalysisSpec(
            **base,
            objective=str(data["objective"]),
            parameters=tuple(str(item) for item in data.get("parameters", ())),
            goal=goal,
            fixed=_numeric_mapping(data.get("fixed"), field_name="fixed"),
            top_k=top_k,
        )

    if kind == "pareto":
        raw_objectives = data.get("objectives")
        if not isinstance(raw_objectives, list) or len(raw_objectives) != 2:
            raise ProjectConfigError("v0.4 Pareto analysis requires exactly two objectives")
        objectives: list[ParetoObjectiveSpec] = []
        names: list[str] = []
        for objective in raw_objectives:
            if not isinstance(objective, dict):
                raise ProjectConfigError("Pareto objectives must be mappings")
            _require_fields(objective, {"name", "expression"}, context="Pareto objective")
            goal = str(objective.get("goal", "minimize"))
            if goal not in {"minimize", "maximize"}:
                raise ProjectConfigError("Pareto objective goal must be minimize or maximize")
            name = str(objective["name"])
            names.append(name)
            objectives.append(
                ParetoObjectiveSpec(name=name, expression=str(objective["expression"]), goal=goal)
            )
        if len(names) != len(set(names)):
            raise ProjectConfigError("Pareto objective names must be unique")
        return ParetoAnalysisSpec(
            **base,
            objectives=tuple(objectives),
            parameters=tuple(str(item) for item in data.get("parameters", ())),
            fixed=_numeric_mapping(data.get("fixed"), field_name="fixed"),
        )

    if kind == "descriptive":
        _require_fields(data, {"dataset", "columns"}, context=f"Analysis {analysis_id!r}")
        columns = tuple(str(item) for item in data["columns"])
        if not columns:
            raise ProjectConfigError("Descriptive analysis requires at least one column")
        bins = int(data.get("bins", 30))
        if bins < 1:
            raise ProjectConfigError("Descriptive bins must be positive")
        return DescriptiveAnalysisSpec(
            **base,
            dataset=str(data["dataset"]),
            columns=columns,
            group_by=str(data["group_by"]) if data.get("group_by") else None,
            confidence=_probability(data.get("confidence", 0.95), field_name="confidence"),
            bins=bins,
        )

    if kind == "hypothesis_test":
        _require_fields(data, {"dataset", "test"}, context=f"Analysis {analysis_id!r}")
        test = str(data["test"])
        supported_tests = {
            "one_sample_t",
            "independent_t",
            "paired_t",
            "mann_whitney",
            "wilcoxon",
            "pearson",
            "spearman",
        }
        if test not in supported_tests:
            raise ProjectConfigError(f"Unsupported hypothesis test {test!r}")
        alternative = str(data.get("alternative", "two-sided"))
        if alternative not in {"two-sided", "less", "greater"}:
            raise ProjectConfigError("alternative must be two-sided, less, or greater")
        raw_columns = data.get("columns", ())
        columns = tuple(str(item) for item in raw_columns)
        raw_groups = data.get("groups", ())
        groups = tuple(str(item) for item in raw_groups)
        return HypothesisTestAnalysisSpec(
            **base,
            dataset=str(data["dataset"]),
            test=test,
            columns=columns,
            column=str(data["column"]) if data.get("column") else None,
            group_by=str(data["group_by"]) if data.get("group_by") else None,
            groups=groups,
            mu=float(data.get("mu", 0.0)),
            equal_var=bool(data.get("equal_var", False)),
            alternative=alternative,
            alpha=_probability(data.get("alpha", 0.05), field_name="alpha"),
        )

    if kind == "bootstrap_ci":
        _require_fields(data, {"dataset", "column"}, context=f"Analysis {analysis_id!r}")
        statistic = str(data.get("statistic", "mean"))
        if statistic not in {"mean", "median"}:
            raise ProjectConfigError("Bootstrap statistic must be mean or median")
        resamples = int(data.get("resamples", 5000))
        if resamples < 100:
            raise ProjectConfigError("Bootstrap resamples must be at least 100")
        return BootstrapCIAnalysisSpec(
            **base,
            dataset=str(data["dataset"]),
            column=str(data["column"]),
            statistic=statistic,
            confidence=_probability(data.get("confidence", 0.95), field_name="confidence"),
            resamples=resamples,
            seed=int(data["seed"]) if data.get("seed") is not None else None,
        )

    raise ProjectConfigError(
        f"Unsupported analysis type {kind!r}; expected sensitivity, residual, parameter_sweep, "
        "pareto, descriptive, hypothesis_test, or bootstrap_ci"
    )


@dataclass(frozen=True)
class ProjectSpec:
    project_id: str
    title: str
    language: str
    parameters: dict[str, ParameterSpec]
    datasets: dict[str, DatasetSpec]
    claims: tuple[ClaimSpec, ...]
    figures: tuple[FigureSpec, ...] = ()
    analyses: tuple[AnalysisSpec, ...] = ()
    execution: ExecutionSpec = field(default_factory=ExecutionSpec)
    source_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)


def _validate_analysis_references(project: ProjectSpec) -> None:
    available_parameters = set(project.parameters)
    claim_ids = {claim.claim_id for claim in project.claims}
    for claim in project.claims:
        if claim.dataset and claim.dataset not in project.datasets:
            raise ProjectConfigError(
                f"Claim {claim.claim_id!r} references unknown dataset {claim.dataset!r}"
            )
        if not claim.dataset and not project.parameters:
            raise ProjectConfigError(
                f"Parameter claim {claim.claim_id!r} requires at least one parameter"
            )

    for analysis in project.analyses:
        if analysis.claim_id and analysis.claim_id not in claim_ids:
            raise ProjectConfigError(
                f"Analysis {analysis.analysis_id!r} references unknown claim {analysis.claim_id!r}"
            )
        if isinstance(
            analysis,
            (DescriptiveAnalysisSpec, HypothesisTestAnalysisSpec, BootstrapCIAnalysisSpec),
        ):
            if analysis.dataset not in project.datasets:
                raise ProjectConfigError(
                    f"Analysis {analysis.analysis_id!r} references unknown dataset "
                    f"{analysis.dataset!r}"
                )
            dataset_columns = set(project.datasets[analysis.dataset].columns)
            referenced: set[str] = set()
            if isinstance(analysis, DescriptiveAnalysisSpec):
                referenced.update(analysis.columns)
                if analysis.group_by:
                    referenced.add(analysis.group_by)
            elif isinstance(analysis, HypothesisTestAnalysisSpec):
                referenced.update(analysis.columns)
                if analysis.column:
                    referenced.add(analysis.column)
                if analysis.group_by:
                    referenced.add(analysis.group_by)
            else:
                referenced.add(analysis.column)
            unknown = sorted(referenced.difference(dataset_columns))
            if unknown:
                raise ProjectConfigError(
                    f"Analysis {analysis.analysis_id!r} references unknown dataset columns: "
                    f"{', '.join(unknown)}"
                )
            continue

        referenced_parameters: set[str] = set()
        fixed: dict[str, float | int] = {}
        if isinstance(analysis, SensitivityAnalysisSpec):
            referenced_parameters.update(analysis.parameters)
            referenced_parameters.update(analysis.baseline)
        elif isinstance(analysis, ResidualAnalysisSpec):
            if analysis.independent:
                referenced_parameters.add(analysis.independent)
        elif isinstance(analysis, (SweepAnalysisSpec, ParetoAnalysisSpec)):
            referenced_parameters.update(analysis.parameters)
            fixed = analysis.fixed
            referenced_parameters.update(fixed)
        unknown = sorted(referenced_parameters.difference(available_parameters))
        if unknown:
            raise ProjectConfigError(
                f"Analysis {analysis.analysis_id!r} references unknown parameters: "
                f"{', '.join(unknown)}"
            )
        overlap = set(getattr(analysis, "parameters", ())).intersection(fixed)
        if overlap:
            raise ProjectConfigError(
                f"Analysis {analysis.analysis_id!r} cannot vary and fix the same parameters: "
                f"{', '.join(sorted(overlap))}"
            )


def load_project(path: str | Path) -> ProjectSpec:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProjectConfigError("Project YAML root must be a mapping")

    project_data = raw.get("project") or {}
    project_id = str(project_data.get("id", source.parent.name or source.stem))
    title = str(project_data.get("title", project_id))
    language = str(project_data.get("language", "en"))

    parameter_data = raw.get("parameters") or {}
    if not isinstance(parameter_data, dict):
        raise ProjectConfigError("parameters must be a mapping")
    parameters = {
        str(name): ParameterSpec.from_mapping(str(name), dict(data))
        for name, data in parameter_data.items()
    }

    raw_datasets = raw.get("datasets") or {}
    if not isinstance(raw_datasets, dict):
        raise ProjectConfigError("datasets must be a mapping")
    datasets = {
        str(dataset_id): DatasetSpec.from_mapping(
            str(dataset_id), dict(data), base_dir=source.resolve().parent
        )
        for dataset_id, data in raw_datasets.items()
    }

    claim_data = raw.get("claims") or []
    if not isinstance(claim_data, list):
        raise ProjectConfigError("claims must be a list")
    claims = tuple(ClaimSpec.from_mapping(dict(item)) for item in claim_data)
    claim_ids = [claim.claim_id for claim in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ProjectConfigError("Claim IDs must be unique")

    output_data = raw.get("outputs") or {}
    raw_figures = output_data.get("figures", [])
    if not isinstance(raw_figures, list):
        raise ProjectConfigError("outputs.figures must be a list")
    figures = tuple(
        FigureSpec.from_mapping(dict(item), index)
        for index, item in enumerate(raw_figures, start=1)
    )
    unknown_claim_targets = {
        figure.claim_id
        for figure in figures
        if figure.claim_id and figure.claim_id not in claim_ids
    }
    if unknown_claim_targets:
        raise ProjectConfigError(
            f"Figures reference unknown claims: {', '.join(sorted(unknown_claim_targets))}"
        )

    raw_analyses = raw.get("analyses") or []
    if not isinstance(raw_analyses, list):
        raise ProjectConfigError("analyses must be a list")
    analyses = tuple(
        _parse_analysis(dict(item), index)
        for index, item in enumerate(raw_analyses, start=1)
    )
    analysis_ids = [analysis.analysis_id for analysis in analyses]
    if len(analysis_ids) != len(set(analysis_ids)):
        raise ProjectConfigError("Analysis IDs must be unique")
    if not claims and not analyses:
        raise ProjectConfigError("A project requires at least one claim or analysis")

    project = ProjectSpec(
        project_id=project_id,
        title=title,
        language=language,
        parameters=parameters,
        datasets=datasets,
        claims=claims,
        figures=figures,
        analyses=analyses,
        execution=ExecutionSpec.from_mapping(raw.get("execution")),
        source_path=source.resolve(),
        raw=raw,
    )
    _validate_analysis_references(project)
    return project
