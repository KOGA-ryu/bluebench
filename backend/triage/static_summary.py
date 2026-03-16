from __future__ import annotations

import ast
from pathlib import Path


ENTRYPOINT_HINTS = {
    "app/main.py": 100,
    "main.py": 90,
    "__main__.py": 95,
    "run.py": 70,
    "manage.py": 65,
    "server.py": 60,
}
NATIVE_IMPORT_PREFIXES = {
    "AVFoundation",
    "AppKit",
    "Cocoa",
    "CoreAudio",
    "CoreFoundation",
    "CoreGraphics",
    "Foundation",
    "PySide6",
    "PyQt5",
    "PyQt6",
    "cv2",
    "numpy",
    "pandas",
    "torch",
}
IGNORED_PATH_PARTS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "vendor",
}


def summarize_static_project(
    project_root: Path,
    file_paths: list[str],
    precomputed_file_records: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    root = project_root.resolve()
    normalized_files = sorted(
        Path(path).as_posix() for path in file_paths if _is_project_path(Path(path).as_posix())
    )
    python_files = [path for path in normalized_files if path.endswith(".py")]
    languages = _language_summary(normalized_files)
    top_level_areas = _top_level_areas(normalized_files)
    if precomputed_file_records is not None:
        file_records = [
            dict(record)
            for record in precomputed_file_records
            if _is_project_path(str(record.get("path") or "")) and str(record.get("path") or "").endswith(".py")
        ]
    else:
        file_records = [_analyze_file(root, relative_path) for relative_path in python_files]
    entry_points = _detect_entry_points(file_records)
    app_type = _guess_app_type(file_records)
    dependencies = _dependency_surface(file_records)

    return {
        "project": {
            "name": root.name,
            "root": str(root),
            "languages": languages,
            "file_count": len(normalized_files),
            "python_file_count": len(python_files),
            "top_level_areas": top_level_areas,
            "entry_points": entry_points,
            "app_type_guess": app_type["label"],
        },
        "dependencies": dependencies,
        "launch_assumptions": _launch_assumptions(entry_points, dependencies),
        "file_records": file_records,
        "app_type_signals": app_type["signals"],
    }


def _is_project_path(relative_path: str) -> bool:
    path = Path(relative_path)
    parts = path.parts
    if not parts:
        return False
    if any(part in IGNORED_PATH_PARTS for part in parts):
        return False
    if any(part.startswith(".") and part not in {".github"} for part in parts[:-1]):
        return False
    return True


def _language_summary(file_paths: list[str]) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    labels = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".json": "JSON",
        ".md": "Markdown",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".toml": "TOML",
        ".ini": "INI",
        ".c": "C",
        ".cc": "C++",
        ".cpp": "C++",
        ".h": "C/C++ Header",
        ".hpp": "C/C++ Header",
        ".cs": "C#",
        ".swift": "Swift",
    }
    for file_path in file_paths:
        suffix = Path(file_path).suffix.lower()
        label = labels.get(suffix, suffix or "no_extension")
        counts[label] = counts.get(label, 0) + 1
    return [
        {"language": language, "count": count}
        for language, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]


