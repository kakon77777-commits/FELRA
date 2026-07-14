from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


class FigureFactory:
    """Generate traceable academic figures with conservative defaults."""

    _CJK_FONT_CANDIDATES = (
        "Noto Sans CJK TC",
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Noto Serif CJK TC",
        "Noto Serif CJK JP",
        "Microsoft JhengHei",
        "PingFang TC",
        "WenQuanYi Zen Hei",
        "Arial Unicode MS",
    )

    @classmethod
    def _configure_fonts(cls) -> None:
        available = {font.name for font in font_manager.fontManager.ttflist}
        preferred = [name for name in cls._CJK_FONT_CANDIDATES if name in available]
        if preferred:
            plt.rcParams["font.sans-serif"] = preferred + list(plt.rcParams["font.sans-serif"])
        plt.rcParams["axes.unicode_minus"] = False

    def __init__(self, output_dir: str | Path) -> None:
        self._configure_fonts()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, filename: str) -> Path:
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Figure filename must stay inside the configured output directory")
        path = self.output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _save(self, figure: plt.Figure, filename: str) -> Path:
        path = self._safe_path(filename)
        figure.tight_layout()
        figure.savefig(path, dpi=180)
        plt.close(figure)
        return path

    def line_plot(
        self,
        x: Iterable[float],
        y: Iterable[float],
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        x_values = np.asarray(x, dtype=float)
        y_values = np.asarray(y, dtype=float)
        if x_values.shape != y_values.shape:
            raise ValueError("x and y must have the same shape")
        figure, axis = plt.subplots()
        axis.plot(x_values, y_values)
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)
        return self._save(figure, filename)

    def scatter_plot(
        self,
        x: Iterable[float],
        y: Iterable[float],
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        x_values = np.asarray(x, dtype=float)
        y_values = np.asarray(y, dtype=float)
        if x_values.shape != y_values.shape:
            raise ValueError("x and y must have the same shape")
        figure, axis = plt.subplots()
        axis.scatter(x_values, y_values, s=10)
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)
        return self._save(figure, filename)

    def histogram(
        self,
        values: Iterable[float],
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        bins: int,
        filename: str,
    ) -> Path:
        array = np.asarray(values, dtype=float)
        figure, axis = plt.subplots()
        axis.hist(array[np.isfinite(array)], bins=bins)
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        return self._save(figure, filename)

    def bar_plot(
        self,
        labels: Sequence[str],
        values: Iterable[float],
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        numeric = np.asarray(values, dtype=float)
        if len(labels) != len(numeric):
            raise ValueError("labels and values must have the same length")
        figure, axis = plt.subplots()
        positions = np.arange(len(labels))
        axis.bar(positions, numeric)
        axis.set_xticks(positions, labels, rotation=30, ha="right")
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(True, axis="y", alpha=0.25)
        return self._save(figure, filename)

    def heatmap(
        self,
        x: Iterable[float],
        y: Iterable[float],
        z: np.ndarray,
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        x_values = np.asarray(x, dtype=float)
        y_values = np.asarray(y, dtype=float)
        z_values = np.asarray(z, dtype=float)
        expected = (len(y_values), len(x_values))
        if z_values.shape != expected:
            raise ValueError(f"z shape must be {expected}, got {z_values.shape}")
        figure, axis = plt.subplots()
        image = axis.imshow(
            z_values,
            origin="lower",
            aspect="auto",
            extent=[x_values.min(), x_values.max(), y_values.min(), y_values.max()],
        )
        figure.colorbar(image, ax=axis)
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        return self._save(figure, filename)

    def contour_plot(
        self,
        x: Iterable[float],
        y: Iterable[float],
        z: np.ndarray,
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        x_values = np.asarray(x, dtype=float)
        y_values = np.asarray(y, dtype=float)
        z_values = np.asarray(z, dtype=float)
        expected = (len(y_values), len(x_values))
        if z_values.shape != expected:
            raise ValueError(f"z shape must be {expected}, got {z_values.shape}")
        x_mesh, y_mesh = np.meshgrid(x_values, y_values, indexing="xy")
        figure, axis = plt.subplots()
        contours = axis.contourf(x_mesh, y_mesh, z_values)
        figure.colorbar(contours, ax=axis)
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        return self._save(figure, filename)

    def phase_map(
        self,
        x: Iterable[float],
        y: Iterable[float],
        phase: np.ndarray,
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        return self.heatmap(
            x,
            y,
            np.asarray(phase, dtype=float),
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            filename=filename,
        )

    def residual_plot(
        self,
        x: Iterable[float],
        residuals: Iterable[float],
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        x_values = np.asarray(x, dtype=float)
        residual_values = np.asarray(residuals, dtype=float)
        if x_values.shape != residual_values.shape:
            raise ValueError("x and residuals must have the same shape")
        figure, axis = plt.subplots()
        axis.scatter(x_values, residual_values, s=10)
        axis.axhline(0.0, linewidth=1)
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)
        return self._save(figure, filename)

    def pareto_plot(
        self,
        x: Iterable[float],
        y: Iterable[float],
        frontier_mask: Iterable[bool],
        *,
        title: str,
        xlabel: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        x_values = np.asarray(x, dtype=float)
        y_values = np.asarray(y, dtype=float)
        mask = np.asarray(frontier_mask, dtype=bool)
        if x_values.shape != y_values.shape or x_values.shape != mask.shape:
            raise ValueError("Pareto x, y, and frontier mask must have the same shape")
        figure, axis = plt.subplots()
        axis.scatter(x_values[~mask], y_values[~mask], s=10, alpha=0.35, label="Candidates")
        frontier_x = x_values[mask]
        frontier_y = y_values[mask]
        order = np.argsort(frontier_x, kind="stable")
        axis.plot(frontier_x[order], frontier_y[order], marker="o", label="Pareto frontier")
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)
        axis.legend()
        return self._save(figure, filename)

    def grouped_boxplot(
        self,
        groups: Sequence[Iterable[float]],
        labels: Sequence[str],
        *,
        title: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        if len(groups) != len(labels):
            raise ValueError("groups and labels must have the same length")
        arrays = [np.asarray(group, dtype=float) for group in groups]
        arrays = [array[np.isfinite(array)] for array in arrays]
        figure, axis = plt.subplots()
        version_parts = matplotlib.__version__.split(".")
        version = tuple(int(part) for part in version_parts[:2])
        label_keyword = "tick_labels" if version >= (3, 9) else "labels"
        axis.boxplot(arrays, **{label_keyword: list(labels)})
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.grid(True, axis="y", alpha=0.25)
        return self._save(figure, filename)

    def confidence_interval_plot(
        self,
        labels: Sequence[str],
        estimates: Iterable[float],
        lower: Iterable[float],
        upper: Iterable[float],
        *,
        title: str,
        ylabel: str,
        filename: str,
    ) -> Path:
        estimate_values = np.asarray(estimates, dtype=float)
        lower_values = np.asarray(lower, dtype=float)
        upper_values = np.asarray(upper, dtype=float)
        if not (
            len(labels) == estimate_values.size == lower_values.size == upper_values.size
        ):
            raise ValueError("confidence interval inputs must have the same length")
        errors = np.vstack(
            [estimate_values - lower_values, upper_values - estimate_values]
        )
        positions = np.arange(len(labels))
        figure, axis = plt.subplots()
        axis.errorbar(positions, estimate_values, yerr=errors, fmt="o", capsize=4)
        axis.set_xticks(positions, labels, rotation=30, ha="right")
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.grid(True, axis="y", alpha=0.25)
        return self._save(figure, filename)

    def bootstrap_distribution(
        self,
        values: Iterable[float],
        *,
        estimate: float,
        lower: float,
        upper: float,
        title: str,
        xlabel: str,
        bins: int,
        filename: str,
    ) -> Path:
        array = np.asarray(values, dtype=float)
        array = array[np.isfinite(array)]
        figure, axis = plt.subplots()
        axis.hist(array, bins=bins)
        axis.axvline(estimate, linewidth=1.5, label="Estimate")
        axis.axvline(lower, linestyle="--", linewidth=1, label="CI lower")
        axis.axvline(upper, linestyle="--", linewidth=1, label="CI upper")
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel("Frequency")
        axis.legend()
        return self._save(figure, filename)
