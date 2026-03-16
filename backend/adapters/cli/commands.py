from __future__ import annotations

from pathlib import Path

from backend.derive.hotspot_ranker import rank_file_hotspots
from backend.derive.run_comparator import compare_runs
from backend.evidence.loaders.evidence_loader import load_run_evidence


def hotspot_summary_command(project_root: Path, run_id: str, *, storage=None) -> dict[str, object]:
    evidence = load_run_evidence(run_id, project_root=project_root, storage=storage)
    return {"run_id": run_id, "hotspots": rank_file_hotspots(evidence)}


def compare_run_command(project_root: Path, baseline_run_id: str, current_run_id: str, *, storage=None) -> dict[str, object]:
    baseline = load_run_evidence(baseline_run_id, project_root=project_root, storage=storage)
    current = load_run_evidence(current_run_id, project_root=project_root, storage=storage)
    return {
        "baseline_run_id": baseline_run_id,
        "current_run_id": current_run_id,
        "comparison": compare_runs(baseline, current),
    }
