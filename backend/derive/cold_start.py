from __future__ import annotations

from pathlib import Path


ENTRY_POINT_NAMES = ("main.py", "app.py", "cli.py", "__main__.py")
PRIORITY_SUBSYSTEMS = ("engine", "core", "profiles", "scripts", "bin", "tests", "app", "src")
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}


def derive_cold_start(repo_root: Path) -> dict[str, object]:
    root = repo_root.expanduser().resolve()
    top_level_dirs = sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and entry.name not in IGNORED_DIRECTORIES and not entry.name.startswith(".")
    )
    top_level_files = sorted(entry.name for entry in root.iterdir() if entry.is_file() and not entry.name.startswith("."))

    entry_points = _detect_entry_points(root, top_level_dirs, top_level_files)
    primary_subsystems = _detect_primary_subsystems(top_level_dirs)
    project_type = _estimate_project_type(top_level_dirs, top_level_files)
    first_review_targets = _build_first_review_targets(entry_points, primary_subsystems)
    confidence = _derive_confidence(entry_points, primary_subsystems, first_review_targets)
    recommended_next_actions = _build_recommended_next_actions(first_review_targets, primary_subsystems)

    return {
        "project_type": project_type,
        "entry_points": entry_points,
        "primary_subsystems": primary_subsystems,
        "first_review_targets": first_review_targets,
        "recommended_next_actions": recommended_next_actions,
        "confidence": confidence,
    }


def _estimate_project_type(top_level_dirs: list[str], top_level_files: list[str]) -> str:
    if {"engine", "core", "profiles"}.issubset(set(top_level_dirs)):
        return "python_tool"
    if "pyproject.toml" in top_level_files and any(name in top_level_dirs for name in ("app", "src")):
        return "python_application"
    if "pyproject.toml" in top_level_files or "requirements.txt" in top_level_files:
        return "python_project"
    return "repo"


def _detect_entry_points(repo_root: Path, top_level_dirs: list[str], top_level_files: list[str]) -> list[str]:
    entry_points: list[str] = []
    for name in ENTRY_POINT_NAMES:
        if name in top_level_files:
            entry_points.append(name)

    for directory in ("engine", "core", "scripts", "bin", "app", "src"):
        if directory not in top_level_dirs:
            continue
        directory_path = repo_root / directory
        for candidate in sorted(directory_path.glob("*.py")):
            if candidate.name in ENTRY_POINT_NAMES or candidate.name.endswith("_engine.py"):
                entry_points.append(candidate.relative_to(repo_root).as_posix())

    deduped: list[str] = []
    seen: set[str] = set()
    for path in entry_points:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped[:5]


def _detect_primary_subsystems(top_level_dirs: list[str]) -> list[str]:
    subsystems: list[str] = []
    for name in PRIORITY_SUBSYSTEMS:
        if name in top_level_dirs:
            subsystems.append(name)
    for name in top_level_dirs:
        if name not in subsystems:
            subsystems.append(name)
    return subsystems[:5]


def _build_first_review_targets(entry_points: list[str], primary_subsystems: list[str]) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    subsystem_set = set(primary_subsystems)
    for entry in entry_points:
        reasons: list[str] = []
        if "/" not in entry:
            reasons.append("root entry file")
        if entry.endswith("_engine.py") or entry.startswith("engine/"):
            reasons.append("likely control path")
        if "/" in entry and entry.split("/", 1)[0] in subsystem_set and len(primary_subsystems) >= 2:
            reasons.append("touches multiple subsystems")
        confidence = "high" if "likely control path" in reasons else "medium"
        targets.append({"path": entry, "reason": reasons or ["likely entry point"], "confidence": confidence})

    targets.sort(key=lambda item: (_target_priority(item), str(item["path"])))
    return targets[:3]


def _target_priority(target: dict[str, object]) -> tuple[int, int]:
    reasons = list(target.get("reason", []))
    control = 0 if "likely control path" in reasons else 1
    junction = 0 if "touches multiple subsystems" in reasons else 1
    root_entry = 0 if "root entry file" in reasons else 1
    return (control, junction, root_entry)


def _derive_confidence(
    entry_points: list[str], primary_subsystems: list[str], first_review_targets: list[dict[str, object]]
) -> str:
    if entry_points and len(primary_subsystems) >= 2 and first_review_targets:
        return "high"
    if entry_points or primary_subsystems:
        return "medium"
    return "low"


def _build_recommended_next_actions(
    first_review_targets: list[dict[str, object]], primary_subsystems: list[str]
) -> list[str]:
    actions = ["run BlueBench hotspot probe"]
    if first_review_targets:
        actions.append(f"inspect {first_review_targets[0]['path']} first")
    if "tests" in primary_subsystems:
        actions.append("check tests before deeper runtime investigation")
    return actions[:3]
