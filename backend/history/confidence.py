from __future__ import annotations

import math
from typing import Any


def summarize_confidence(records: list[dict[str, Any]]) -> dict[str, Any]:
    sample_count = len(records)
    experiment = str(records[0].get("experiment") or "") if records else ""
    target = str(records[0].get("target") or "") if records else ""
    gains = [_runtime_gain_pct(record) for record in records]
    valid_gains = [gain for gain in gains if gain is not None]
    mean_gain = sum(valid_gains) / len(valid_gains) if valid_gains else 0.0
    variance_value = _variance(valid_gains, mean_gain)
    improvement_rate = (
        sum(1 for record in records if str(record.get("result") or "") == "improved") / sample_count
        if sample_count
        else 0.0
    )
    confidence = _base_confidence(sample_count, improvement_rate)
    if _has_high_relative_variance(mean_gain, variance_value):
        confidence = _downgrade_confidence(confidence)

    return {
        "experiment": experiment,
        "target": target,
        "sample_count": sample_count,
        "mean_runtime_gain_pct": mean_gain,
        "variance": variance_value,
        "variance_level": _variance_level(mean_gain, variance_value),
        "improvement_rate": improvement_rate,
        "confidence": confidence,
    }


def _runtime_gain_pct(record: dict[str, Any]) -> float | None:
    derived = dict(record.get("derived") or {})
    runtime_delta_pct = derived.get("runtime_delta_pct")
    try:
        return -float(runtime_delta_pct)
    except (TypeError, ValueError):
        return None


def _variance(values: list[float], mean: float) -> float:
    if len(values) <= 1:
        return 0.0
    return sum((value - mean) ** 2 for value in values) / len(values)


def _base_confidence(sample_count: int, improvement_rate: float) -> str:
    if sample_count < 3:
        return "low"
    if sample_count <= 6:
        return "medium"
    if improvement_rate >= 0.7:
        return "high"
    return "medium"


def _has_high_relative_variance(mean_gain: float, variance_value: float) -> bool:
    if variance_value <= 0.0:
        return False
    std_dev = math.sqrt(variance_value)
    baseline = abs(mean_gain)
    if baseline <= 0.0:
        return std_dev > 5.0
    return std_dev > (baseline * 0.6)


def _variance_level(mean_gain: float, variance_value: float) -> str:
    if variance_value <= 0.0:
        return "low"
    if _has_high_relative_variance(mean_gain, variance_value):
        return "high"
    return "medium"


def _downgrade_confidence(confidence: str) -> str:
    if confidence == "high":
        return "medium"
    if confidence == "medium":
        return "low"
    return "low"
