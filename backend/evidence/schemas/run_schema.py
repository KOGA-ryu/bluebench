from __future__ import annotations

from typing import Any

EVIDENCE_SCHEMA_VERSION = "1"


def normalize_run_evidence(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    measured = dict(data.get("measured") or {})
    stages = dict(data.get("stages") or {})
    files = list(data.get("files") or [])
    return {
        "schema_version": str(data.get("schema_version") or EVIDENCE_SCHEMA_VERSION),
        "run_id": str(data.get("run_id") or ""),
        "run_name": str(data.get("run_name") or ""),
        "timestamp": str(data.get("timestamp") or ""),
        "status": str(data.get("status") or ""),
        "quality": str(data.get("quality") or "") or None,
        "project_root": str(data.get("project_root") or ""),
        "scenario_kind": str(data.get("scenario_kind") or ""),
        "hardware_profile": str(data.get("hardware_profile") or ""),
        "measured": {
            "runtime_ms": _to_float(measured.get("runtime_ms")),
            "trace_overhead_ms": _to_float(measured.get("trace_overhead_ms")),
        },
        "stages": {
            str(key): float(value)
            for key, value in stages.items()
            if _to_float(value) is not None
        },
        "files": [
            {
                "file_path": str(item.get("file_path") or ""),
                "raw_ms": float(item.get("raw_ms") or 0.0),
                "call_count": _to_int(item.get("call_count")),
                "rolling_score": _to_float(item.get("rolling_score")),
                "normalized_compute_score": _to_float(item.get("normalized_compute_score")),
            }
            for item in files
            if str(item.get("file_path") or "")
        ],
    }


def build_run_evidence(
    *,
    run_id: str,
    run_name: str,
    timestamp: str,
    status: str,
    quality: str | None,
    project_root: str,
    scenario_kind: str,
    hardware_profile: str,
    runtime_ms: float | None,
    trace_overhead_ms: float | None,
    stages: dict[str, float] | None,
    files: list[dict[str, Any]] | None,
    schema_version: str = EVIDENCE_SCHEMA_VERSION,
) -> dict[str, Any]:
    return normalize_run_evidence(
        {
            "schema_version": schema_version,
            "run_id": run_id,
            "run_name": run_name,
            "timestamp": timestamp,
            "status": status,
            "quality": quality,
            "project_root": project_root,
            "scenario_kind": scenario_kind,
            "hardware_profile": hardware_profile,
            "measured": {
                "runtime_ms": runtime_ms,
                "trace_overhead_ms": trace_overhead_ms,
            },
            "stages": stages or {},
            "files": files or [],
        }
    )


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
