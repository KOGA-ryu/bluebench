from __future__ import annotations

from typing import Any

from .evidence_labels import make_evidence_label
from .hotspot_ranker import rank_file_hotspots
from .run_comparator import compare_runs


def build_run_summary(
    run_evidence: dict[str, Any] | None,
    previous_evidence: dict[str, Any] | None = None,
    *,
    limit_hot_files: int = 10,
) -> dict[str, Any]:
    current = dict(run_evidence or {})
    previous = dict(previous_evidence or {})
    hotspots = rank_file_hotspots(current, limit=limit_hot_files)
    comparison = compare_runs(previous if previous else None, current if current else None)
    measured = dict(current.get("measured") or {})
    evidence_types = {
        "measured": [
            make_evidence_label("measured", "run_id", current.get("run_id")),
            make_evidence_label("measured", "runtime_ms", measured.get("runtime_ms")),
            make_evidence_label("measured", "trace_overhead_ms", measured.get("trace_overhead_ms")),
        ],
        "derived": [
            make_evidence_label("derived", "hotspot_count", len(hotspots)),
            make_evidence_label("derived", "runtime_delta_ms", comparison.get("runtime_delta_ms")),
        ],
        "inferred": [],
        "missing": [],
    }
    return {
        "run": {
            "run_id": current.get("run_id"),
            "run_name": current.get("run_name"),
            "quality": current.get("quality"),
            "status": current.get("status"),
        },
        "measured": measured,
        "hotspots": hotspots,
        "comparison": comparison,
        "summary_lines": _summary_lines(current, hotspots, comparison),
        "evidence_types": evidence_types,
    }


def _summary_lines(current: dict[str, Any], hotspots: list[dict[str, Any]], comparison: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if current.get("run_name"):
        lines.append(f"Run: {current['run_name']}")
    if hotspots:
        top = hotspots[0]
        lines.append(f"Top hotspot: {top['file_path']} ({float(top['raw_ms']):.2f} ms)")
    delta = comparison.get("runtime_delta_ms")
    if delta is not None:
        lines.append(f"Runtime delta: {float(delta):+.2f} ms")
    return lines
