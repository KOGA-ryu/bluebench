from __future__ import annotations

from pathlib import Path

from backend.evidence.loaders.evidence_loader import load_run_evidence
from backend.instrumentation.storage import InstrumentationStorage


class RunEngine:
    def __init__(self, project_root: Path, storage: InstrumentationStorage | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.storage = storage or InstrumentationStorage(self.project_root / ".bluebench" / "instrumentation.sqlite3")
        self.storage.initialize_schema()

    def load_run_evidence(self, run_id: str) -> dict[str, object] | None:
        return load_run_evidence(run_id, project_root=self.project_root, storage=self.storage)
