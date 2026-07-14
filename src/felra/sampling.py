from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import prod

import numpy as np

from felra.config import ParameterSpec


@dataclass(frozen=True)
class SampleSet:
    variables: dict[str, np.ndarray]
    strategy: str
    sample_count: int
    exhaustive_declared_grid: bool = False


def parameter_axis(spec: ParameterSpec) -> np.ndarray:
    if spec.values:
        dtype = int if spec.kind == "int" else float
        return np.asarray(spec.values, dtype=dtype)
    assert spec.minimum is not None and spec.maximum is not None
    if spec.kind == "int":
        axis = np.rint(np.linspace(spec.minimum, spec.maximum, spec.samples)).astype(int)
        return np.unique(axis)
    return np.linspace(float(spec.minimum), float(spec.maximum), spec.samples, dtype=float)


def build_declared_samples(
    parameters: dict[str, ParameterSpec],
    *,
    max_evaluations: int,
    seed: int,
) -> SampleSet:
    axes = {name: parameter_axis(spec) for name, spec in parameters.items()}
    grid_size = prod(len(axis) for axis in axes.values())
    if grid_size <= max_evaluations:
        names = list(axes)
        meshes = np.meshgrid(*(axes[name] for name in names), indexing="ij")
        variables = {name: mesh.reshape(-1) for name, mesh in zip(names, meshes, strict=True)}
        return SampleSet(
            variables=variables,
            strategy="declared_cartesian_grid",
            sample_count=grid_size,
            exhaustive_declared_grid=True,
        )

    rng = np.random.default_rng(seed)
    sample_count = max_evaluations
    variables: dict[str, np.ndarray] = {}
    for name, spec in parameters.items():
        axis = axes[name]
        if spec.values:
            variables[name] = rng.choice(axis, size=sample_count, replace=True)
        elif spec.kind == "int":
            assert spec.minimum is not None and spec.maximum is not None
            variables[name] = rng.integers(
                int(spec.minimum), int(spec.maximum) + 1, size=sample_count
            )
        else:
            assert spec.minimum is not None and spec.maximum is not None
            variables[name] = rng.uniform(
                float(spec.minimum), float(spec.maximum), size=sample_count
            )
    return SampleSet(
        variables=variables,
        strategy="budgeted_uniform_sampling",
        sample_count=sample_count,
        exhaustive_declared_grid=False,
    )


def build_boundary_samples(parameters: dict[str, ParameterSpec]) -> SampleSet:
    names = list(parameters)
    boundary_values: list[tuple[float | int, ...]] = []
    for spec in parameters.values():
        axis = parameter_axis(spec)
        values = (axis[0],) if len(axis) == 1 else (axis[0], axis[-1])
        boundary_values.append(values)
    points = list(product(*boundary_values))
    variables = {
        name: np.asarray([point[index] for point in points])
        for index, name in enumerate(names)
    }
    return SampleSet(
        variables=variables,
        strategy="domain_corners",
        sample_count=len(points),
        exhaustive_declared_grid=True,
    )


def build_random_samples(
    parameters: dict[str, ParameterSpec], *, sample_count: int, seed: int
) -> SampleSet:
    rng = np.random.default_rng(seed)
    variables: dict[str, np.ndarray] = {}
    for name, spec in parameters.items():
        if spec.values:
            variables[name] = rng.choice(parameter_axis(spec), size=sample_count, replace=True)
        elif spec.kind == "int":
            assert spec.minimum is not None and spec.maximum is not None
            variables[name] = rng.integers(
                int(spec.minimum), int(spec.maximum) + 1, size=sample_count
            )
        else:
            assert spec.minimum is not None and spec.maximum is not None
            variables[name] = rng.uniform(
                float(spec.minimum), float(spec.maximum), size=sample_count
            )
    return SampleSet(
        variables=variables,
        strategy="counterexample_uniform_random",
        sample_count=sample_count,
        exhaustive_declared_grid=False,
    )
