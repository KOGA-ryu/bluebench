from __future__ import annotations

from pathlib import Path

from backend.evidence.store.sqlite_store import SQLiteEvidenceStore
from backend.instrumentation.storage import InstrumentationStorage


def list_completed_runs(
    *,
    project_root: Path | None = None,
    storage: InstrumentationStorage | None = None,
) -> list[dict[str, object]]:
    runtime_storage = storage or InstrumentationStorage(
        (project_root or Path.cwd()) / ".bluebench" / "instrumentation.sqlite3"
    )
    runtime_storage.initialize_schema()
    return SQLiteEvidenceStore(runtime_storage).list_completed_runs(project_root=project_root)


def load_previous_comparable_run(
    run_id: str,
    *,
    project_root: Path | None = None,
    storage: InstrumentationStorage | None = None,
) -> dict[str, object] | None:
    runtime_storage = storage or InstrumentationStorage(
        (project_root or Path.cwd()) / ".bluebench" / "instrumentation.sqlite3"
    )
    runtime_storage.initialize_schema()
    return SQLiteEvidenceStore(runtime_storage).load_previous_comparable_run(run_id, project_root=project_root)


def resolve_display_run_evidence(
    active_run_id: str | None,
    run_view_mode: str,
    *,
    project_root: Path | None = None,
    storage: InstrumentationStorage | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if not active_run_id:
        return None, None
    runtime_storage = storage or InstrumentationStorage(
        (project_root or Path.cwd()) / ".bluebench" / "instrumentation.sqlite3"
    )
    runtime_storage.initialize_schema()
    evidence_store = SQLiteEvidenceStore(runtime_storage)
    selected = evidence_store.load_run_evidence(active_run_id)
    if selected is None:
        return None, None
    if run_view_mode == "previous":
        previous = evidence_store.load_previous_comparable_run(active_run_id, project_root=project_root)
        return selected, previous
    return selected, selected
