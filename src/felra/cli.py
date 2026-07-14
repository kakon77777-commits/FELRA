from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import yaml

from felra.batch import run_batch
from felra.evidence import write_evidence_bundle
from felra.figures import FigureFactory
from felra.models import Claim
from felra.runner import run_project
from felra.validation import VerificationOrchestrator, validate_predicate


def _template(project_id: str) -> dict[str, object]:
    return {
        "project": {"id": project_id, "title": project_id, "language": "zh-TW"},
        "execution": {"max_evaluations": 200000, "random_samples": 20000, "seed": 42},
        "parameters": {
            "x": {"type": "float", "range": [-10, 10], "samples": 1001},
            "a": {"type": "float", "range": [0.5, 2.0], "samples": 31},
        },
        "claims": [
            {
                "id": "claim_001",
                "statement": "在聲明域內，a·x² 皆非負",
                "expression": "a * x ** 2 >= 0",
                "status": "hypothesis",
                "required_checks": ["numerical", "boundaries", "counterexample_search"],
            }
        ],
        "analyses": [
            {
                "id": "local_sensitivity",
                "type": "sensitivity",
                "title": "基準點局部敏感度",
                "expression": "a * x ** 2",
                "parameters": ["x", "a"],
                "baseline": {"x": 1.0, "a": 1.0},
                "claim_id": "claim_001",
            },
            {
                "id": "coefficient_sweep",
                "type": "parameter_sweep",
                "title": "係數參數掃描",
                "objective": "(a - 1.25) ** 2",
                "parameters": ["a"],
                "goal": "minimize",
                "fixed": {"x": 1.0},
                "claim_id": "claim_001",
            },
        ],
        "outputs": {
            "figures": [
                {
                    "id": "square_curve",
                    "type": "line",
                    "x": "x",
                    "y": "a * x ** 2",
                    "title": "平方函數族中央切片",
                    "xlabel": "x",
                    "ylabel": "a·x²",
                    "filename": "square_curve.png",
                    "claim_id": "claim_001",
                }
            ]
        },
    }


def _init_project(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)
    (path / "project.yaml").write_text(
        yaml.safe_dump(_template(path.name), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (path / "README.md").write_text(
        "# FELRA Research Project\n\nRun `felra run project.yaml --output artifacts/run`.\n",
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

    run_parser = subparsers.add_parser("run", help="Run a declarative FELRA project")
    run_parser.add_argument("project_file", type=Path)
    run_parser.add_argument("--output", type=Path, default=Path("artifacts/run"))

    batch_parser = subparsers.add_parser("batch", help="Run a FELRA batch manifest")
    batch_parser.add_argument("batch_file", type=Path)
    batch_parser.add_argument("--output", type=Path, default=Path("artifacts/batch"))
    batch_parser.add_argument("--workers", type=int, default=None)

    demo_parser = subparsers.add_parser("demo", help="Run the built-in validation demo")
    demo_parser.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "init":
        _init_project(args.path)
        print(f"Created FELRA project: {args.path}")
    elif args.command == "run":
        run = run_project(args.project_file, args.output)
        result = "PASS" if run.passed else "ATTENTION REQUIRED"
        print(f"FELRA project complete: {result} — {args.output}")
        if run.warnings:
            print(f"Warnings: {len(run.warnings)} (see project_report.md)")
    elif args.command == "batch":
        run = run_batch(args.batch_file, args.output, workers=args.workers)
        result = "PASS" if run.passed else "ATTENTION REQUIRED"
        print(f"FELRA batch complete: {result} — {args.output}")
    elif args.command == "demo":
        _run_demo(args.output)


if __name__ == "__main__":
    main()
