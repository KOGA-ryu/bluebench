from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.adapters.cli.commands import cold_start_command, compare_run_command, stress_canonical_command
from backend.chain_artifact import write_verified_chain_result
from backend.instrumentation.storage import InstrumentationStorage
from backend.recommend import recommend_next_experiment
from backend.version import load_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BlueBench product entrypoint.")
    parser.add_argument("--version", action="store_true", help="Print BlueBench version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    ui_parser = subparsers.add_parser("ui", help="Launch the BlueBench desktop shell.")
    ui_parser.add_argument("--project-root", default=str(REPO_ROOT))

    run_parser = subparsers.add_parser("run", help="Run BlueBench evidence collection on a script target.")
    run_parser.add_argument("target", help="Python script path or module name.")
    run_parser.add_argument("--project-root", default=str(REPO_ROOT))
    run_parser.add_argument("--run-name", default="bluebench_cli_run")
    run_parser.add_argument("--scenario-kind", default="custom_script")
    run_parser.add_argument("--hardware-profile", default="local_machine")
    run_parser.add_argument("--database", default=None)
    run_parser.add_argument("--module", action="store_true", help="Treat target as a Python module name.")
    run_parser.add_argument("target_args", nargs=argparse.REMAINDER, help="Arguments passed to the target after --.")

    compare_parser = subparsers.add_parser("compare", help="Compare two completed runs.")
    compare_parser.add_argument("baseline")
    compare_parser.add_argument("current")
    compare_parser.add_argument("--project-root", default=str(REPO_ROOT))
    compare_parser.add_argument("--chain-id")
    compare_parser.add_argument("--target")

    recommend_parser = subparsers.add_parser("recommend-next", help="Emit the next deterministic recommendation.")
    recommend_parser.add_argument("--target", required=True)
    recommend_parser.add_argument("--run", dest="run_id")
    recommend_parser.add_argument("--baseline", dest="baseline_run_id")
    recommend_parser.add_argument("--project-root", default=str(REPO_ROOT))

    cold_start_parser = subparsers.add_parser("cold-start", help="Inspect a repo and emit a compact first-pass packet.")
    cold_start_parser.add_argument("--repo", required=True)

    stress_parser = subparsers.add_parser("stress-canonical", help="Run the canonical endurance loop.")
    stress_parser.add_argument("--iterations", type=int, default=100)
    stress_parser.add_argument("--project-root", default=str(REPO_ROOT))
    stress_parser.add_argument("--jitter-ms", type=float, default=0.0)
    stress_parser.add_argument("--inject-history-failure-every", type=int, default=0)
    stress_parser.add_argument("--seed", type=int, default=7)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(load_version())
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "ui":
        return _run_subprocess([sys.executable, str(REPO_ROOT / "backend" / "main.py")])
    if args.command == "run":
        return _run_instrumented_target(args)
    if args.command == "compare":
        payload = compare_run_command(Path(args.project_root), args.baseline, args.current)
        if args.chain_id and args.target:
            chain_path = write_verified_chain_result(
                Path(args.project_root),
                chain_id=str(args.chain_id),
                review_target=str(args.target),
                bluebench_run_id=str(args.current),
                comparison=dict(payload["comparison"]),
            )
            payload["chain_artifact_path"] = str(chain_path)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "recommend-next":
        payload = recommend_next_experiment(
            args.target,
            run_id=args.run_id,
            baseline_run_id=args.baseline_run_id,
            project_root=Path(args.project_root),
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "cold-start":
        payload = cold_start_command(Path(args.repo))
        print(payload["formatted_summary"])
        return 0
    if args.command == "stress-canonical":
        project_root = Path(args.project_root)
        storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
        return stress_canonical_command(
            project_root,
            args.iterations,
            stdout=sys.stdout,
            storage=storage,
            jitter_ms=args.jitter_ms,
            inject_history_failure_every=args.inject_history_failure_every,
            seed=args.seed,
        )
    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_instrumented_target(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser().resolve()
    database = Path(args.database).expanduser().resolve() if args.database else project_root / ".bluebench" / "instrumentation.sqlite3"
    command = [
        sys.executable,
        "-m",
        "backend.instrumentation.script_runner",
        "--database",
        str(database),
        "--project-root",
        str(project_root),
        "--run-name",
        str(args.run_name),
        "--scenario-kind",
        str(args.scenario_kind),
        "--hardware-profile",
        str(args.hardware_profile),
    ]
    if args.module:
        command.extend(["--module-name", str(args.target)])
    else:
        command.extend(["--script-path", str(Path(args.target).expanduser().resolve())])
    command.append("--")
    target_args = list(args.target_args or [])
    if target_args and target_args[0] == "--":
        target_args = target_args[1:]
    command.extend(target_args)
    return _run_subprocess(command)


def _run_subprocess(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=str(REPO_ROOT))
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
