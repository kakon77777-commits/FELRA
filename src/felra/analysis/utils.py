from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from felra.config import ParameterSpec
from felra.expressions import evaluate_expression
from felra.sampling import SampleSet, parameter_axis


def jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(jsonable(dict(payload)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_csv(path: Path, columns: Mapping[str, Iterable[Any]]) -> int:
    arrays = {name: np.asarray(values).reshape(-1) for name, values in columns.items()}
    lengths = {len(values) for values in arrays.values()}
    if not arrays:
        path.write_text("", encoding="utf-8")
        return 0
    if len(lengths) != 1:
        raise ValueError("All CSV columns must have the same length")
    row_count = lengths.pop()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(arrays)
        for index in range(row_count):
            writer.writerow([jsonable(values[index]) for values in arrays.values()])
    return row_count


def scalar_expression(expression: str, context: Mapping[str, Any]) -> float:
    value = np.asarray(evaluate_expression(expression, context), dtype=float)
    if value.size != 1:
        raise ValueError(f"Expression must produce one scalar, got shape {value.shape}")
    return float(value.reshape(-1)[0])


def broadcast_expression(
    expression: str,
    context: Mapping[str, Any],
    expected_count: int,
) -> np.ndarray:
    value = np.asarray(evaluate_expression(expression, context), dtype=float)
    if value.ndim == 0:
        return np.full(expected_count, float(value), dtype=float)
    value = value.reshape(-1)
    if value.size != expected_count:
        raise ValueError(
            f"Expression output size {value.size} does not match sample count {expected_count}"
        )
    return value


def midpoint(spec: ParameterSpec) -> float | int:
    axis = parameter_axis(spec)
    value = axis[len(axis) // 2].item()
    return int(value) if spec.kind == "int" else float(value)


def default_context(parameters: Mapping[str, ParameterSpec]) -> dict[str, float | int]:
    return {name: midpoint(spec) for name, spec in parameters.items()}


def clamp_to_domain(value: float | int, spec: ParameterSpec) -> float | int:
    axis = parameter_axis(spec)
    if spec.values:
        nearest = axis[np.argmin(np.abs(axis.astype(float) - float(value)))].item()
        return int(nearest) if spec.kind == "int" else float(nearest)
    assert spec.minimum is not None and spec.maximum is not None
    clipped = min(max(float(value), float(spec.minimum)), float(spec.maximum))
    if spec.kind == "int":
        return int(round(clipped))
    return float(clipped)


def sample_columns(samples: SampleSet) -> dict[str, np.ndarray]:
    return {name: np.asarray(values).reshape(-1) for name, values in samples.variables.items()}
