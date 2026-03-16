from __future__ import annotations

import os
from pathlib import Path

try:
    from backend.core.graph_engine.graph_manager import GraphManager
except ModuleNotFoundError:
    from core.graph_engine.graph_manager import GraphManager


class ProjectLoader:
    def __init__(self, graph_manager: GraphManager, scanner_class: type) -> None:
        self.graph_manager = graph_manager
        self.scanner_class = scanner_class
        self.last_static_file_records: list[dict[str, object]] = []

    def load_project(self, project_path: str | Path, include_prefixes: list[str] | None = None) -> list[str]:
        project_path = Path(project_path)
        self.graph_manager.clear()
        normalized_prefixes = [Path(prefix).as_posix().strip("/") for prefix in (include_prefixes or []) if str(prefix).strip()]
        scanner = self.scanner_class(self.graph_manager, project_path, include_prefixes=normalized_prefixes)
        scanner.scan()
        self.last_static_file_records = scanner.static_file_records() if hasattr(scanner, "static_file_records") else []
        self.graph_manager.build_relationship_index()
        return self._list_python_files(project_path, normalized_prefixes)

    def _list_python_files(self, project_path: Path, include_prefixes: list[str] | None = None) -> list[str]:
        python_files: list[str] = []
        ignored_directories = {
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
            "venv",
        }

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [
                directory
                for directory in dirs
                if directory not in ignored_directories
            ]
            for file_name in files:
                if not file_name.endswith(".py"):
                    continue
                if file_name == "__init__.py":
                    continue

                file_path = Path(root) / file_name
                relative_path = file_path.relative_to(project_path).as_posix()
                if include_prefixes and not any(
                    relative_path == prefix or relative_path.startswith(f"{prefix}/") for prefix in include_prefixes
                ):
                    continue
                python_files.append(relative_path)

        return sorted(python_files)
