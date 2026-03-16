from __future__ import annotations

import json
from pathlib import Path


def export_triage_json(triage: dict[str, object], target_path: Path) -> Path:
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(triage, indent=2, sort_keys=True), encoding="utf-8")
    return target_path


def export_triage_markdown(triage: dict[str, object], target_path: Path) -> Path:
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    project = dict(triage.get("project") or {})
    runtime_context = dict(triage.get("runtime_context") or {})
    architecture = dict(triage.get("architecture") or {})
    compute = dict(triage.get("compute") or {})
    operational_risks = dict(triage.get("operational_risks") or {})
    hypotheses = list(triage.get("hypotheses") or [])
    recommended_actions = list(triage.get("recommended_actions") or [])

    lines.append(f"# {project.get('name', 'Project')} Triage")
    lines.append("")
    lines.append("## Project Summary")
    lines.append(f"- Root: {project.get('root', '-')}")
    lines.append(f"- App Type Guess: {project.get('app_type_guess', '-')}")
    lines.append(f"- File Count: {project.get('file_count', 0)}")
    entry_points = list(project.get("entry_points") or [])
    if entry_points:
        lines.append("- Entry Points:")
        for item in entry_points[:5]:
            lines.append(f"  - {item.get('path', '-')} (score {item.get('score', 0)})")
    lines.append("")
    lines.append("## Runtime Context")
    selected_run = runtime_context.get("selected_run")
    if isinstance(selected_run, dict):
        lines.append(f"- Run: {selected_run.get('run_name', '-')}")
        lines.append(f"- Scenario: {selected_run.get('scenario_kind', '-')}")
        lines.append(f"- Hardware: {selected_run.get('hardware_profile', '-')}")
    else:
        lines.append("- Run: none")
    for warning in runtime_context.get("quality_warnings", []) or []:
        lines.append(f"- Warning: {warning}")
    lines.append("")
    lines.append("## Architecture Snapshot")
    for item in architecture.get("suspected_subsystems", []) or []:
        lines.append(f"- {item.get('name', '-')}: {item.get('role', '-')}")
    for note in architecture.get("coupling_notes", []) or []:
        lines.append(f"- Note: {note}")
    lines.append("")
    lines.append("## Measured Compute Summary")
    for item in compute.get("hot_files", []) or []:
        lines.append(
            f"- {item.get('file_path', '-')}: score {float(item.get('normalized_compute_score', 0.0)):.1f}, total {float(item.get('total_time_ms', 0.0)):.1f} ms"
        )
    lines.append("")
    lines.append("## Dependency and Environment Risks")
    for item in operational_risks.get("native_dependencies", []) or []:
        lines.append(f"- Native dependency: {item}")
    for item in operational_risks.get("launch_assumptions", []) or []:
        lines.append(f"- Launch assumption: {item}")
    lines.append("")
    lines.append("## Bottleneck Hypotheses")
    for item in hypotheses:
        lines.append(f"- {item.get('title', '-')}")
        lines.append(f"  - Confidence: {item.get('confidence', '-')}")
        lines.append(f"  - Reasoning: {item.get('reasoning', '-')}")
    lines.append("")
    lines.append("## Suggested First Actions")
    for item in recommended_actions:
        lines.append(f"- {item.get('priority', '-')}. {item.get('title', '-')}")
        lines.append(f"  - Confidence: {item.get('confidence', '-')}")
        lines.append(f"  - Reason: {item.get('reason', '-')}")
    target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target_path
