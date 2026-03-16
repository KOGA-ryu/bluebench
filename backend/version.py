from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_version() -> str:
    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        return version_path.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"
