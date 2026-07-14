from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AnalysisResult:
    analysis_id: str
    kind: str
    title: str
    success: bool
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    claim_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
