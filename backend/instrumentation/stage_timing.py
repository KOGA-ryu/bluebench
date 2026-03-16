from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
import time


def record_stage_timing(name: str, elapsed_ms: float) -> None:
    path = _stage_timings_path()
    if path is None:
        return
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing[str(name)] = float(elapsed_ms)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")


@contextmanager
def timed_stage(name: str):
    started = time.perf_counter()
    try:
        yield
    finally:
        record_stage_timing(name, (time.perf_counter() - started) * 1000.0)


def load_stage_timings() -> dict[str, float]:
    path = _stage_timings_path()
    if path is None or not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in loaded.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def clear_stage_timings() -> None:
    path = _stage_timings_path()
    if path is None or not path.exists():
        return
    try:
        path.unlink()
    except OSError:
        return


def _stage_timings_path() -> Path | None:
    value = os.environ.get("BLUEBENCH_STAGE_TIMINGS_PATH", "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()
