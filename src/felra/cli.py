from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import yaml

from felra import __version__
from felra.batch import run_batch
from felra.config import load_project
from felra.export import export_paper_bundle
from felra.preregistration import verify_preregistration, write_preregistration
from felra.reproducibility import replay_run
from felra.evidence import write_evidence_bundle
from felra.figures import FigureFactory
from felra.models import Claim
from felra.registry import filter_registry_records, load_registry_records
from felra.runner import run_project
from felra.validation import VerificationOrchestrator, validate_predicate


def _template(project_id: str) -> dict[str, object]:
    return {
        "project": {"id": project_id, "title": project_id, "language": "zh-TW"},
        "execution": {"max_evaluations": 200000, "random_samples": 20000, "seed": 42},
        "preregistration": {
            "enabled": False,
            "path": ".felra-preregistration/preregistration.json",
            "mode": "warn",
        },
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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


    registry_parser = subparsers.add_parser(
        "registry", help="Inspect an append-only FELRA experiment registry"
    )
    registry_parser.add_argument("path", type=Path)
    registry_parser.add_argument("--limit", type=int, default=20)
    registry_parser.add_argument("--project", type=str, default=None)
    registry_parser.add_argument(
        "--status", choices=["passed", "failed", "all"], default="all"
    )

    preregister_parser = subparsers.add_parser(
        "preregister", help="Create an immutable scientific-plan preregistration record"
    )
    preregister_parser.add_argument("project_file", type=Path)
    preregister_parser.add_argument("--output", type=Path, default=None)
    preregister_parser.add_argument("--replace", action="store_true")

    verify_prereg_parser = subparsers.add_parser(
        "verify-preregistration", help="Compare a project with its preregistered plan"
    )
    verify_prereg_parser.add_argument("project_file", type=Path)
    verify_prereg_parser.add_argument("--record", type=Path, default=None)

    replay_parser = subparsers.add_parser(
        "replay", help="Re-run a FELRA evidence bundle and compare its result fingerprint"
    )
    replay_parser.add_argument("run_dir", type=Path)
    replay_parser.add_argument("--output", type=Path, default=Path("artifacts/replay"))

    export_parser = subparsers.add_parser(
        "export", help="Export a paper-ready reproducibility bundle from a FELRA run"
    )
    export_parser.add_argument("run_dir", type=Path)
    export_parser.add_argument("--output", type=Path, default=Path("artifacts/paper-bundle"))

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
    elif args.command == "registry":
        passed = None if args.status == "all" else args.status == "passed"
        records = filter_registry_records(
            load_registry_records(args.path), project_id=args.project, passed=passed
        )
        limit = max(0, args.limit)
        selected = records[-limit:] if limit else []
        if not selected:
            print("No matching FELRA registry records.")
        for record in selected:
            status = "PASS" if record.get("passed") else "ATTENTION"
            print(
                f"{record.get('created_at')}  {status:<9} "
                f"{record.get('project_id')}  {record.get('run_id')}"
            )
    elif args.command == "preregister":
        project = load_project(args.project_file)
        output = args.output
        if output is None:
            output = Path(project.preregistration.path)
            if not output.is_absolute():
                output = project.source_path.parent / output
        record = write_preregistration(project, output.resolve(), replace=args.replace)
        print(f"Preregistered {record['project_id']}: {output.resolve()}")
        print(f"Plan SHA-256: {record['plan_sha256']}")
    elif args.command == "verify-preregistration":
        project = load_project(args.project_file)
        record_path = args.record
        if record_path is None:
            record_path = Path(project.preregistration.path)
            if not record_path.is_absolute():
                record_path = project.source_path.parent / record_path
        result = verify_preregistration(project, record_path.resolve())
        print(f"Preregistration status: {result.status}")
        print(result.message)
        if not result.matched:
            raise SystemExit(2)
    elif args.command == "replay":
        result = replay_run(args.run_dir.resolve(), args.output.resolve())
        status = "MATCH" if result["matched"] else "MISMATCH"
        print(f"FELRA replay: {status} — {args.output}")
        if not result["matched"]:
            raise SystemExit(3)
    elif args.command == "export":
        manifest = export_paper_bundle(args.run_dir.resolve(), args.output.resolve())
        print(
            f"FELRA paper bundle exported: {args.output} "
            f"({len(manifest['files'])} indexed files)"
        )
    elif args.command == "demo":
        _run_demo(args.output)


if __name__ == "__main__":
    main()
