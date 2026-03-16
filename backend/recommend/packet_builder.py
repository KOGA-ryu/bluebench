from __future__ import annotations

from typing import Any


RECOMMEND_PACKET_SCHEMA_VERSION = "1"


def build_next_experiment_packet(
    *,
    target: str,
    run_id: str | None,
    baseline_run_id: str | None,
    recommended_experiment: str,
    reason: dict[str, list[dict[str, Any]]],
    confidence: str,
) -> dict[str, Any]:
    return {
        "schema_version": RECOMMEND_PACKET_SCHEMA_VERSION,
        "packet_type": "next_experiment",
        "target": target,
        "run_id": run_id,
        "recommended_experiment": recommended_experiment,
        "reason": reason,
        "constraints": [
            "use_canonical_evidence_only",
            "do_not_claim_cause_without_experiment",
            "prefer_minimal_changes",
            "verify_with_compare_runs",
        ],
        "confidence": confidence,
    }
