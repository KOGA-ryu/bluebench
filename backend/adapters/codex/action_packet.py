from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.derive.hotspot_ranker import rank_file_hotspots
from backend.derive.summary_builder import build_run_summary
from backend.evidence.loaders.evidence_loader import load_run_evidence
from backend.evidence.loaders.run_loader import load_previous_comparable_run
from backend.instrumentation.storage import InstrumentationStorage


ACTION_PACKET_SCHEMA_VERSION = "1"


def generate_action_packet(
    run_id: str,
    *,
    project_root: Path | None = None,
    storage: InstrumentationStorage | None = None,
) -> dict[str, Any]:
    project_root = (project_root or Path.cwd()).resolve()
    runtime_storage = storage or InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
    runtime_storage.initialize_schema()

    current_evidence = load_run_evidence(run_id, project_root=project_root, storage=runtime_storage)
    if current_evidence is None:
        raise ValueError(f"Run evidence not found for run_id={run_id}")
    baseline_evidence = load_previous_comparable_run(run_id, project_root=project_root, storage=runtime_storage)
    summary = build_run_summary(current_evidence, baseline_evidence, limit_hot_files=10)
    hotspots = rank_file_hotspots(current_evidence, limit=1)
    primary_hotspot = dict(hotspots[0]) if hotspots else {}
    primary_target_path = str(primary_hotspot.get("file_path") or "")

    supporting_evidence = _supporting_evidence(summary, primary_hotspot)
    baseline_run_id = str((baseline_evidence or {}).get("run_id") or "") or None

    return {
        # Action Packet Schema (v1)
        # {
        #   "schema_version": "1",
        #   "packet_type": "hotspot_investigation",
        #   "run_id": "...",
        #   "baseline_run_id": "...",
        #   "primary_target": {"type": "file", "path": "..."},
        #   "supporting_evidence": {"measured": [...], "derived": [...], "inferred": [...]},
        #   "recommended_actions": [...],
        #   "constraints": [...]
        # }
        "schema_version": ACTION_PACKET_SCHEMA_VERSION,
        "packet_type": "hotspot_investigation",
        "run_id": str(current_evidence.get("run_id") or run_id),
        "baseline_run_id": baseline_run_id,
        "primary_target": {
            "type": "file",
            "path": primary_target_path,
        },
        "supporting_evidence": supporting_evidence,
        "recommended_actions": _recommended_actions(primary_target_path),
        "constraints": [
            "do_not_claim_cause_without_experiment",
            "prefer_minimal_changes",
            "verify_with_compare_runs",
        ],
    }


def _supporting_evidence(summary: dict[str, Any], primary_hotspot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    evidence_types = dict(summary.get("evidence_types") or {})
    measured = list(evidence_types.get("measured") or [])
    derived = list(evidence_types.get("derived") or [])
    inferred = list(evidence_types.get("inferred") or [])

    if primary_hotspot:
        measured.extend(
            [
                {"type": "measured", "key": "primary_target_path", "value": primary_hotspot.get("file_path")},
                {"type": "measured", "key": "primary_target_raw_ms", "value": primary_hotspot.get("raw_ms")},
                {"type": "measured", "key": "primary_target_call_count", "value": primary_hotspot.get("call_count")},
            ]
        )
        derived.extend(
            [
                {
                    "type": "derived",
                    "key": "primary_target_normalized_compute_score",
                    "value": primary_hotspot.get("normalized_compute_score"),
                },
                {
                    "type": "derived",
                    "key": "primary_target_rolling_score",
                    "value": primary_hotspot.get("rolling_score"),
                },
            ]
        )
    return {
        "measured": measured,
        "derived": derived,
        "inferred": inferred,
    }


def _recommended_actions(primary_target_path: str) -> list[dict[str, str]]:
    target = primary_target_path or ""
    return [
        {
            "action": "inspect_file",
            "target": target,
            "confidence": "high",
        },
        {
            "action": "run_experiment",
            "experiment": "isolate_hotspot",
            "target": target,
            "confidence": "high",
        },
    ]
