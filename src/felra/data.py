from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from felra.config import DatasetSpec
from felra.sampling import SampleSet


class DatasetLoadError(ValueError):
    """Raised when an external dataset cannot satisfy its declared schema."""


@dataclass
class DatasetQuality:
    dataset_id: str
    source_path: str
    source_sha256: str
    total_rows: int
    loaded_rows: int
    dropped_rows: int
    duplicate_rows: int
    missing_by_column: dict[str, int] = field(default_factory=dict)
    invalid_by_column: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Dataset:
    spec: DatasetSpec
    columns: dict[str, np.ndarray]
    quality: DatasetQuality

    @property
    def row_count(self) -> int:
        return self.quality.loaded_rows

    def sample_set(self) -> SampleSet:
        return SampleSet(
            variables=self.columns,
            strategy=f"dataset:{self.spec.dataset_id}",
            sample_count=self.row_count,
            exhaustive_declared_grid=True,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_missing(raw: str | None, tokens: set[str]) -> bool:
    if raw is None:
        return True
    return raw.strip().lower() in tokens


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "t"}:
        return True
    if normalized in {"0", "false", "no", "n", "f"}:
        return False
    raise ValueError(f"cannot parse Boolean value {value!r}")


def _convert(value: str, kind: str) -> Any:
    if kind == "float":
        return float(value)
    if kind == "int":
        number = float(value)
        if not number.is_integer():
            raise ValueError(f"expected integer, got {value!r}")
        return int(number)
    if kind == "bool":
        return _parse_bool(value)
    if kind == "str":
        return value
    raise ValueError(f"unsupported column type {kind!r}")


def _missing_value(kind: str) -> Any:
    if kind in {"float", "int"}:
        return np.nan
    if kind == "bool":
        return None
    return ""


def _column_array(values: list[Any], kind: str) -> np.ndarray:
    if kind == "float":
        return np.asarray(values, dtype=float)
    if kind == "int":
        if any(isinstance(value, float) and np.isnan(value) for value in values):
            return np.asarray(values, dtype=float)
        return np.asarray(values, dtype=int)
    if kind == "bool" and all(value is not None for value in values):
        return np.asarray(values, dtype=bool)
    return np.asarray(values, dtype=object)


def _open_text(path: Path, *, encoding: str):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding=encoding, newline="")
    return path.open("r", encoding=encoding, newline="")


def _read_raw_rows(spec: DatasetSpec) -> list[dict[str, Any]]:
    path = spec.path
    if spec.format == "csv":
        with _open_text(path, encoding=spec.encoding) as handle:
            reader = csv.DictReader(handle, delimiter=spec.delimiter)
            if reader.fieldnames is None:
                raise DatasetLoadError(f"Dataset {spec.dataset_id!r} has no header")
            absent = sorted(set(spec.columns).difference(reader.fieldnames))
            if absent:
                raise DatasetLoadError(
                    f"Dataset {spec.dataset_id!r} is missing declared columns: {', '.join(absent)}"
                )
            return [dict(row) for row in reader]
    if spec.format == "json":
        with _open_text(path, encoding=spec.encoding) as handle:
            payload = json.load(handle)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise DatasetLoadError(
                f"Dataset {spec.dataset_id!r} JSON root must be a list of objects"
            )
        return [dict(item) for item in payload]
    if spec.format == "jsonl":
        rows: list[dict[str, Any]] = []
        with _open_text(path, encoding=spec.encoding) as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DatasetLoadError(
                        f"Dataset {spec.dataset_id!r} JSONL line {line_number} is invalid: {exc}"
                    ) from exc
                if not isinstance(item, dict):
                    raise DatasetLoadError(
                        f"Dataset {spec.dataset_id!r} JSONL line {line_number} must be an object"
                    )
                rows.append(dict(item))
        return rows
    raise DatasetLoadError(f"Unsupported dataset format {spec.format!r}")


