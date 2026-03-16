from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from backend.instrumentation.storage import InstrumentationStorage
from .exporter import export_triage_json, export_triage_markdown
from .service import generate_triage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a BlueBench triage report for a project.")
    parser.add_argument("--project-root", required=True, help="Path to the project root")
    parser.add_argument("--run-id", default=None, help="Completed run id to use for runtime-aware triage")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick", help="Triage depth")
    parser.add_argument(
        "--database",
        default=None,
        help="Path to instrumentation SQLite database. Defaults to <project>/.bluebench/instrumentation.sqlite3",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for bb_triage_report.json and bb_triage_report.md. Defaults to project root.",
    )
    return parser


def main(argv: list[str] | None = None, stdout: TextIO | None = None) -> int:
    output = stdout or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).expanduser().resolve()
    database_path = (
        Path(args.database).expanduser().resolve()
        if args.database
        else project_root / ".bluebench" / "instrumentation.sqlite3"
    )
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else project_root

    storage = InstrumentationStorage(database_path)
    triage = generate_triage(project_root, run_id=args.run_id, mode=args.mode, storage=storage)

    json_path = export_triage_json(triage, output_dir / "bb_triage_report.json")
    markdown_path = export_triage_markdown(triage, output_dir / "bb_triage_report.md")

    _print_summary(triage, json_path, markdown_path, output)
    return 0


def _print_summary(
    triage: dict[str, object],
    json_path: Path,
    markdown_path: Path,
    output: TextIO,
) -> None:
    project = dict(triage.get("project") or {})
    runtime_context = dict(triage.get("runtime_context") or {})
    compute = dict(triage.get("compute") or {})
    recommendations = list(triage.get("recommended_actions") or [])

    print(f"Project: {project.get('name', '-')}", file=output)
    print(f"Root: {project.get('root', '-')}", file=output)
    print(f"App Type Guess: {project.get('app_type_guess', '-')}", file=output)
    entry_points = list(project.get("entry_points") or [])
    if entry_points:
        top_entry = entry_points[0]
        print(f"Top Entry Point: {top_entry.get('path', '-')} (score {int(top_entry.get('score', 0))})", file=output)
    selected_run = runtime_context.get("selected_run")
    if isinstance(selected_run, dict):
        print(
            f"Run: {selected_run.get('run_name', '-')} · {selected_run.get('scenario_kind', '-')} · {selected_run.get('hardware_profile', '-')}",
            file=output,
        )
    else:
        print("Run: none", file=output)
    print("Hot Files:", file=output)
    hot_files = list(compute.get("hot_files") or [])
    if not hot_files:
        print("- none", file=output)
    else:
        for item in hot_files[:5]:
            print(
                f"- {item.get('file_path', '-')} · score {float(item.get('normalized_compute_score', 0.0)):.1f} · {float(item.get('total_time_ms', 0.0)):.1f} ms",
                file=output,
            )
    print("Recommended Actions:", file=output)
    if not recommendations:
        print("- none", file=output)
    else:
        for item in recommendations[:5]:
            print(f"- {item.get('title', '-')} [{item.get('confidence', '-')}] ", file=output)
    print(f"JSON: {json_path}", file=output)
    print(f"Markdown: {markdown_path}", file=output)


if __name__ == "__main__":
    raise SystemExit(main())
