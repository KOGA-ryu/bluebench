from __future__ import annotations

from typing import Any

from backend.derive.summary_builder import build_run_summary


def build_run_report(
    current_evidence: dict[str, Any] | None,
    previous_evidence: dict[str, Any] | None = None,
    *,
    title: str = "Run Report",
) -> dict[str, Any]:
    summary = build_run_summary(current_evidence, previous_evidence)
    return {
        "title": title,
        "run": summary.get("run"),
        "measured": summary.get("measured"),
        "hotspots": summary.get("hotspots"),
        "comparison": summary.get("comparison"),
        "summary_lines": summary.get("summary_lines"),
        "evidence_types": summary.get("evidence_types"),
    }
