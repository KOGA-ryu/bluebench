from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.context import build_context_pack, export_context_json, export_context_markdown
from backend.instrumentation.storage import InstrumentationStorage
from backend.triage.service import generate_triage


def main() -> int:
    project_root = PROJECT_ROOT
    storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
    storage.initialize_schema()
    triage = generate_triage(project_root, mode="full", storage=storage)
    context_pack = build_context_pack(project_root, None, "current", mode="short", storage=storage)
    export_context_json(context_pack, project_root / ".bluebench" / "bb_context_short.json")
    export_context_markdown(context_pack, project_root / ".bluebench" / "bb_context_short.md")
    if not triage.get("project"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
