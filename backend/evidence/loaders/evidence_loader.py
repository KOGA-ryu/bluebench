from __future__ import annotations

from pathlib import Path

from backend.evidence.store.sqlite_store import SQLiteEvidenceStore
from backend.instrumentation.storage import InstrumentationStorage


def load_run_evidence(
    run_id: str,
    *,
    project_root: Path | None = None,
    storage: InstrumentationStorage | None = None,
) -> dict[str, object] | None:
    runtime_storage = storage or InstrumentationStorage(
        (project_root or Path.cwd()) / ".bluebench" / "instrumentation.sqlite3"
    )
    runtime_storage.initialize_schema()
    return SQLiteEvidenceStore(runtime_storage).load_run_evidence(run_id)