def _top_level_areas(file_paths: list[str]) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for file_path in file_paths:
        parts = Path(file_path).parts
        key = parts[0] if len(parts) > 1 else "(root)"
        counts[key] = counts.get(key, 0) + 1
    return [
        {"name": name, "file_count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]


def _analyze_file(project_root: Path, relative_path: str) -> dict[str, object]:
    source_path = project_root / relative_path
    source = ""
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError:
        pass

    imports: list[str] = []
    has_main_guard = False
    callable_count = 0
    class_count = 0
    framework_markers: set[str] = set()
    optional_imports: set[str] = set()
    native_imports: set[str] = set()
    if source:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                        top_level = alias.name.split(".", 1)[0]
                        if top_level in NATIVE_IMPORT_PREFIXES:
                            native_imports.add(top_level)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                        top_level = node.module.split(".", 1)[0]
                        if top_level in NATIVE_IMPORT_PREFIXES:
                            native_imports.add(top_level)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    callable_count += 1
                elif isinstance(node, ast.ClassDef):
                    class_count += 1
                elif isinstance(node, ast.Try):
                    for guarded in node.body:
                        if isinstance(guarded, ast.Import):
                            for alias in guarded.names:
                                optional_imports.add(alias.name.split(".", 1)[0])
                        elif isinstance(guarded, ast.ImportFrom) and guarded.module:
                            optional_imports.add(guarded.module.split(".", 1)[0])
            has_main_guard = "__name__ == \"__main__\"" in source or "__name__ == '__main__'" in source
            lowered = source.lower()
            if "qapplication(" in lowered or "pyside6" in lowered or "pyqt" in lowered:
                framework_markers.add("qt")
            if "fastapi(" in lowered or "from fastapi" in lowered:
                framework_markers.add("fastapi")
            if "flask(" in lowered or "from flask" in lowered:
                framework_markers.add("flask")
            if "argparse" in lowered or "click.command" in lowered or "typer.typer" in lowered:
                framework_markers.add("cli")

    return {
        "path": relative_path,
        "imports": sorted(set(imports)),
        "has_main_guard": has_main_guard,
        "callable_count": callable_count,
        "class_count": class_count,
        "framework_markers": sorted(framework_markers),
        "optional_imports": sorted(optional_imports),
        "native_imports": sorted(native_imports),
    }


def _detect_entry_points(file_records: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for record in file_records:
        path = str(record["path"])
        score = 0
        reasons: list[str] = []
        for hint, hint_score in ENTRYPOINT_HINTS.items():
            if path.endswith(hint):
                score += hint_score
                reasons.append(f"path matches {hint}")
        if record.get("has_main_guard"):
            score += 50
            reasons.append("contains __main__ guard")
        framework_markers = list(record.get("framework_markers") or [])
        if "qt" in framework_markers:
            score += 25
            reasons.append("imports Qt framework")
        if "fastapi" in framework_markers or "flask" in framework_markers:
            score += 20
            reasons.append("looks like server entry")
        if "cli" in framework_markers:
            score += 15
            reasons.append("contains CLI framework markers")
        if score <= 0:
            continue
        candidates.append(
            {
                "path": path,
                "score": score,
                "reasons": reasons,
            }
        )
    return sorted(candidates, key=lambda item: (-int(item["score"]), str(item["path"]).lower()))


def _guess_app_type(file_records: list[dict[str, object]]) -> dict[str, object]:
    scores = {"desktop": 0, "server": 0, "cli": 0, "library": 0}
    signals: list[str] = []
    for record in file_records:
        markers = set(record.get("framework_markers") or [])
        imports = set(record.get("imports") or [])
        if "qt" in markers:
            scores["desktop"] += 3
            signals.append(f"{record['path']} imports Qt")
        if "fastapi" in markers or "flask" in markers:
            scores["server"] += 3
            signals.append(f"{record['path']} contains web framework markers")
        if "cli" in markers:
            scores["cli"] += 2
            signals.append(f"{record['path']} contains CLI markers")
        if any(name.startswith("PySide6") or name.startswith("PyQt") for name in imports):
            scores["desktop"] += 2
        if any(name.startswith("fastapi") or name.startswith("flask") or name.startswith("django") for name in imports):
            scores["server"] += 2
        if record.get("has_main_guard"):
            scores["cli"] += 1
    if max(scores.values(), default=0) == 0:
        return {"label": "library_or_mixed", "signals": signals}
    label = max(scores.items(), key=lambda item: item[1])[0]
    return {"label": label, "signals": signals[:10]}


def _dependency_surface(file_records: list[dict[str, object]]) -> dict[str, object]:
    external_counts: dict[str, int] = {}
    native_imports: dict[str, int] = {}
    optional_imports: dict[str, int] = {}
    native_risk_files: list[dict[str, object]] = []
    for record in file_records:
        file_native_imports = [name for name in record.get("native_imports", []) if isinstance(name, str)]
        if file_native_imports:
            native_risk_files.append(
                {
                    "path": str(record["path"]),
                    "native_imports": sorted(file_native_imports),
                }
            )
        for optional_name in record.get("optional_imports", []):
            if not isinstance(optional_name, str) or not optional_name:
                continue
            optional_imports[optional_name] = optional_imports.get(optional_name, 0) + 1
        for import_name in record.get("imports", []):
            if not isinstance(import_name, str) or not import_name:
                continue
            top_level = import_name.split(".", 1)[0]
            if top_level in NATIVE_IMPORT_PREFIXES:
                native_imports[top_level] = native_imports.get(top_level, 0) + 1
            elif not _looks_internal_import(top_level):
                external_counts[top_level] = external_counts.get(top_level, 0) + 1
    external_modules = [
        {"name": name, "count": count}
        for name, count in sorted(external_counts.items(), key=lambda item: (-item[1], item[0].lower()))[:20]
    ]
    native_modules = [
        {"name": name, "count": count}
        for name, count in sorted(native_imports.items(), key=lambda item: (-item[1], item[0].lower()))
    ]
    optional_modules = [
        {"name": name, "count": count}
        for name, count in sorted(optional_imports.items(), key=lambda item: (-item[1], item[0].lower()))
    ]
    return {
        "external_modules": external_modules,
        "native_modules": native_modules,
        "optional_modules": optional_modules,
        "native_risk_files": native_risk_files,
    }


def _launch_assumptions(
    entry_points: list[dict[str, object]],
    dependencies: dict[str, object],
) -> list[dict[str, object]]:
    assumptions: list[dict[str, object]] = []
    if entry_points:
        assumptions.append(
            {
                "title": "single_entry_candidate",
                "detail": f"Top launch candidate is {entry_points[0]['path']}",
            }
        )
    native_modules = list(dependencies.get("native_modules") or [])
    if native_modules:
        assumptions.append(
            {
                "title": "native_runtime_dependencies",
                "detail": "Project imports native or platform-specific modules at import time",
            }
        )
    optional_modules = list(dependencies.get("optional_modules") or [])
    if optional_modules:
        assumptions.append(
            {
                "title": "optional_dependency_paths",
                "detail": "Project uses guarded or optional imports that may change behavior across environments",
            }
        )
    return assumptions


def _looks_internal_import(top_level: str) -> bool:
    return top_level in {
        "app",
        "backend",
        "frontend",
        "core",
        "tests",
        "utils",
        "models",
        "scanner",
        "api",
    }
