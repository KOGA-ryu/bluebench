from __future__ import annotations

from typing import Any

DERIVE_VERSION = "1"


def compare_runs(
    baseline: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline_data = dict(baseline or {})
    current_data = dict(current or {})
    baseline_measured = dict(baseline_data.get("measured") or {})
    current_measured = dict(current_data.get("measured") or {})
    baseline_stages = dict(baseline_data.get("stages") or {})
    current_stages = dict(current_data.get("stages") or {})
    baseline_files = {str(item.get("file_path")): float(item.get("raw_ms") or 0.0) for item in baseline_data.get("files", []) or []}
    current_files = {str(item.get("file_path")): float(item.get("raw_ms") or 0.0) for item in current_data.get("files", []) or []}
    baseline_schema_version = str(baseline_data.get("schema_version") or "")
    current_schema_version = str(current_data.get("schema_version") or "")
    schema_compatible = not baseline_schema_version or not current_schema_version or baseline_schema_version == current_schema_version
    comparison_warnings: list[str] = []
    if not schema_compatible:
        comparison_warnings.append(
            f"Evidence schema mismatch: baseline={baseline_schema_version or '-'} current={current_schema_version or '-'}."
        )

    return {
        "derive_version": DERIVE_VERSION,
        "schema_versions": {
            "baseline": baseline_schema_version or None,
            "current": current_schema_version or None,
        },
        "schema_compatible": schema_compatible,
        "comparison_warnings": comparison_warnings,
        "runtime_delta_ms": _delta(current_measured.get("runtime_ms"), baseline_measured.get("runtime_ms")),
        "trace_overhead_delta_ms": _delta(current_measured.get("trace_overhead_ms"), baseline_measured.get("trace_overhead_ms")),
        "stage_deltas": {
            key: _delta(current_stages.get(key), baseline_stages.get(key))
            for key in sorted(set(baseline_stages) | set(current_stages))
        },
        "file_deltas": sorted(
            [
                {
                    "file_path": key,
                    "raw_ms_delta": _delta(current_files.get(key), baseline_files.get(key)),
                }
                for key in sorted(set(baseline_files) | set(current_files))
            ],
            key=lambda item: (-abs(float(item["raw_ms_delta"] or 0.0)), str(item["file_path"]).lower()),
        ),
    }


def _delta(current: Any, baseline: Any) -> float | None:
    try:
        current_value = float(current)
    except (TypeError, ValueError):
        current_value = None
    try:
        baseline_value = float(baseline)
    except (TypeError, ValueError):
        baseline_value = None
    if current_value is None and baseline_value is None:
        return None
    return float(current_value or 0.0) - float(baseline_value or 0.0)
