from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.derive.summary_builder import build_run_summary
from backend.evidence.loaders.evidence_loader import load_run_evidence
from backend.evidence.loaders.run_loader import load_previous_comparable_run
from backend.history.history_summary import summarize_experiment_history
from backend.instrumentation.storage import InstrumentationStorage

from .packet_builder import build_next_experiment_packet
from .rules import choose_next_experiment


def recommend_next_experiment(
    target: str,
    run_id: str | None = None,
    baseline_run_id: str | None = None,
    *,
    project_root: Path | None = None,
    storage: InstrumentationStorage | None = None,
) -> dict[str, Any]:
    project_root = (project_root or Path.cwd()).resolve()
    runtime_storage = storage or InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
    runtime_storage.initialize_schema()

    current_evidence = (
        load_run_evidence(run_id, project_root=project_root, storage=runtime_storage)
        if run_id
        else None
    )
    baseline_evidence = None
    if baseline_run_id:
        baseline_evidence = load_run_evidence(baseline_run_id, project_root=project_root, storage=runtime_storage)
    elif run_id:
        baseline_evidence = load_previous_comparable_run(run_id, project_root=project_root, storage=runtime_storage)
        baseline_run_id = str((baseline_evidence or {}).get("run_id") or "") or None

    summary = build_run_summary(current_evidence, baseline_evidence, limit_hot_files=10)
    effective_target = target or _top_target(summary)
    isolate_history = summarize_experiment_history(project_root, target=effective_target, experiment="isolate_hotspot")
    compare_history = summarize_experiment_history(project_root, target=effective_target, experiment="compare_runs")
    recommended_experiment, reason, confidence = choose_next_experiment(
        target=effective_target,
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        summary=summary,
        isolate_history=isolate_history,
        compare_history=compare_history,
    )

    return build_next_experiment_packet(
        target=effective_target,
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        recommended_experiment=recommended_experiment,
        reason=reason,
        confidence=confidence,
    )


def _top_target(summary: dict[str, Any]) -> str:
    hotspots = list(summary.get("hotspots") or [])
    if not hotspots:
        return ""
    return str(hotspots[0].get("file_path") or "")
