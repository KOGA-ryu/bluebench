from __future__ import annotations

import json
from pathlib import Path


def export_context_json(context_pack: dict[str, object], target_path: Path) -> Path:
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(context_pack, indent=2, sort_keys=True), encoding="utf-8")
    return target_path


def export_context_markdown(context_pack: dict[str, object], target_path: Path) -> Path:
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    project = dict(context_pack.get("project") or {})
    session = dict(context_pack.get("session") or {})
    runtime = dict(context_pack.get("runtime") or {})
    compute = dict(context_pack.get("compute") or {})
    risks = list(context_pack.get("risks") or [])
    actions = list(context_pack.get("actions") or [])
    hypotheses = list(context_pack.get("hypotheses") or [])
    lines = [
        f"# {project.get('name', 'Project')} Context Pack",
        "",
        "## Session",
        f"- Selected Run: {session.get('selected_run_id') or 'none'}",
        f"- Display Run: {session.get('display_run_id') or 'none'}",
        f"- View Mode: {session.get('run_view_mode', '-')}",
        "",
        "## Project",
        f"- Root: {project.get('root', '-')}",
        f"- App Type Guess: {project.get('app_type_guess', '-')}",
        "Entry Points:",
    ]
    entry_points = list(project.get("entry_points") or [])
    lines.extend(
        [f"- {item.get('path', '-')} (score {int(item.get('score', 0))})" for item in entry_points]
        or ["- none"]
    )
    lines.extend(["", "## Runtime"])
    selected_run = runtime.get("selected_run")
    if isinstance(selected_run, dict):
        lines.append(
            f"- {selected_run.get('run_name', '-')} · {selected_run.get('scenario_kind', '-')} · {selected_run.get('hardware_profile', '-')}"
        )
    else:
        lines.append("- none")
    lines.extend(["Quality Warnings:"])
    lines.extend([f"- {item}" for item in runtime.get("quality_warnings", []) or []] or ["- none"])
    lines.extend(["", "## Compute", "Hot Files:"])
    lines.extend(
        [
            f"- {item.get('file_path', '-')} · score {float(item.get('normalized_compute_score', 0.0)):.1f}"
            for item in compute.get("hot_files", []) or []
        ]
        or ["- none"]
    )
    lines.extend(["Hot Functions:"])
    lines.extend(
        [
            f"- {item.get('display_name', '-')} · {item.get('file_path', '-')} · {float(item.get('total_time_ms', 0.0)):.1f} ms"
            for item in compute.get("hot_functions", []) or []
        ]
        or ["- none"]
    )
    lines.extend(["", "## Risks"])
    lines.extend([f"- {item.get('label', '-')}" for item in risks] or ["- none"])
    lines.extend(["", "## Hypotheses"])
    lines.extend([f"- {item.get('title', '-')} [{item.get('confidence', '-')}] " for item in hypotheses] or ["- none"])
    lines.extend(["", "## Actions"])
    lines.extend([f"- {item.get('title', '-')} [{item.get('confidence', '-')}] " for item in actions] or ["- none"])
    target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target_path
