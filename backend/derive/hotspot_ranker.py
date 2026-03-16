from __future__ import annotations

from typing import Any


def rank_file_hotspots(run_evidence: dict[str, Any] | None, limit: int | None = 10) -> list[dict[str, Any]]:
    evidence = dict(run_evidence or {})
    rows = list(evidence.get("files") or [])
    ranked = sorted(
        [
            {
                "file_path": str(item.get("file_path") or ""),
                "raw_ms": float(item.get("raw_ms") or 0.0),
                "call_count": item.get("call_count"),
                "rolling_score": item.get("rolling_score"),
                "normalized_compute_score": item.get("normalized_compute_score"),
            }
            for item in rows
            if str(item.get("file_path") or "")
        ],
        key=lambda item: (-float(item["raw_ms"]), str(item["file_path"]).lower()),
    )
    return ranked if limit is None else ranked[:limit]
