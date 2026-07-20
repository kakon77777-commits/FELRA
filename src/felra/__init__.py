"""FELRA Python-first academic verification workbench."""

from .config import ProjectSpec, load_project
from .models import Claim, EvidenceBundle, ValidationResult
from .runner import ProjectRun, run_project

__all__ = [
    "Claim",
    "EvidenceBundle",
    "ProjectRun",
    "ProjectSpec",
    "ValidationResult",
    "load_project",
    "run_project",
]
__version__ = "0.7.0"
