from __future__ import annotations

from pathlib import Path
import unittest

from backend.core.graph_engine.graph_manager import GraphManager
from backend.triage.architecture_heuristics import build_architecture_snapshot, build_hypotheses


class TriageHeuristicsTests(unittest.TestCase):
    def test_architecture_snapshot_and_hypotheses_are_populated(self) -> None:
        manager = GraphManager()
        manager.clear()
        manager.add_node("repo", "repo", "subsystem")
        manager.add_node("app/main.py", "main", "module", parent="repo", file_path="app/main.py", line_number=1)
        manager.add_node("app/service.py", "service", "module", parent="repo", file_path="app/service.py", line_number=1)
        manager.add_node("core/worker.py", "worker", "module", parent="repo", file_path="core/worker.py", line_number=1)
        manager.add_node("app/main.py::main", "main", "function", parent="app/main.py", file_path="app/main.py", line_number=3)
        manager.add_node("app/service.py::load", "load", "function", parent="app/service.py", file_path="app/service.py", line_number=4)
        manager.add_node("core/worker.py::run", "run", "function", parent="core/worker.py", file_path="core/worker.py", line_number=5)
        manager.add_edge("app/main.py", "app/service.py", "imports")
        manager.add_edge("app/service.py", "core/worker.py", "imports")
        manager.add_edge("app/main.py::main", "app/service.py::load", "calls")
        manager.add_edge("app/service.py::load", "core/worker.py::run", "calls")
        manager.build_relationship_index()

        static_summary = {
            "project": {"top_level_areas": [{"name": "app", "file_count": 2}, {"name": "core", "file_count": 1}]},
            "file_records": [
                {"path": "app/main.py", "imports": ["PySide6.QtWidgets"], "framework_markers": ["qt"]},
                {"path": "app/service.py", "imports": ["requests", "sqlite3"], "framework_markers": []},
            ],
        }
        runtime_summary = {
            "hot_files": [
                {"file_path": "app/service.py", "normalized_compute_score": 88.0, "total_time_ms": 400.0},
                {"file_path": "core/worker.py", "normalized_compute_score": 55.0, "total_time_ms": 220.0},
            ],
            "quality_warnings": ["Only 2 files were seen during instrumentation."],
        }

        snapshot = build_architecture_snapshot(Path("/tmp/repo"), manager, static_summary, runtime_summary)
        hypotheses = build_hypotheses(snapshot, runtime_summary)

        self.assertTrue(snapshot["relationship_hotspots"])
        self.assertTrue(snapshot["suspected_subsystems"])
        self.assertTrue(hypotheses)


if __name__ == "__main__":
    unittest.main()
