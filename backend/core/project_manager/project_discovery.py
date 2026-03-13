from __future__ import annotations

from pathlib import Path


IGNORED_DIRECTORIES = {".git", "__pycache__", "node_modules"}


class ProjectDiscovery:
    def __init__(self, dev_root: str | Path = "~/dev") -> None:
        self.dev_root = Path(dev_root).expanduser().resolve()

    def discover_projects(self) -> list[str]:
        if not self.dev_root.exists():
            return []

        project_names: list[str] = []
        for entry in sorted(self.dev_root.iterdir(), key=lambda path: path.name.lower()):
            if not entry.is_dir():
                continue
            if entry.name in IGNORED_DIRECTORIES:
                continue
            project_names.append(entry.name)
        return project_names
