from __future__ import annotations

import json
from pathlib import Path

from backend.instrumentation.storage import InstrumentationStorage


def summarize_runtime(
    project_root: Path,
    storage: InstrumentationStorage,
    run_id: str | None,
) -> dict[str, object]:
    project_root = project_root.resolve()
    if not run_id:
        return _empty_runtime_summary(project_root)

    run_row = storage.fetch_run(run_id)
    if run_row is None:
        return _empty_runtime_summary(project_root)

    previous_run_id = storage.fetch_previous_comparable_run_id(
        run_id,
        str(run_row["scenario_kind"]),
        str(run_row["hardware_profile"]),
        run_row["project_root"],
    )
    previous_run = storage.fetch_run(previous_run_id) if previous_run_id else None
    run_summary = storage.fetch_run_summary(run_id)
    file_summaries = storage.fetch_file_summaries(run_id, limit=10)
    hottest_files = [
        {
            "file_path": str(row["file_path"]),
            "normalized_compute_score": float(row["normalized_compute_score"]),
            "rolling_score": float(row["rolling_score"]),
            "total_time_ms": float(row["total_time_ms"]),
            "exception_count": int(row["exception_count"]),
        }
        for row in file_summaries
    ]
    hot_functions = []
    for row in file_summaries[:3]:
        hot_functions.extend(
            {
                "file_path": str(func_row["file_path"]),
                "display_name": str(func_row["display_name"]),
                "normalized_compute_score": float(func_row["normalized_compute_score"]),
                "total_time_ms": float(func_row["total_time_ms"]),
                "call_count": int(func_row["call_count"]),
                "exception_count": int(func_row["exception_count"]),
            }
            for func_row in storage.fetch_function_summaries_for_file(run_id, str(row["file_path"]))[:3]
        )
    external_pressure = _external_pressure(hottest_files, storage, run_id)
    report = _load_performance_report(project_root)
    deltas = []
    failure_count = 0
    if run_summary is not None:
        deltas = json.loads(str(run_summary["biggest_score_deltas_json"]))
        failure_count = int(run_summary["failure_count"])

    return {
        "selected_run": {
            "run_id": str(run_row["run_id"]),
            "run_name": str(run_row["run_name"]),
            "project_root": str(run_row["project_root"] or project_root),
            "scenario_kind": str(run_row["scenario_kind"]),
            "hardware_profile": str(run_row["hardware_profile"]),
            "status": str(run_row["status"]),
            "started_at": str(run_row["started_at"]),
            "finished_at": str(run_row["finished_at"] or ""),
        },
        "previous_comparable_run": (
            {
                "run_id": str(previous_run["run_id"]),
                "run_name": str(previous_run["run_name"]),
                "finished_at": str(previous_run["finished_at"] or ""),
            }
            if previous_run is not None
            else None
        ),
        "hot_files": hottest_files,
        "hot_functions": sorted(
            hot_functions,
            key=lambda entry: (-float(entry["normalized_compute_score"]), -float(entry["total_time_ms"]), str(entry["display_name"]).lower()),
        )[:10],
        "external_pressure": external_pressure,
        "failures": {
            "failure_count": failure_count,
            "failure_heavy_files": [item for item in hottest_files if int(item["exception_count"]) > 0][:10],
        },
        "regressions": [
            {
                "file_path": str(item.get("file_path") or ""),
                "score_delta": float(item.get("score_delta") or 0.0),
            }
            for item in deltas[:10]
        ],
        "quality_warnings": _quality_warnings(run_summary, report, hottest_files),
        "performance_report": report,
    }


def _empty_runtime_summary(project_root: Path) -> dict[str, object]:
    return {
        "selected_run": None,
        "previous_comparable_run": None,
        "hot_files": [],
        "hot_functions": [],
        "external_pressure": [],
        "failures": {"failure_count": 0, "failure_heavy_files": []},
        "regressions": [],
        "quality_warnings": ["No selected completed run."],
        "performance_report": _load_performance_report(project_root),
    }


def _external_pressure(
    hottest_files: list[dict[str, object]],
    storage: InstrumentationStorage,
    run_id: str,
) -> list[dict[str, object]]:
    pressure: list[dict[str, object]] = []
    for item in hottest_files:
        row = storage.fetch_file_summary(run_id, str(item["file_path"]))
        if row is None:
            continue
        raw_summary = str(row["external_pressure_summary"] or "")
        if not raw_summary:
            continue
        try:
            parsed = json.loads(raw_summary)
        except json.JSONDecodeError:
            continue
        buckets = parsed.get("external_buckets")
        if not isinstance(buckets, dict):
            continue
        for bucket_name, values in buckets.items():
            if not isinstance(values, dict):
                continue
            total_time_ms = float(values.get("total_time_ms") or 0.0)
            if total_time_ms <= 0.0:
                continue
            pressure.append(
                {
                    "file_path": str(item["file_path"]),
                    "bucket_name": str(bucket_name),
                    "total_time_ms": total_time_ms,
                    "call_count": int(values.get("call_count") or 0),
                }
            )
    return sorted(pressure, key=lambda entry: (-float(entry["total_time_ms"]), str(entry["bucket_name"]).lower()))[:15]


def _load_performance_report(project_root: Path) -> dict[str, object] | None:
    report_path = project_root / "bb_performance_report.json"
    if not report_path.is_file():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _quality_warnings(
    run_summary,
    performance_report: dict[str, object] | None,
    hottest_files: list[dict[str, object]],
) -> list[str]:
    warnings: list[str] = []
    if run_summary is not None and int(run_summary["failure_count"]) > 0:
        warnings.append(f"{int(run_summary['failure_count'])} failures were recorded in this run.")
    if len(hottest_files) <= 3:
        warnings.append(f"Only {len(hottest_files)} files appear in the top measured set.")
    if performance_report is None:
        warnings.append("Performance report is missing.")
        return warnings
    files_seen = int(performance_report.get("files_seen", 0))
    if files_seen <= 3:
        warnings.append(f"Only {files_seen} files were seen during instrumentation.")
    runtime_ms = float(performance_report.get("instrumented_runtime_ms", 0.0))
    trace_overhead_ms = float(performance_report.get("trace_overhead_estimate_ms", 0.0))
    if runtime_ms > 0.0 and trace_overhead_ms / runtime_ms >= 0.5:
        warnings.append("Tracer overhead is at least 50% of measured runtime.")
    return warnings
