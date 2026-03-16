from __future__ import annotations

from pathlib import Path

from backend.evidence.loaders.evidence_loader import load_run_evidence
from backend.derive.run_comparator import compare_runs
from .base import ExperimentResult


def compare_runs_experiment(
    project_root: Path,
    baseline_run_id: str,
    current_run_id: str,
    *,
    storage=None,
) -> ExperimentResult:
    baseline = load_run_evidence(baseline_run_id, project_root=project_root, storage=storage)
    current = load_run_evidence(current_run_id, project_root=project_root, storage=storage)
    return ExperimentResult(
        name="compare_runs",
        evidence={"baseline": baseline, "current": current},
        derived=compare_runs(baseline, current),
    )
