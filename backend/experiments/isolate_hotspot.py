from __future__ import annotations

from pathlib import Path

from backend.evidence.loaders.evidence_loader import load_run_evidence
from backend.derive.hotspot_ranker import rank_file_hotspots
from .base import ExperimentResult


def isolate_hotspot_experiment(
    project_root: Path,
    run_id: str,
    *,
    storage=None,
) -> ExperimentResult:
    evidence = load_run_evidence(run_id, project_root=project_root, storage=storage)
    hotspots = rank_file_hotspots(evidence, limit=1)
    return ExperimentResult(
        name="isolate_hotspot",
        evidence={"run": evidence},
        derived={
            "top_hotspot": hotspots[0] if hotspots else None,
            "note": "Placeholder isolation recipe; expand with variant runs later.",
        },
    )
