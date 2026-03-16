from __future__ import annotations

from pathlib import Path

from backend.core.graph_engine.graph_manager import GraphManager
from backend.core.project_manager.project_loader import ProjectLoader
from backend.instrumentation.storage import InstrumentationStorage
from backend.scanner.python_parser.python_scanner import PythonRepoScanner
from .architecture_heuristics import build_architecture_snapshot, build_hypotheses
from .recommendations import build_recommendations
from .runtime_summary import summarize_runtime
from .static_summary import summarize_static_project


def generate_triage(
    project_root: Path,
    run_id: str | None = None,
    mode: str = "quick",
    storage: InstrumentationStorage | None = None,
    include_prefixes: list[str] | None = None,
) -> dict[str, object]:
    resolved_project_root = Path(project_root).expanduser().resolve()
    if not resolved_project_root.is_dir():
        raise ValueError(f"Project root does not exist: {resolved_project_root}")
    if mode not in {"quick", "full"}:
        raise ValueError("mode must be 'quick' or 'full'")

    graph_manager = GraphManager()
    project_loader = ProjectLoader(graph_manager, PythonRepoScanner)
    file_paths = project_loader.load_project(resolved_project_root, include_prefixes=include_prefixes)
    static_summary = summarize_static_project(
        resolved_project_root,
        file_paths,
        precomputed_file_records=project_loader.last_static_file_records,
    )

    runtime_storage = storage or InstrumentationStorage(
        resolved_project_root / ".bluebench" / "instrumentation.sqlite3"
    )
    runtime_storage.initialize_schema()
    runtime_summary = summarize_runtime(resolved_project_root, runtime_storage, run_id)
    architecture_snapshot = build_architecture_snapshot(
        resolved_project_root,
        graph_manager,
        static_summary,
        runtime_summary,
    )
    hypotheses = build_hypotheses(architecture_snapshot, runtime_summary)
    recommendations = build_recommendations(static_summary, runtime_summary, architecture_snapshot)

    dependencies = dict(static_summary.get("dependencies") or {})
    launch_assumptions = [
        str(item.get("detail") or item.get("title") or "")
        for item in static_summary.get("launch_assumptions", []) or []
        if isinstance(item, dict)
    ]
    triage = {
        "project": {
            **dict(static_summary.get("project") or {}),
            "entry_points": static_summary.get("project", {}).get("entry_points", []),
        },
        "runtime_context": {
            "selected_run": runtime_summary.get("selected_run"),
            "previous_comparable_run": runtime_summary.get("previous_comparable_run"),
            "quality_warnings": runtime_summary.get("quality_warnings", []),
        },
        "architecture": architecture_snapshot,
        "compute": {
            "hot_files": runtime_summary.get("hot_files", []),
            "hot_functions": runtime_summary.get("hot_functions", []),
            "external_pressure": runtime_summary.get("external_pressure", []),
            "failures": runtime_summary.get("failures", {}),
            "regressions": runtime_summary.get("regressions", []),
        },
        "operational_risks": {
            "native_dependencies": [item["name"] for item in dependencies.get("native_modules", [])],
            "optional_dependencies": [item["name"] for item in dependencies.get("optional_modules", [])],
            "native_risk_files": [item["path"] for item in dependencies.get("native_risk_files", [])],
            "launch_assumptions": launch_assumptions,
            "external_modules": [item["name"] for item in dependencies.get("external_modules", [])[:10]],
        },
        "hypotheses": hypotheses,
        "recommended_actions": recommendations,
        "evidence": {
            "static_sources": [str(resolved_project_root)],
            "runtime_sources": [str(runtime_summary["selected_run"]["run_id"])] if runtime_summary.get("selected_run") else [],
        },
        "mode": mode,
    }
    if mode == "quick":
        return triage
    triage["project"]["app_type_signals"] = static_summary.get("app_type_signals", [])
    triage["project"]["file_records"] = static_summary.get("file_records", [])
    triage["compute"]["performance_report"] = runtime_summary.get("performance_report")
    return triage
