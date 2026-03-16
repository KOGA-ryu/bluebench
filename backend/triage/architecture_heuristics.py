from __future__ import annotations

from pathlib import Path

from backend.core.graph_engine.graph_manager import GraphManager
from .static_summary import _is_project_path


def build_architecture_snapshot(
    project_root: Path,
    graph_manager: GraphManager,
    static_summary: dict[str, object],
    runtime_summary: dict[str, object],
) -> dict[str, object]:
    top_level_areas = list(static_summary.get("project", {}).get("top_level_areas", []))
    coupling = _relationship_coupling(graph_manager)
    subsystem_candidates = _subsystem_candidates(top_level_areas, runtime_summary)
    hotspot_folders = _folder_hotspots(runtime_summary)
    mixed_concern_files = _mixed_concern_files(static_summary)

    return {
        "top_level_areas": top_level_areas,
        "suspected_subsystems": subsystem_candidates,
        "relationship_hotspots": coupling[:10],
        "folder_hotspots": hotspot_folders,
        "coupling_notes": _coupling_notes(coupling, mixed_concern_files),
        "mixed_concern_files": mixed_concern_files[:10],
        "project_root": str(project_root.resolve()),
    }


def build_hypotheses(
    architecture_snapshot: dict[str, object],
    runtime_summary: dict[str, object],
) -> list[dict[str, object]]:
    hypotheses: list[dict[str, object]] = []
    hot_files = list(runtime_summary.get("hot_files") or [])
    quality_warnings = list(runtime_summary.get("quality_warnings") or [])
    relationship_hotspots = list(architecture_snapshot.get("relationship_hotspots") or [])
    if hot_files:
        hottest = hot_files[0]
        hypotheses.append(
            {
                "title": "Compute is concentrated in a small set of files",
                "reasoning": f"{hottest['file_path']} leads the measured run with score {float(hottest['normalized_compute_score']):.1f}.",
                "confidence": "high",
                "evidence": [f"hot file {item['file_path']}" for item in hot_files[:3]],
            }
        )
    if relationship_hotspots:
        hotspot = relationship_hotspots[0]
        hypotheses.append(
            {
                "title": "Coupling is likely concentrated around a few files",
                "reasoning": f"{hotspot['file_path']} has high relationship fan-in/fan-out.",
                "confidence": "medium",
                "evidence": [f"{hotspot['file_path']} relationship score {hotspot['relationship_score']}"],
            }
        )
    if quality_warnings:
        hypotheses.append(
            {
                "title": "Run quality limits certainty of some conclusions",
                "reasoning": quality_warnings[0],
                "confidence": "medium",
                "evidence": quality_warnings[:3],
            }
        )
    if not hypotheses:
        hypotheses.append(
            {
                "title": "Static structure suggests a moderately modular codebase",
                "reasoning": "No strong runtime hotspot or coupling signal was available.",
                "confidence": "low",
                "evidence": ["static-only triage"],
            }
        )
    return hypotheses


def _relationship_coupling(graph_manager: GraphManager) -> list[dict[str, object]]:
    scores: list[dict[str, object]] = []
    file_paths = {
        str(node.get("file_path"))
        for node in graph_manager.nodes
        if isinstance(node.get("file_path"), str) and node.get("file_path") and _is_project_path(str(node.get("file_path")))
    }
    for file_path in sorted(file_paths):
        calls = len(graph_manager.get_file_calls(file_path))
        imports = len(graph_manager.get_file_imports(file_path))
        called_by = len(graph_manager.get_file_called_by(file_path))
        imported_by = len(graph_manager.get_file_imported_by(file_path))
        relationship_score = calls + imports + called_by + imported_by
        if relationship_score <= 0:
            continue
        scores.append(
            {
                "file_path": file_path,
                "calls": calls,
                "imports": imports,
                "called_by": called_by,
                "imported_by": imported_by,
                "relationship_score": relationship_score,
            }
        )
    return sorted(scores, key=lambda item: (-int(item["relationship_score"]), str(item["file_path"]).lower()))


def _subsystem_candidates(top_level_areas: list[dict[str, object]], runtime_summary: dict[str, object]) -> list[dict[str, object]]:
    hot_files = list(runtime_summary.get("hot_files") or [])
    hot_area_names = {Path(str(item["file_path"])).parts[0] for item in hot_files if Path(str(item["file_path"])).parts}
    results: list[dict[str, object]] = []
    for area in top_level_areas[:10]:
        name = str(area.get("name") or "")
        if not name:
            continue
        role = "hot_subsystem" if name in hot_area_names else "supporting_subsystem"
        results.append({"name": name, "role": role, "file_count": int(area.get("file_count") or 0)})
    return results


def _folder_hotspots(runtime_summary: dict[str, object]) -> list[dict[str, object]]:
    totals: dict[str, float] = {}
    for item in runtime_summary.get("hot_files", []):
        file_path = Path(str(item["file_path"]))
        folder = file_path.parts[0] if len(file_path.parts) > 1 else "(root)"
        totals[folder] = totals.get(folder, 0.0) + float(item.get("total_time_ms") or 0.0)
    return [
        {"name": name, "total_time_ms": total_time}
        for name, total_time in sorted(totals.items(), key=lambda entry: (-entry[1], entry[0].lower()))
    ]


def _mixed_concern_files(static_summary: dict[str, object]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for record in static_summary.get("file_records", []):
        imports = list(record.get("imports") or [])
        framework_markers = set(record.get("framework_markers") or [])
        touches_ui = "qt" in framework_markers
        touches_network = any(name.startswith(("requests", "httpx", "fastapi", "flask")) for name in imports)
        touches_data = any(name.startswith(("sqlite3", "sqlalchemy", "pandas", "numpy")) for name in imports)
        score = int(touches_ui) + int(touches_network) + int(touches_data)
        if score >= 2:
            results.append(
                {
                    "file_path": str(record["path"]),
                    "reason": "mixes multiple concern types",
                    "score": score,
                }
            )
    return sorted(results, key=lambda item: (-int(item["score"]), str(item["file_path"]).lower()))


def _coupling_notes(
    coupling: list[dict[str, object]],
    mixed_concern_files: list[dict[str, object]],
) -> list[str]:
    notes: list[str] = []
    if coupling:
        notes.append(
            f"{coupling[0]['file_path']} has the highest relationship load in the scanned graph."
        )
    if mixed_concern_files:
        notes.append(
            f"{mixed_concern_files[0]['file_path']} mixes multiple concern types and may be harder to change safely."
        )
    return notes
