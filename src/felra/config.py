from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

import yaml

from felra.numeric_backends import NUMERIC_ONTOLOGIES
from felra.precision_ladder import GROWTH_STRATEGIES
from felra.numeric_policy import NumericPolicy

from felra.formal import BACKENDS as FORMAL_BACKENDS
from felra.formal import FORMAL_STATUSES


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
        # Stage B: externally produced exact data. `exact` keeps the literal
        # text and an exact Fraction; `interval` keeps a pair of them. Neither
        # rounds on load, which is the whole point — a column typed `float`
        # discards the producer's precision before FELRA has seen it, and a
        # column typed `str` keeps the text while losing that it is a number.
        if kind not in {"float", "int", "str", "bool", "exact", "interval"}:
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
        if format_name not in {"csv", "json", "jsonl"}:
            raise ProjectConfigError("Dataset format must be csv, json, or jsonl")
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
    cache: bool = False
    cache_dir: str = ".felra-cache"
    refresh_cache: bool = False

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "ExecutionSpec":
        data = data or {}
        max_evaluations = int(data.get("max_evaluations", 200_000))
        random_samples = int(data.get("random_samples", 20_000))
        if max_evaluations < 1 or random_samples < 1:
            raise ProjectConfigError("Execution budgets must be positive")
        cache_dir = str(data.get("cache_dir", ".felra-cache"))
        if not cache_dir.strip():
            raise ProjectConfigError("execution.cache_dir must not be empty")
        return cls(
            max_evaluations=max_evaluations,
            random_samples=random_samples,
            seed=int(data.get("seed", 42)),
            cache=bool(data.get("cache", False)),
            cache_dir=cache_dir,
            refresh_cache=bool(data.get("refresh_cache", False)),
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


@dataclass(frozen=True)
class PowerAnalysisSpec(BaseAnalysisSpec):
    test: str = "one_sample_t"
    effect_size: float = 0.5
    alpha: float = 0.05
    target_power: float | None = 0.8
    sample_size: int | None = None
    alternative: str = "two-sided"
    allocation_ratio: float = 1.0
    max_sample_size: int = 10000


@dataclass(frozen=True)
class RobustnessAnalysisSpec(BaseAnalysisSpec):
    dataset: str = ""
    statistic: str = "mean"
    columns: tuple[str, ...] = ()
    group_by: str | None = None
    groups: tuple[str, ...] = ()
    method: str = "bootstrap"
    repetitions: int = 2000
    fraction: float = 0.8
    confidence: float = 0.95
    seed: int | None = None
    bins: int = 40


@dataclass(frozen=True)
class MultipleComparisonAnalysisSpec(BaseAnalysisSpec):
    dataset: str = ""
    column: str = ""
    group_by: str = ""
    groups: tuple[str, ...] = ()
    comparisons: tuple[tuple[str, str], ...] = ()
    test: str = "independent_t"
    correction: str = "holm"
    alpha: float = 0.05
    alternative: str = "two-sided"
    equal_var: bool = False


@dataclass(frozen=True)
class ModelCandidateSpec:
    name: str
    model: str = "linear"
    degree: int = 1
    standardize: bool = True


@dataclass(frozen=True)
class CrossValidationAnalysisSpec(BaseAnalysisSpec):
    dataset: str = ""
    target: str = ""
    features: tuple[str, ...] = ()
    model: str = "linear"
    degree: int = 1
    folds: int = 5
    shuffle: bool = True
    seed: int | None = None
    standardize: bool = True


@dataclass(frozen=True)
class ModelComparisonAnalysisSpec(BaseAnalysisSpec):
    dataset: str = ""
    target: str = ""
    features: tuple[str, ...] = ()
    models: tuple[ModelCandidateSpec, ...] = ()
    folds: int = 5
    shuffle: bool = True
    seed: int | None = None
    primary_metric: str = "rmse"


@dataclass(frozen=True)
class SymbolicAnalysisSpec(BaseAnalysisSpec):
    check: str = "equivalence"
    variables: tuple[str, ...] = ()
    assumptions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    lhs: str = ""
    rhs: str = ""
    expression: str = ""
    with_respect_to: str = ""
    expected_derivative: str = ""


@dataclass(frozen=True)
class NumericalSoundnessAnalysisSpec(BaseAnalysisSpec):
    expression: str = ""
    parameters: tuple[str, ...] = ()
    precision_digits: int = 30
    precision_sample_limit: int = 200
    condition_threshold: float = 1e6
    relative_error_threshold: float = 1e-6


@dataclass(frozen=True)
class CrossMethodSpec:
    name: str
    expression: str
    backend: str = "numeric"


@dataclass(frozen=True)
class CrossMethodAnalysisSpec(BaseAnalysisSpec):
    parameters: tuple[str, ...] = ()
    methods: tuple[CrossMethodSpec, ...] = ()
    precision_digits: int = 30
    tolerance: float = 1e-9


@dataclass(frozen=True)
class ObligationExportAnalysisSpec(BaseAnalysisSpec):
    """Stage-F proof-obligation export. `claim_id` is required: this analysis
    renders a CLAIM, so without one there is nothing to export."""

    backend: str | None = None
    path: str | None = None
    expect: str = "verified"
    timeout_seconds: int = 900


@dataclass(frozen=True)
class DecimalResidualAnalysisSpec(BaseAnalysisSpec):
    """§12's verification pack. `value` is a quoted string, read exactly."""

    value: str = ""
    bases: tuple[int, ...] = (2, 3, 8, 10, 16)
    levels: int = 8
    backends: tuple[str, ...] = ("float64", "decimal", "binary_mp")
    precisions: tuple[int, ...] = (16, 40)


@dataclass(frozen=True)
class NumericCertificateAnalysisSpec(BaseAnalysisSpec):
    """Stage-E strict envelope. `box` bounds are quoted strings, read exactly."""

    expression: str = ""
    box: dict[str, dict[str, str]] = field(default_factory=dict)
    establish: str | None = None


@dataclass(frozen=True)
class PrecisionLadderAnalysisSpec(BaseAnalysisSpec):
    """Stage-D precision ladder. Tolerances are STRINGS so that a declared 1e-80
    is read exactly rather than through a float that cannot hold it."""

    expression: str = ""
    points: tuple[dict[str, str], ...] = ()
    initial_precision_bits: int = 64
    strategy: str = "doubling"
    step_bits: int = 64
    max_precision_bits: int = 4096
    consecutive_levels: int = 3
    absolute_tolerance: str = "1e-80"
    relative_tolerance: str = "1e-70"


@dataclass(frozen=True)
class CrossBackendAnalysisSpec(BaseAnalysisSpec):
    """Stage-C cross-ontology comparison.

    `points` are lists of EXACT STRINGS on purpose: writing `0.1` as a YAML float
    would round the value before any backend saw it, and the analysis would then
    compare three ontologies' opinions of an already-rounded number.
    """

    expression: str = ""
    backends: tuple[str, ...] = ("float64", "decimal", "rational")
    points: tuple[dict[str, str], ...] = ()
    tolerance: float = 1e-12
    decimal_prec: int = 50
    report_points: int = 20


@dataclass(frozen=True)
class FormalCheckAnalysisSpec(BaseAnalysisSpec):
    """Stage-4 external formal check.

    A project declares WHICH adapter and WHAT obligation, never a command to run.
    `expect` is the formal status the author asserts in advance, so a checker
    returning something else is a reportable disagreement rather than a silently
    accepted result.
    """

    backend: str = "lean"
    obligation: str = ""
    project_dir: str | None = None
    jar: str | None = None
    path: str | None = None
    config_file: str | None = None
    expect: str = "verified"
    timeout_seconds: int = 900
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    derives_from: tuple[str, ...] = ()
    axioms_within: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PreregistrationSpec:
    enabled: bool = False
    path: str = ".felra-preregistration/preregistration.json"
    mode: str = "warn"

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "PreregistrationSpec":
        data = data or {}
        path = str(data.get("path", ".felra-preregistration/preregistration.json"))
        if not path.strip():
            raise ProjectConfigError("preregistration.path must not be empty")
        mode = str(data.get("mode", "warn"))
        if mode not in {"warn", "strict"}:
            raise ProjectConfigError("preregistration.mode must be warn or strict")
        return cls(enabled=bool(data.get("enabled", False)), path=path, mode=mode)


@dataclass(frozen=True)
class RegistrySpec:
    enabled: bool = False
    path: str = ".felra-registry/registry.jsonl"
    tags: tuple[str, ...] = ()
    notes: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "RegistrySpec":
        data = data or {}
        path = str(data.get("path", ".felra-registry/registry.jsonl"))
        if not path.strip():
            raise ProjectConfigError("registry.path must not be empty")
        tags = tuple(str(item) for item in data.get("tags", ()))
        return cls(
            enabled=bool(data.get("enabled", False)),
            path=path,
            tags=tags,
            notes=str(data["notes"]) if data.get("notes") is not None else None,
        )


AnalysisSpec: TypeAlias = (
    SensitivityAnalysisSpec
    | ResidualAnalysisSpec
    | SweepAnalysisSpec
    | ParetoAnalysisSpec
    | DescriptiveAnalysisSpec
    | HypothesisTestAnalysisSpec
    | BootstrapCIAnalysisSpec
    | PowerAnalysisSpec
    | RobustnessAnalysisSpec
    | MultipleComparisonAnalysisSpec
    | CrossValidationAnalysisSpec
    | ModelComparisonAnalysisSpec
    | SymbolicAnalysisSpec
    | NumericalSoundnessAnalysisSpec
    | CrossMethodAnalysisSpec
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


    if kind == "power":
        _require_fields(data, {"test", "effect_size"}, context=f"Analysis {analysis_id!r}")
        test = str(data["test"])
        if test not in {"one_sample_t", "paired_t", "independent_t", "correlation"}:
            raise ProjectConfigError(f"Unsupported power-analysis test {test!r}")
        effect_size = float(data["effect_size"])
        if effect_size == 0:
            raise ProjectConfigError("Power-analysis effect_size must be non-zero")
        alternative = str(data.get("alternative", "two-sided"))
        if alternative not in {"two-sided", "less", "greater"}:
            raise ProjectConfigError("alternative must be two-sided, less, or greater")
        target_power_raw = data.get("target_power")
        sample_size_raw = data.get("sample_size")
        if target_power_raw is None and sample_size_raw is None:
            target_power_raw = 0.8
        target_power = (
            None if target_power_raw is None else _probability(target_power_raw, field_name="target_power")
        )
        sample_size = None if sample_size_raw is None else int(sample_size_raw)
        if sample_size is not None and sample_size < 2:
            raise ProjectConfigError("Power-analysis sample_size must be at least 2")
        allocation_ratio = float(data.get("allocation_ratio", 1.0))
        if allocation_ratio <= 0:
            raise ProjectConfigError("allocation_ratio must be positive")
        max_sample_size = int(data.get("max_sample_size", 10000))
        if max_sample_size < 4:
            raise ProjectConfigError("max_sample_size must be at least 4")
        return PowerAnalysisSpec(
            **base,
            test=test,
            effect_size=effect_size,
            alpha=_probability(data.get("alpha", 0.05), field_name="alpha"),
            target_power=target_power,
            sample_size=sample_size,
            alternative=alternative,
            allocation_ratio=allocation_ratio,
            max_sample_size=max_sample_size,
        )

    if kind == "robustness":
        _require_fields(data, {"dataset", "statistic", "columns"}, context=f"Analysis {analysis_id!r}")
        statistic = str(data["statistic"])
        if statistic not in {"mean", "median", "std", "correlation", "mean_difference"}:
            raise ProjectConfigError(f"Unsupported robustness statistic {statistic!r}")
        columns = tuple(str(item) for item in data["columns"])
        required_columns = 2 if statistic == "correlation" else 1
        if len(columns) != required_columns:
            raise ProjectConfigError(
                f"Robustness statistic {statistic!r} requires {required_columns} column(s)"
            )
        group_by = str(data["group_by"]) if data.get("group_by") else None
        groups = tuple(str(item) for item in data.get("groups", ()))
        if statistic == "mean_difference" and (group_by is None or len(groups) != 2):
            raise ProjectConfigError("mean_difference requires group_by and exactly two groups")
        method = str(data.get("method", "bootstrap"))
        if method not in {"bootstrap", "subsample"}:
            raise ProjectConfigError("Robustness method must be bootstrap or subsample")
        repetitions = int(data.get("repetitions", 2000))
        if repetitions < 100:
            raise ProjectConfigError("Robustness repetitions must be at least 100")
        fraction = float(data.get("fraction", 0.8))
        if not 0.0 < fraction <= 1.0:
            raise ProjectConfigError("Robustness fraction must be in (0, 1]")
        bins = int(data.get("bins", 40))
        if bins < 1:
            raise ProjectConfigError("Robustness bins must be positive")
        return RobustnessAnalysisSpec(
            **base,
            dataset=str(data["dataset"]),
            statistic=statistic,
            columns=columns,
            group_by=group_by,
            groups=groups,
            method=method,
            repetitions=repetitions,
            fraction=fraction,
            confidence=_probability(data.get("confidence", 0.95), field_name="confidence"),
            seed=int(data["seed"]) if data.get("seed") is not None else None,
            bins=bins,
        )


    if kind == "multiple_comparisons":
        _require_fields(
            data, {"dataset", "column", "group_by"}, context=f"Analysis {analysis_id!r}"
        )
        test = str(data.get("test", "independent_t"))
        if test not in {"independent_t", "mann_whitney"}:
            raise ProjectConfigError("multiple_comparisons test must be independent_t or mann_whitney")
        correction = str(data.get("correction", "holm"))
        if correction not in {"none", "bonferroni", "holm", "fdr_bh"}:
            raise ProjectConfigError("correction must be none, bonferroni, holm, or fdr_bh")
        alternative = str(data.get("alternative", "two-sided"))
        if alternative not in {"two-sided", "less", "greater"}:
            raise ProjectConfigError("alternative must be two-sided, less, or greater")
        raw_comparisons = data.get("comparisons", ())
        comparisons: list[tuple[str, str]] = []
        for item in raw_comparisons:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ProjectConfigError("Each comparison must contain exactly two group names")
            comparisons.append((str(item[0]), str(item[1])))
        return MultipleComparisonAnalysisSpec(
            **base,
            dataset=str(data["dataset"]),
            column=str(data["column"]),
            group_by=str(data["group_by"]),
            groups=tuple(str(item) for item in data.get("groups", ())),
            comparisons=tuple(comparisons),
            test=test,
            correction=correction,
            alpha=_probability(data.get("alpha", 0.05), field_name="alpha"),
            alternative=alternative,
            equal_var=bool(data.get("equal_var", False)),
        )

    if kind == "cross_validation":
        _require_fields(
            data, {"dataset", "target", "features"}, context=f"Analysis {analysis_id!r}"
        )
        features = tuple(str(item) for item in data["features"])
        if not features:
            raise ProjectConfigError("cross_validation requires at least one feature")
        model = str(data.get("model", "linear"))
        if model not in {"linear", "polynomial"}:
            raise ProjectConfigError("cross_validation model must be linear or polynomial")
        degree = int(data.get("degree", 1))
        if degree < 1:
            raise ProjectConfigError("cross_validation degree must be at least 1")
        folds = int(data.get("folds", 5))
        if folds < 2:
            raise ProjectConfigError("cross_validation folds must be at least 2")
        return CrossValidationAnalysisSpec(
            **base,
            dataset=str(data["dataset"]),
            target=str(data["target"]),
            features=features,
            model=model,
            degree=degree,
            folds=folds,
            shuffle=bool(data.get("shuffle", True)),
            seed=int(data["seed"]) if data.get("seed") is not None else None,
            standardize=bool(data.get("standardize", True)),
        )

    if kind == "model_comparison":
        _require_fields(
            data, {"dataset", "target", "features", "models"},
            context=f"Analysis {analysis_id!r}",
        )
        features = tuple(str(item) for item in data["features"])
        if not features:
            raise ProjectConfigError("model_comparison requires at least one feature")
        raw_models = data["models"]
        if not isinstance(raw_models, list) or len(raw_models) < 2:
            raise ProjectConfigError("model_comparison requires at least two model candidates")
        models: list[ModelCandidateSpec] = []
        names: list[str] = []
        for index_model, item in enumerate(raw_models, start=1):
            if not isinstance(item, dict):
                raise ProjectConfigError("model candidates must be mappings")
            model = str(item.get("type", "linear"))
            if model not in {"linear", "polynomial"}:
                raise ProjectConfigError("model candidate type must be linear or polynomial")
            degree = int(item.get("degree", 1))
            if degree < 1:
                raise ProjectConfigError("model candidate degree must be at least 1")
            name = str(item.get("name", f"model_{index_model:02d}"))
            names.append(name)
            models.append(
                ModelCandidateSpec(
                    name=name,
                    model=model,
                    degree=degree,
                    standardize=bool(item.get("standardize", True)),
                )
            )
        if len(names) != len(set(names)):
            raise ProjectConfigError("model candidate names must be unique")
        folds = int(data.get("folds", 5))
        if folds < 2:
            raise ProjectConfigError("model_comparison folds must be at least 2")
        primary_metric = str(data.get("primary_metric", "rmse"))
        if primary_metric not in {"rmse", "mae", "r2"}:
            raise ProjectConfigError("primary_metric must be rmse, mae, or r2")
        return ModelComparisonAnalysisSpec(
            **base,
            dataset=str(data["dataset"]),
            target=str(data["target"]),
            features=features,
            models=tuple(models),
            folds=folds,
            shuffle=bool(data.get("shuffle", True)),
            seed=int(data["seed"]) if data.get("seed") is not None else None,
            primary_metric=primary_metric,
        )

    if kind == "symbolic":
        _require_fields(data, {"check", "variables"}, context=f"Analysis {analysis_id!r}")
        check = str(data["check"])
        if check not in {"equivalence", "derivative"}:
            raise ProjectConfigError("symbolic check must be equivalence or derivative")
        variables = tuple(str(item) for item in data["variables"])
        if not variables:
            raise ProjectConfigError("symbolic analysis requires at least one variable")
        if len(variables) != len(set(variables)):
            raise ProjectConfigError("symbolic variables must be unique")
        raw_assumptions = data.get("assumptions", {})
        if not isinstance(raw_assumptions, dict):
            raise ProjectConfigError("symbolic assumptions must be a mapping")
        assumptions: dict[str, tuple[str, ...]] = {}
        for name, keywords in raw_assumptions.items():
            if str(name) not in variables:
                raise ProjectConfigError(
                    f"symbolic assumptions reference undeclared variable {name!r}"
                )
            if isinstance(keywords, str):
                keywords = [keywords]
            assumptions[str(name)] = tuple(str(item) for item in keywords)
        if check == "equivalence":
            _require_fields(data, {"lhs", "rhs"}, context=f"Analysis {analysis_id!r}")
            return SymbolicAnalysisSpec(
                **base,
                check=check,
                variables=variables,
                assumptions=assumptions,
                lhs=str(data["lhs"]),
                rhs=str(data["rhs"]),
            )
        _require_fields(
            data,
            {"expression", "with_respect_to", "expected_derivative"},
            context=f"Analysis {analysis_id!r}",
        )
        with_respect_to = str(data["with_respect_to"])
        if with_respect_to not in variables:
            raise ProjectConfigError(
                f"symbolic with_respect_to {with_respect_to!r} must be a declared variable"
            )
        return SymbolicAnalysisSpec(
            **base,
            check=check,
            variables=variables,
            assumptions=assumptions,
            expression=str(data["expression"]),
            with_respect_to=with_respect_to,
            expected_derivative=str(data["expected_derivative"]),
        )

    if kind == "numerical_soundness":
        _require_fields(data, {"expression", "parameters"}, context=f"Analysis {analysis_id!r}")
        parameters = tuple(str(item) for item in data["parameters"])
        if not parameters:
            raise ProjectConfigError("numerical_soundness requires at least one parameter")
        if len(parameters) != len(set(parameters)):
            raise ProjectConfigError("numerical_soundness parameters must be unique")
        precision_digits = int(data.get("precision_digits", 30))
        if precision_digits < 15:
            raise ProjectConfigError(
                "numerical_soundness precision_digits must be at least 15 "
                "(float64 already carries ~15-17 significant digits)"
            )
        precision_sample_limit = int(data.get("precision_sample_limit", 200))
        if precision_sample_limit < 1:
            raise ProjectConfigError("numerical_soundness precision_sample_limit must be positive")
        condition_threshold = float(data.get("condition_threshold", 1e6))
        if condition_threshold <= 0:
            raise ProjectConfigError("numerical_soundness condition_threshold must be positive")
        relative_error_threshold = float(data.get("relative_error_threshold", 1e-6))
        if relative_error_threshold <= 0:
            raise ProjectConfigError(
                "numerical_soundness relative_error_threshold must be positive"
            )
        return NumericalSoundnessAnalysisSpec(
            **base,
            expression=str(data["expression"]),
            parameters=parameters,
            precision_digits=precision_digits,
            precision_sample_limit=precision_sample_limit,
            condition_threshold=condition_threshold,
            relative_error_threshold=relative_error_threshold,
        )

    if kind == "cross_method":
        _require_fields(data, {"parameters", "methods"}, context=f"Analysis {analysis_id!r}")
        cm_parameters = tuple(str(item) for item in data["parameters"])
        if not cm_parameters:
            raise ProjectConfigError("cross_method requires at least one parameter")
        if len(cm_parameters) != len(set(cm_parameters)):
            raise ProjectConfigError("cross_method parameters must be unique")
        raw_methods = data["methods"]
        if not isinstance(raw_methods, list) or len(raw_methods) < 2:
            raise ProjectConfigError("cross_method requires at least two methods")
        methods: list[CrossMethodSpec] = []
        method_names: list[str] = []
        for item in raw_methods:
            if not isinstance(item, dict):
                raise ProjectConfigError("cross_method methods must be mappings")
            _require_fields(item, {"name", "expression"}, context="cross_method method")
            backend = str(item.get("backend", "numeric"))
            if backend not in {"numeric", "symbolic", "high_precision"}:
                raise ProjectConfigError(
                    "cross_method method backend must be numeric, symbolic, or high_precision"
                )
            name = str(item["name"])
            method_names.append(name)
            methods.append(
                CrossMethodSpec(name=name, expression=str(item["expression"]), backend=backend)
            )
        if len(method_names) != len(set(method_names)):
            raise ProjectConfigError("cross_method method names must be unique")
        cm_precision_digits = int(data.get("precision_digits", 30))
        if cm_precision_digits < 15:
            raise ProjectConfigError("cross_method precision_digits must be at least 15")
        tolerance = float(data.get("tolerance", 1e-9))
        if tolerance <= 0:
            raise ProjectConfigError("cross_method tolerance must be positive")
        return CrossMethodAnalysisSpec(
            **base,
            parameters=cm_parameters,
            methods=tuple(methods),
            precision_digits=cm_precision_digits,
            tolerance=tolerance,
        )

    if kind == "obligation_export":
        if not base.get("claim_id"):
            raise ProjectConfigError(
                "obligation_export requires a claim_id; it renders a claim, so "
                "without one there is nothing to export")
        oe_backend = data.get("backend")
        if oe_backend is not None:
            oe_backend = str(oe_backend)
            if oe_backend not in FORMAL_BACKENDS:
                raise ProjectConfigError(
                    "obligation_export backend must be one of %s"
                    % ", ".join(FORMAL_BACKENDS))
            if oe_backend != "z3":
                raise ProjectConfigError(
                    "only the z3 backend can check an exported obligation; the "
                    "exporter emits SMT-LIB2, and handing it to a model checker or "
                    "a proof assistant would be handing them a file they cannot read")
        oe_expect = str(data.get("expect", "verified"))
        if oe_expect not in FORMAL_STATUSES:
            raise ProjectConfigError(
                "obligation_export expect must be one of %s"
                % ", ".join(FORMAL_STATUSES))
        return ObligationExportAnalysisSpec(
            **base,
            backend=oe_backend,
            path=(str(data["path"]) if data.get("path") else None),
            expect=oe_expect,
            timeout_seconds=int(data.get("timeout_seconds", 900)),
        )

    if kind == "decimal_residual":
        _require_fields(data, {"value"}, context=f"Analysis {analysis_id!r}")
        if isinstance(data["value"], float):
            raise ProjectConfigError(
                "decimal_residual value is a YAML float, already rounded before any "
                "residue is taken; quote it so it is read exactly")
        dr_bases = tuple(int(b) for b in data.get("bases", (2, 3, 8, 10, 16)))
        if any(b < 2 for b in dr_bases):
            raise ProjectConfigError("decimal_residual bases must all be at least 2")
        if len(dr_bases) < 5:
            raise ProjectConfigError(
                "acceptance 18.5 asks for at least five bases; %d given"
                % len(dr_bases))
        dr_backends = tuple(str(b) for b in
                            data.get("backends", ("float64", "decimal", "binary_mp")))
        for backend in dr_backends:
            if backend not in NUMERIC_ONTOLOGIES:
                raise ProjectConfigError(
                    "decimal_residual backend must be one of %s"
                    % ", ".join(NUMERIC_ONTOLOGIES))
        return DecimalResidualAnalysisSpec(
            **base,
            value=str(data["value"]),
            bases=dr_bases,
            levels=int(data.get("levels", 8)),
            backends=dr_backends,
            precisions=tuple(int(p) for p in data.get("precisions", (16, 40))),
        )

    if kind == "numeric_certificate":
        _require_fields(data, {"expression", "box"}, context=f"Analysis {analysis_id!r}")
        raw_box = data["box"]
        if not isinstance(raw_box, dict) or not raw_box:
            raise ProjectConfigError("numeric_certificate box must be a non-empty mapping")
        nc_box: dict[str, dict[str, str]] = {}
        for name, bounds in raw_box.items():
            if not isinstance(bounds, dict) or {"lo", "hi"} - set(bounds):
                raise ProjectConfigError(
                    "numeric_certificate box.%s needs `lo` and `hi`" % name)
            for key in ("lo", "hi"):
                if isinstance(bounds[key], float):
                    raise ProjectConfigError(
                        "numeric_certificate box.%s.%s is a YAML float, already "
                        "rounded before the enclosure is built; quote it so the "
                        "endpoint is exact" % (name, key))
            nc_box[str(name)] = {"lo": str(bounds["lo"]), "hi": str(bounds["hi"])}
        establish = data.get("establish")
        if establish is not None and str(establish) not in (">", ">=", "<", "<="):
            raise ProjectConfigError(
                "numeric_certificate establish must be one of >, >=, <, <=")
        return NumericCertificateAnalysisSpec(
            **base,
            expression=str(data["expression"]),
            box=nc_box,
            establish=None if establish is None else str(establish),
        )

    if kind == "precision_ladder":
        _require_fields(data, {"expression", "points"},
                        context=f"Analysis {analysis_id!r}")
        pl_strategy = str(data.get("strategy", "doubling"))
        if pl_strategy not in GROWTH_STRATEGIES:
            raise ProjectConfigError(
                "precision_ladder strategy must be one of %s"
                % ", ".join(GROWTH_STRATEGIES))
        pl_points = []
        for item in data["points"]:
            if not isinstance(item, dict):
                raise ProjectConfigError("precision_ladder points must be mappings")
            row = {}
            for name, value in item.items():
                if isinstance(value, float):
                    raise ProjectConfigError(
                        "precision_ladder point %s=%r is a YAML float, already "
                        "rounded before the ladder starts; quote it" % (name, value))
                row[str(name)] = str(value)
            pl_points.append(row)
        if not pl_points:
            raise ProjectConfigError("precision_ladder requires a non-empty points list")
        levels = int(data.get("consecutive_levels", 3))
        if levels < 2:
            raise ProjectConfigError(
                "precision_ladder consecutive_levels must be at least 2; one level "
                "compared with itself is not a stability test")
        initial = int(data.get("initial_precision_bits", 64))
        maximum = int(data.get("max_precision_bits", 4096))
        if initial < 1 or maximum < initial:
            raise ProjectConfigError(
                "precision_ladder needs 1 <= initial_precision_bits <= "
                "max_precision_bits")
        for key in ("absolute_tolerance", "relative_tolerance"):
            if key in data and isinstance(data[key], float):
                raise ProjectConfigError(
                    "precision_ladder %s must be a quoted string; a YAML float "
                    "cannot hold the magnitudes this field is for. Note that YAML "
                    "reads `1e-80` as a string but `1.0e-80` as a float, so the "
                    "same tolerance is safe written one way and lossy the other — "
                    "quote it and the distinction stops mattering." % key)
        return PrecisionLadderAnalysisSpec(
            **base,
            expression=str(data["expression"]),
            points=tuple(pl_points),
            initial_precision_bits=initial,
            strategy=pl_strategy,
            step_bits=int(data.get("step_bits", 64)),
            max_precision_bits=maximum,
            consecutive_levels=levels,
            absolute_tolerance=str(data.get("absolute_tolerance", "1e-80")),
            relative_tolerance=str(data.get("relative_tolerance", "1e-70")),
        )

    if kind == "cross_backend":
        _require_fields(data, {"expression", "points"},
                        context=f"Analysis {analysis_id!r}")
        cb_backends = tuple(str(x) for x in data.get(
            "backends", ("float64", "decimal", "rational")))
        if len(cb_backends) < 2:
            raise ProjectConfigError("cross_backend requires at least two backends")
        if len(cb_backends) != len(set(cb_backends)):
            raise ProjectConfigError("cross_backend backends must be unique")
        for backend in cb_backends:
            if backend not in NUMERIC_ONTOLOGIES:
                raise ProjectConfigError(
                    "cross_backend backend must be one of %s"
                    % ", ".join(NUMERIC_ONTOLOGIES)
                )
        raw_points = data["points"]
        if not isinstance(raw_points, list) or not raw_points:
            raise ProjectConfigError("cross_backend requires a non-empty points list")
        cb_points = []
        for item in raw_points:
            if not isinstance(item, dict):
                raise ProjectConfigError("cross_backend points must be mappings")
            row = {}
            for name, value in item.items():
                if isinstance(value, float):
                    raise ProjectConfigError(
                        "cross_backend point %s=%r is a YAML float, which has "
                        "already been rounded before any backend sees it; quote it "
                        "as a string so it can be parsed exactly" % (name, value)
                    )
                row[str(name)] = str(value)
            cb_points.append(row)
        cb_tolerance = float(data.get("tolerance", 1e-12))
        if cb_tolerance < 0:
            raise ProjectConfigError("cross_backend tolerance must not be negative")
        cb_prec = int(data.get("decimal_prec", 50))
        if cb_prec < 1:
            raise ProjectConfigError("cross_backend decimal_prec must be positive")
        return CrossBackendAnalysisSpec(
            **base,
            expression=str(data["expression"]),
            backends=cb_backends,
            points=tuple(cb_points),
            tolerance=cb_tolerance,
            decimal_prec=cb_prec,
            report_points=int(data.get("report_points", 20)),
        )

    if kind == "formal_check":
        _require_fields(data, {"backend", "obligation"}, context=f"Analysis {analysis_id!r}")
        fc_backend = str(data["backend"])
        if fc_backend not in FORMAL_BACKENDS:
            raise ProjectConfigError(
                "formal_check backend must be one of %s; the backend list is closed "
                "on purpose, see docs/FORMAL_BACKENDS.md" % ", ".join(FORMAL_BACKENDS)
            )
        obligation = str(data["obligation"]).strip()
        if not obligation:
            raise ProjectConfigError("formal_check obligation must not be empty")
        expect = str(data.get("expect", "verified"))
        if expect not in FORMAL_STATUSES:
            raise ProjectConfigError(
                "formal_check expect must be one of %s" % ", ".join(FORMAL_STATUSES)
            )
        timeout_seconds = int(data.get("timeout_seconds", 900))
        if timeout_seconds <= 0:
            raise ProjectConfigError("formal_check timeout_seconds must be positive")
        if data.get("axioms_within") is not None and fc_backend != "lean":
            raise ProjectConfigError(
                "formal_check axioms_within is only meaningful for the lean "
                "backend; declaring it elsewhere would be a claim nothing checks"
            )
        if fc_backend == "tlc" and not data.get("jar"):
            raise ProjectConfigError(
                "formal_check backend tlc requires a `jar` path; FELRA does not ship "
                "or download tla2tools.jar"
            )
        return FormalCheckAnalysisSpec(
            **base,
            backend=fc_backend,
            obligation=obligation,
            project_dir=(str(data["project_dir"]) if data.get("project_dir") else None),
            jar=(str(data["jar"]) if data.get("jar") else None),
            path=(str(data["path"]) if data.get("path") else None),
            config_file=(str(data["config_file"]) if data.get("config_file") else None),
            expect=expect,
            timeout_seconds=timeout_seconds,
            assumptions=tuple(str(x) for x in data.get("assumptions", ())),
            limitations=tuple(str(x) for x in data.get("limitations", ())),
            derives_from=tuple(str(x) for x in data.get("derives_from", ())),
            axioms_within=(tuple(str(x) for x in data["axioms_within"])
                           if data.get("axioms_within") is not None else None),
        )

    raise ProjectConfigError(
        f"Unsupported analysis type {kind!r}; expected sensitivity, residual, parameter_sweep, "
        "pareto, descriptive, hypothesis_test, bootstrap_ci, power, robustness, "
        "multiple_comparisons, cross_validation, model_comparison, symbolic, "
        "numerical_soundness, cross_method, cross_backend, precision_ladder, numeric_certificate, or formal_check"
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
    registry: RegistrySpec = field(default_factory=RegistrySpec)
    preregistration: PreregistrationSpec = field(default_factory=PreregistrationSpec)
    source_path: Path | None = None
    numeric_policy: NumericPolicy | None = None
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
            (
                DescriptiveAnalysisSpec,
                HypothesisTestAnalysisSpec,
                BootstrapCIAnalysisSpec,
                RobustnessAnalysisSpec,
                MultipleComparisonAnalysisSpec,
                CrossValidationAnalysisSpec,
                ModelComparisonAnalysisSpec,
            ),
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
            elif isinstance(analysis, BootstrapCIAnalysisSpec):
                referenced.add(analysis.column)
            elif isinstance(analysis, RobustnessAnalysisSpec):
                referenced.update(analysis.columns)
                if analysis.group_by:
                    referenced.add(analysis.group_by)
            elif isinstance(analysis, MultipleComparisonAnalysisSpec):
                referenced.add(analysis.column)
                referenced.add(analysis.group_by)
            else:
                referenced.update(analysis.features)
                referenced.add(analysis.target)
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
        elif isinstance(analysis, (NumericalSoundnessAnalysisSpec, CrossMethodAnalysisSpec)):
            referenced_parameters.update(analysis.parameters)
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
        registry=RegistrySpec.from_mapping(raw.get("registry")),
        preregistration=PreregistrationSpec.from_mapping(raw.get("preregistration")),
        source_path=source.resolve(),
        numeric_policy=NumericPolicy.from_mapping(raw.get("numeric_policy")),
        raw=raw,
    )
    _validate_analysis_references(project)
    return project