def load_dataset(spec: DatasetSpec) -> Dataset:
    path = spec.path
    if not path.exists():
        raise FileNotFoundError(path)

    missing_tokens = {token.strip().lower() for token in spec.missing_values}
    missing_by_column = {name: 0 for name in spec.columns}
    invalid_by_column = {name: 0 for name in spec.columns}
    accepted_rows: list[dict[str, Any]] = []
    dropped_rows = 0
    raw_rows = _read_raw_rows(spec)
    total_rows = len(raw_rows)

    for row_number, raw_row in enumerate(raw_rows, start=1):
        converted: dict[str, Any] = {}
        row_has_required_problem = False
        for name, column_spec in spec.columns.items():
            raw_value = raw_row.get(name)
            raw_text = None if raw_value is None else str(raw_value)
            if _is_missing(raw_text, missing_tokens):
                missing_by_column[name] += 1
                if column_spec.required:
                    row_has_required_problem = True
                converted[name] = _missing_value(column_spec.kind)
                continue
            assert raw_text is not None
            try:
                converted[name] = _convert(raw_text.strip(), column_spec.kind)
            except (TypeError, ValueError):
                invalid_by_column[name] += 1
                if column_spec.required:
                    row_has_required_problem = True
                converted[name] = _missing_value(column_spec.kind)

        if row_has_required_problem:
            if spec.on_error == "error":
                raise DatasetLoadError(
                    f"Dataset {spec.dataset_id!r} row {row_number} contains missing or invalid "
                    "required values"
                )
            if spec.on_error == "drop":
                dropped_rows += 1
                continue
        accepted_rows.append(converted)

    if not accepted_rows:
        raise DatasetLoadError(f"Dataset {spec.dataset_id!r} contains no usable rows")

    columns = {
        name: _column_array([row[name] for row in accepted_rows], column_spec.kind)
        for name, column_spec in spec.columns.items()
    }
    duplicate_rows = len(accepted_rows) - len(
        {
            tuple(
                None if isinstance(row[name], float) and np.isnan(row[name]) else row[name]
                for name in spec.columns
            )
            for row in accepted_rows
        }
    )
    warnings: list[str] = []
    if dropped_rows:
        warnings.append(f"Dropped {dropped_rows} rows under on_error={spec.on_error!r}.")
    if duplicate_rows:
        warnings.append(f"Detected {duplicate_rows} duplicate rows in declared columns.")
    quality = DatasetQuality(
        dataset_id=spec.dataset_id,
        source_path=str(path),
        source_sha256=_sha256(path),
        total_rows=total_rows,
        loaded_rows=len(accepted_rows),
        dropped_rows=dropped_rows,
        duplicate_rows=duplicate_rows,
        missing_by_column=missing_by_column,
        invalid_by_column=invalid_by_column,
        warnings=warnings,
    )
    return Dataset(spec=spec, columns=columns, quality=quality)


def write_dataset_evidence(dataset: Dataset, output_root: Path) -> list[str]:
    output_dir = output_root / "datasets" / dataset.spec.dataset_id
    output_dir.mkdir(parents=True, exist_ok=True)
    quality_path = output_dir / "quality.json"
    normalized_path = output_dir / "normalized.csv"
    report_path = output_dir / "dataset_report.md"

    quality_path.write_text(
        json.dumps(dataset.quality.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with normalized_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        names = list(dataset.columns)
        writer.writerow(names)
        for index in range(dataset.row_count):
            values: list[Any] = []
            for name in names:
                value = dataset.columns[name][index]
                if isinstance(value, np.generic):
                    value = value.item()
                if isinstance(value, float) and np.isnan(value):
                    value = ""
                values.append(value)
            writer.writerow(values)

    lines = [
        f"# FELRA Dataset Report — {dataset.spec.dataset_id}",
        "",
        f"- Source: `{dataset.spec.path}`",
        f"- Format: `{dataset.spec.format}`",
        f"- SHA-256: `{dataset.quality.source_sha256}`",
        f"- Rows read: `{dataset.quality.total_rows}`",
        f"- Rows loaded: `{dataset.quality.loaded_rows}`",
        f"- Rows dropped: `{dataset.quality.dropped_rows}`",
        f"- Duplicate rows: `{dataset.quality.duplicate_rows}`",
        f"- Error policy: `{dataset.spec.on_error}`",
        "",
        "## Column quality",
        "",
        "| Column | Type | Required | Missing | Invalid |",
        "|---|---|---:|---:|---:|",
    ]
    for name, spec in dataset.spec.columns.items():
        lines.append(
            f"| `{name}` | `{spec.kind}` | `{spec.required}` | "
            f"`{dataset.quality.missing_by_column[name]}` | "
            f"`{dataset.quality.invalid_by_column[name]}` |"
        )
    if dataset.quality.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in dataset.quality.warnings)
    lines.extend(
        [
            "",
            "> The normalized CSV is a deterministic projection of the declared columns, not a "
            "replacement for the source dataset.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return [
        str(quality_path.relative_to(output_root)),
        str(normalized_path.relative_to(output_root)),
        str(report_path.relative_to(output_root)),
    ]
