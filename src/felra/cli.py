from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import yaml

from felra.evidence import write_evidence_bundle
from felra.figures import FigureFactory
from felra.models import Claim
from felra.validation import VerificationOrchestrator, validate_predicate


def _init_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    project = {
        "project": {"id": path.name, "title": path.name, "language": "zh-TW"},
        "claims": [
            {
                "id": "claim_001",
                "statement": "在聲明域內填寫可計算檢驗的研究命題",
                "status": "hypothesis",
                "required_checks": ["numerical", "boundaries", "counterexample_search"],
            }
        ],
        "parameters": {"x": {"type": "float", "range": [-10, 10], "samples": 1001}},
        "outputs": {"figures": ["line_plot"], "formats": ["png"]},
    }
    (path / "project.yaml").write_text(
        yaml.safe_dump(project, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (path / "README.md").write_text(
        "# FELRA Research Project\n\nEdit `project.yaml`, then add experiment code.\n",
        encoding="utf-8",
    )


def _run_demo(output: Path) -> None:
    claim = Claim(
        claim_id="demo_nonnegative_square",
        statement="For every sampled real x in [-10, 10], x² is non-negative.",
        domain_description="10,001 evenly spaced float64 samples on [-10, 10]",
    )
    samples = np.linspace(-10.0, 10.0, 10_001)
    orchestrator = VerificationOrchestrator(claim).add_check(
        lambda: validate_predicate(lambda x: x * x >= 0.0, samples)
    )
    bundle = orchestrator.run()

    figure_path = FigureFactory(output / "figures").line_plot(
        samples,
        samples**2,
        title="Non-negativity of the square function",
        xlabel="x",
        ylabel="x²",
        filename="nonnegative_square.png",
    )
    bundle.figures.append(str(figure_path.relative_to(output)))
    write_evidence_bundle(bundle, output)
    print(f"Demo complete: {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="felra")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a FELRA research project")
    init_parser.add_argument("path", type=Path)

    demo_parser = subparsers.add_parser("demo", help="Run the built-in validation demo")
    demo_parser.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init":
        _init_project(args.path)
        print(f"Created FELRA project: {args.path}")
    elif args.command == "demo":
        _run_demo(args.output)


if __name__ == "__main__":
    main()
