from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.core.graph_engine.graph_manager import GraphManager
from backend.core.project_manager.project_loader import ProjectLoader
from backend.scanner.python_parser.python_scanner import PythonRepoScanner


class ProjectLoaderTests(unittest.TestCase):
    def test_loader_excludes_venv_and_site_packages_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            (project_root / "app").mkdir(parents=True, exist_ok=True)
            (project_root / ".venv" / "lib" / "python3.14" / "site-packages" / "pkg").mkdir(parents=True, exist_ok=True)
            (project_root / "app" / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            (project_root / ".venv" / "lib" / "python3.14" / "site-packages" / "pkg" / "noise.py").write_text(
                "def noise():\n    return 2\n",
                encoding="utf-8",
            )

            manager = GraphManager()
            loader = ProjectLoader(manager, PythonRepoScanner)
            file_paths = loader.load_project(project_root)

        self.assertEqual(file_paths, ["app/main.py"])
        self.assertTrue(manager.has_node("app/main.py"))
        self.assertFalse(manager.has_node(".venv/lib/python3.14/site-packages/pkg/noise.py"))

    def test_loader_can_bound_scan_to_include_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            (project_root / "backend" / "triage").mkdir(parents=True, exist_ok=True)
            (project_root / "frontend").mkdir(parents=True, exist_ok=True)
            (project_root / "backend" / "triage" / "service.py").write_text("def run():\n    return 1\n", encoding="utf-8")
            (project_root / "frontend" / "view.py").write_text("def render():\n    return 2\n", encoding="utf-8")

            manager = GraphManager()
            loader = ProjectLoader(manager, PythonRepoScanner)
            file_paths = loader.load_project(project_root, include_prefixes=["backend/triage"])

        self.assertEqual(file_paths, ["backend/triage/service.py"])
        self.assertTrue(manager.has_node("backend/triage/service.py"))
        self.assertFalse(manager.has_node("frontend/view.py"))


if __name__ == "__main__":
    unittest.main()
