from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPERIMENT_LOG_SCHEMA_VERSION = "1"


def log_experiment_result(
    project_root: Path,
    experiment_payload: dict[str, Any],
    *,
    baseline_run_id: str | None = None,
    current_run_id: str | None = None,
) -> dict[str, Any]:
    record = build_experiment_record(
        experiment_payload,
        baseline_run_id=baseline_run_id,
        current_run_id=current_run_id,
    )
    log_path = _history_path(project_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def load_experiment_records(
    project_root: Path,
    *,
    target: str | None = None,
    experiment: str | None = None,
) -> list[dict[str, Any]]:
    log_path = _history_path(project_root)
    if not log_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if target and str(record.get("target") or "") != target:
            continue
        if experiment and str(record.get("experiment") or "") != experiment:
            continue
        records.append(record)
    return records


def build_experiment_record(
    experiment_payload: dict[str, Any],
    *,
    baseline_run_id: str | None = None,
    current_run_id: str | None = None,
) -> dict[str, Any]:
    experiment_name = str(experiment_payload.get("experiment") or "")
    result = dict(experiment_payload.get("result") or {})
    evidence = dict(result.get("evidence") or {})
    derived = dict(result.get("derived") or {})

    inferred_baseline_run_id = baseline_run_id or _extract_run_id(evidence.get("baseline"))
    inferred_current_run_id = current_run_id or _extract_run_id(evidence.get("current")) or _extract_run_id(evidence.get("run"))
    target = _target_for_experiment(experiment_name, derived)
    runtime_delta_ms = _to_float(derived.get("runtime_delta_ms"))
    trace_overhead_delta_ms = _to_float(derived.get("trace_overhead_delta_ms"))
    runtime_delta_pct = _runtime_delta_pct(evidence, runtime_delta_ms)

    return {
        "schema_version": EXPERIMENT_LOG_SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": experiment_name,
        "target": target,
        "baseline_run_id": inferred_baseline_run_id,
        "current_run_id": inferred_current_run_id,
        "measured": {
            "runtime_delta_ms": runtime_delta_ms,
            "trace_overhead_delta_ms": trace_overhead_delta_ms,
        },
        "derived": {
            "runtime_delta_pct": runtime_delta_pct,
        },
        "result": _result_label(runtime_delta_ms),
    }


def _history_path(project_root: Path) -> Path:
    return Path(project_root).resolve() / ".bluebench" / "experiment_history.jsonl"


def _extract_run_id(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    run_id = str(value.get("run_id") or "")
    return run_id or None


def _target_for_experiment(experiment_name: str, derived: dict[str, Any]) -> str:
    if experiment_name == "compare_runs":
        file_deltas = list(derived.get("file_deltas") or [])
        if file_deltas:
            return str(file_deltas[0].get("file_path") or "")
    if experiment_name == "isolate_hotspot":
        top_hotspot = dict(derived.get("top_hotspot") or {})
        return str(top_hotspot.get("file_path") or "")
    return ""


def _runtime_delta_pct(evidence: dict[str, Any], runtime_delta_ms: float | None) -> float | None:
    if runtime_delta_ms is None:
        return None
    baseline = dict(evidence.get("baseline") or {})
    baseline_measured = dict(baseline.get("measured") or {})
    baseline_runtime_ms = _to_float(baseline_measured.get("runtime_ms"))
    if baseline_runtime_ms in (None, 0.0):
        return None
    return (runtime_delta_ms / baseline_runtime_ms) * 100.0


def _result_label(runtime_delta_ms: float | None) -> str:
    if runtime_delta_ms is None:
        return "neutral"
    if runtime_delta_ms < 0.0:
        return "improved"
    if runtime_delta_ms > 0.0:
        return "regressed"
    return "neutral"


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
