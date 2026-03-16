from __future__ import annotations

import json
from typing import Any

from backend.instrumentation.storage import InstrumentationStorage


def build_file_compute_details(
    storage: InstrumentationStorage,
    run_id: str | None,
    file_path: str,
) -> dict[str, Any]:
    if not run_id or not file_path:
        return {}
    row = storage.fetch_file_summary(run_id, file_path)
    if row is None:
        return {}
    current_score = float(row["normalized_compute_score"])
    delta: float | None = None
    run_row = storage.fetch_run(run_id)
    if run_row is not None:
        previous_run_id = storage.fetch_previous_comparable_run_id(
            run_id,
            str(run_row["scenario_kind"]),
            str(run_row["hardware_profile"]),
            run_row["project_root"],
        )
        if previous_run_id:
            previous_row = storage.fetch_file_summary(previous_run_id, file_path)
            previous_score = float(previous_row["normalized_compute_score"]) if previous_row is not None else 0.0
            delta = current_score - previous_score
    external_summary = json.loads(str(row["external_pressure_summary"])) if row["external_pressure_summary"] else {}
    return {
        "file_path": str(row["file_path"]),
        "normalized_compute_score": current_score,
        "compute_tier": 9 if current_score >= 67 else 6 if current_score >= 34 else 3,
        "compute_tally": current_score,
        "total_self_time_ms": float(row["total_self_time_ms"]),
        "total_time_ms": float(row["total_time_ms"]),
        "call_count": int(row["call_count"]),
        "exception_count": int(row["exception_count"]),
        "rolling_score": float(row["rolling_score"]),
        "delta": delta,
        "external_pressure_summary": external_summary if isinstance(external_summary, dict) else {},
    }


def build_function_compute_details(
    storage: InstrumentationStorage,
    run_id: str | None,
    file_path: str,
) -> list[dict[str, Any]]:
    if not run_id or not file_path:
        return []
    function_compute: list[dict[str, Any]] = []
    for row in storage.fetch_function_summaries_for_file(run_id, file_path):
        symbol_key = str(row["symbol_key"])
        symbol_name = symbol_key.split("::", 1)[1] if "::" in symbol_key else str(row["display_name"])
        function_compute.append(
            {
                "symbol_key": symbol_key,
                "symbol_name": symbol_name,
                "display_name": str(row["display_name"]),
                "self_time_ms": float(row["self_time_ms"]),
                "total_time_ms": float(row["total_time_ms"]),
                "call_count": int(row["call_count"]),
                "exception_count": int(row["exception_count"]),
                "last_exception_type": row["last_exception_type"],
                "normalized_compute_score": float(row["normalized_compute_score"]),
            }
        )
    return function_compute
