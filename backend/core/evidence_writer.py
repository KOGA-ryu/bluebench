from __future__ import annotations

from typing import Any

from backend.evidence.schemas.run_schema import build_run_evidence


def performance_report_to_run_evidence(
    report: dict[str, Any],
    *,
    run_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = dict(run_row or {})
    return build_run_evidence(
        run_id=str(row.get("run_id") or report.get("run_id") or ""),
        run_name=str(row.get("run_name") or report.get("run_name") or ""),
        timestamp=str(row.get("finished_at") or report.get("report_generated_at") or ""),
        status=str(row.get("status") or report.get("status") or ""),
        quality=str(report.get("run_quality") or "") or None,
        project_root=str(row.get("project_root") or ""),
        scenario_kind=str(row.get("scenario_kind") or report.get("scenario_kind") or ""),
        hardware_profile=str(row.get("hardware_profile") or report.get("hardware_profile") or ""),
        runtime_ms=_to_float(report.get("instrumented_runtime_ms")),
        trace_overhead_ms=_to_float(report.get("trace_overhead_estimate_ms")),
        stages={
            str(key): float(value)
            for key, value in dict(report.get("stage_timings_ms") or {}).items()
            if _to_float(value) is not None
        },
        files=list(report.get("top_files_by_raw_ms") or []),
    )


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
