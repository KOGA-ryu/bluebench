from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.derive.summary_builder import build_run_summary
from backend.evidence.loaders.run_loader import resolve_display_run_evidence
from backend.instrumentation.storage import InstrumentationStorage


def build_codex_context_pack(
    project_root: Path,
    active_run_id: str | None,
    run_view_mode: str,
    *,
    storage: InstrumentationStorage | None = None,
    limit_hot_files: int = 10,
) -> dict[str, Any]:
    runtime_storage = storage or InstrumentationStorage(Path(project_root).resolve() / ".bluebench" / "instrumentation.sqlite3")
    runtime_storage.initialize_schema()
    selected_run, display_run = resolve_display_run_evidence(
        active_run_id,
        run_view_mode,
        project_root=Path(project_root).resolve(),
        storage=runtime_storage,
    )
    previous_run = None
    if selected_run and display_run and selected_run.get("run_id") == display_run.get("run_id"):
        from backend.evidence.loaders.run_loader import load_previous_comparable_run

        previous_run = load_previous_comparable_run(str(selected_run["run_id"]), project_root=Path(project_root).resolve(), storage=runtime_storage)
    elif display_run and selected_run and display_run.get("run_id") != selected_run.get("run_id"):
        previous_run = selected_run
    summary = build_run_summary(display_run, previous_run, limit_hot_files=limit_hot_files)
    return {
        "selected_run": selected_run,
        "display_run": display_run,
        "summary": summary,
    }
