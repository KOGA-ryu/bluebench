from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from backend.instrumentation.storage import InstrumentationStorage

from .exporters import export_context_json, export_context_markdown
from .service import build_context_pack


def main(argv: list[str] | None = None, output: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an AI Context Pack for a BlueBench project.")
    parser.add_argument("--project-root", required=True, help="Project root to summarize")
    parser.add_argument("--run-id", default=None, help="Selected run id override")
    parser.add_argument(
        "--run-view-mode",
        choices=("current", "previous"),
        default=None,
        help="Display run view override. Defaults to saved session state or current.",
    )
    parser.add_argument(
        "--mode",
        choices=("tiny", "short", "full"),
        default="short",
        help="Context compression level",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Path to instrumentation sqlite database. Defaults to project-local .bluebench database.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for bb_context_<mode>.json and bb_context_<mode>.md. Defaults to project root/.bluebench.",
    )
    parsed = parser.parse_args(argv)
    stream = output or sys.stdout

    project_root = Path(parsed.project_root).expanduser().resolve()
    db_path = (
        Path(parsed.database).expanduser().resolve()
        if parsed.database
        else project_root / ".bluebench" / "instrumentation.sqlite3"
    )
    storage = InstrumentationStorage(db_path)
    storage.initialize_schema()

    context_pack = build_context_pack(
        project_root,
        parsed.run_id,
        parsed.run_view_mode or "current",
        mode=parsed.mode,
        storage=storage,
    )
    output_dir = (
        Path(parsed.output_dir).expanduser().resolve()
        if parsed.output_dir
        else project_root / ".bluebench"
    )
    json_path = export_context_json(context_pack, output_dir / f"bb_context_{parsed.mode}.json")
    markdown_path = export_context_markdown(context_pack, output_dir / f"bb_context_{parsed.mode}.md")
    _print_summary(context_pack, json_path, markdown_path, stream)
    return 0


def _print_summary(
    context_pack: dict[str, object],
    json_path: Path,
    markdown_path: Path,
    output: TextIO,
) -> None:
    project = dict(context_pack.get("project") or {})
    session = dict(context_pack.get("session") or {})
    compute = dict(context_pack.get("compute") or {})
    output.write(f"Project: {project.get('name', '-')}\n")
    output.write(f"Mode: {context_pack.get('mode', '-')}\n")
    output.write(f"Selected Run: {session.get('selected_run_id') or 'none'}\n")
    output.write(f"Display Run: {session.get('display_run_id') or 'none'}\n")
    output.write(f"Hot Files: {len(compute.get('hot_files') or [])}\n")
    output.write(f"JSON: {json_path}\n")
    output.write(f"Markdown: {markdown_path}\n")


if __name__ == "__main__":
    raise SystemExit(main())
