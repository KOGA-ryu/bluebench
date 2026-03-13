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

    def load_project(self, project_path: str | Path) -> list[str]:
        project_path = Path(project_path)
        self.graph_manager.clear()
        scanner = self.scanner_class(self.graph_manager, project_path)
        scanner.scan()
        return self._list_python_files(project_path)

    def _list_python_files(self, project_path: Path) -> list[str]:
        python_files: list[str] = []

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [
                directory
                for directory in dirs
                if directory not in {".venv", "__pycache__", ".git", "node_modules"}
            ]
            for file_name in files:
                if not file_name.endswith(".py"):
                    continue
                if file_name == "__init__.py":
                    continue

                file_path = Path(root) / file_name
                python_files.append(file_path.relative_to(project_path).as_posix())

        return sorted(python_files)
