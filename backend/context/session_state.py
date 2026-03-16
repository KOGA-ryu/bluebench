from __future__ import annotations

import json
from pathlib import Path


def default_session_path(project_root: Path) -> Path:
    resolved_root = Path(project_root).expanduser().resolve()
    return resolved_root / ".bluebench" / "session.json"


def load_session_state(project_root: Path) -> dict[str, object]:
    session_path = default_session_path(project_root)
    if not session_path.is_file():
        return {}
    try:
        loaded = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save_session_state(project_root: Path, state: dict[str, object]) -> Path:
    session_path = default_session_path(project_root)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    return session_path
