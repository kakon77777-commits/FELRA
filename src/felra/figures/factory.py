from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


class FigureFactory:
    """Generate traceable academic figures with conservative defaults."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        x_values = np.asarray(list(x), dtype=float)
        y_values = np.asarray(list(y), dtype=float)
        if x_values.shape != y_values.shape:
            raise ValueError("x and y must have the same shape")

        figure, axis = plt.subplots()
        axis.plot(x_values, y_values)
        axis.set_title(title)
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)
        figure.tight_layout()

        path = self.output_dir / filename
        figure.savefig(path, dpi=180)
        plt.close(figure)
        return path
