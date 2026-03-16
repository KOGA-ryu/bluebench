from __future__ import annotations

from typing import Any


TRACE_OVERHEAD_RATIO_THRESHOLD = 0.4


def choose_next_experiment(
    *,
    target: str,
    run_id: str | None,
    baseline_run_id: str | None,
    summary: dict[str, Any],
    isolate_history: dict[str, Any],
    compare_history: dict[str, Any],
) -> tuple[str, dict[str, list[dict[str, Any]]], str]:
    measured = _measured_reason(summary)
    derived = _derived_reason(summary)
    isolate_history_reason = _history_reason(isolate_history, "isolate_hotspot")
    compare_history_reason = _history_reason(compare_history, "compare_runs")

    if _high_trace_overhead(summary):
        return (
            "trace_overhead",
            {"measured": measured, "derived": derived, "history": []},
            "high",
        )

    if int(isolate_history.get("history", {}).get("sample_count") or 0) == 0:
        return (
            "isolate_hotspot",
            {"measured": measured, "derived": derived, "history": isolate_history_reason},
            "high",
        )

    history_sample_count = max(
        int(isolate_history.get("history", {}).get("sample_count") or 0),
        int(compare_history.get("history", {}).get("sample_count") or 0),
    )
    history_confidence = _best_history_confidence(isolate_history, compare_history)
    if history_sample_count < 3 or history_confidence == "low":
        return (
            "rerun_repeatability",
            {"measured": measured, "derived": derived, "history": isolate_history_reason + compare_history_reason},
            "medium",
        )

    if baseline_run_id and int(compare_history.get("history", {}).get("sample_count") or 0) == 0:
        return (
            "compare_runs",
            {"measured": measured, "derived": derived, "history": compare_history_reason},
            "high",
        )

    if history_confidence in {"medium", "high"}:
        return (
            "inspect_file",
            {"measured": measured, "derived": derived, "history": isolate_history_reason},
            history_confidence,
        )

    return (
        "rerun_repeatability",
        {"measured": measured, "derived": derived, "history": isolate_history_reason + compare_history_reason},
        "low",
    )


def _measured_reason(summary: dict[str, Any]) -> list[dict[str, Any]]:
    measured = dict(summary.get("measured") or {})
    run = dict(summary.get("run") or {})
    return [
        {"key": "run_id", "value": run.get("run_id")},
        {"key": "trace_overhead_ms", "value": measured.get("trace_overhead_ms")},
    ]


def _derived_reason(summary: dict[str, Any]) -> list[dict[str, Any]]:
    comparison = dict(summary.get("comparison") or {})
    hotspots = list(summary.get("hotspots") or [])
    top = dict(hotspots[0]) if hotspots else {}
    return [
        {"key": "top_hotspot", "value": top.get("file_path")},
        {"key": "runtime_delta_ms", "value": comparison.get("runtime_delta_ms")},
    ]


def _history_reason(history_summary: dict[str, Any], experiment_name: str) -> list[dict[str, Any]]:
    history = dict(history_summary.get("history") or {})
    if not history:
        return [{"key": f"{experiment_name}_history", "value": "none"}]
    return [
        {"key": f"{experiment_name}_sample_count", "value": history.get("sample_count")},
        {"key": f"{experiment_name}_confidence", "value": history.get("confidence")},
    ]


def _high_trace_overhead(summary: dict[str, Any]) -> bool:
    measured = dict(summary.get("measured") or {})
    runtime_ms = _to_float(measured.get("runtime_ms"))
    trace_overhead_ms = _to_float(measured.get("trace_overhead_ms"))
    if runtime_ms in (None, 0.0) or trace_overhead_ms is None:
        return False
    return (trace_overhead_ms / runtime_ms) >= TRACE_OVERHEAD_RATIO_THRESHOLD


def _best_history_confidence(*history_summaries: dict[str, Any]) -> str:
    ranks = {"low": 0, "medium": 1, "high": 2}
    best = "low"
    for history_summary in history_summaries:
        confidence = str(history_summary.get("history", {}).get("confidence") or "low")
        if ranks.get(confidence, 0) > ranks.get(best, 0):
            best = confidence
    return best


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
