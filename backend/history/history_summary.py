from __future__ import annotations

from pathlib import Path
from typing import Any

from .confidence import summarize_confidence
from .experiment_log import load_experiment_records


def summarize_experiment_history(
    project_root: Path,
    *,
    target: str,
    experiment: str | None = None,
) -> dict[str, Any]:
    if experiment:
        records = load_experiment_records(project_root, target=target, experiment=experiment)
        confidence = summarize_confidence(records)
        return {
            "target": target,
            "experiment": experiment,
            "history": _history_view(confidence),
        }

    records = load_experiment_records(project_root, target=target)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("experiment") or ""), []).append(record)
    summaries = []
    for experiment_name in sorted(grouped):
        confidence = summarize_confidence(grouped[experiment_name])
        summaries.append(
            {
                "target": target,
                "experiment": experiment_name,
                "history": _history_view(confidence),
            }
        )
    return {
        "target": target,
        "summaries": summaries,
    }


def _history_view(confidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_count": int(confidence.get("sample_count") or 0),
        "improvement_rate": float(confidence.get("improvement_rate") or 0.0),
        "mean_runtime_gain_pct": float(confidence.get("mean_runtime_gain_pct") or 0.0),
        "variance": str(confidence.get("variance_level") or "low"),
        "confidence": str(confidence.get("confidence") or "low"),
    }
