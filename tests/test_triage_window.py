from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.instrumentation.storage import InstrumentationStorage

try:
    from backend.triage_window import TriageWindow
except ModuleNotFoundError:
    TriageWindow = None


class TriageWindowTests(unittest.TestCase):
    def test_refresh_run_selector_scopes_runs_to_project(self) -> None:
        if TriageWindow is None:
            self.skipTest("PySide6 not available in test environment")

        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = InstrumentationStorage(Path(tmp_dir) / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-1",
                    "run_name": "project_one",
                    "project_root": "/tmp/project-one",
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.insert_run(
                {
                    "run_id": "run-2",
                    "run_name": "project_two",
                    "project_root": "/tmp/project-two",
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:01:00+00:00",
                    "status": "completed",
                }
            )
            window = TriageWindow(lambda: Path("/tmp/project-one"), storage)
            try:
                window._refresh_project_context()
                labels = [window.run_selector.itemText(index) for index in range(window.run_selector.count())]
            finally:
                window.close()

        self.assertEqual(len(labels), 2)
        self.assertTrue(any("project_one" in label for label in labels))
        self.assertFalse(any("project_two" in label for label in labels))

    def test_action_buttons_enable_when_triage_has_targets(self) -> None:
        if TriageWindow is None:
            self.skipTest("PySide6 not available in test environment")

        calls: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = InstrumentationStorage(Path(tmp_dir) / "instrumentation.sqlite3")
            storage.initialize_schema()
            window = TriageWindow(lambda: Path("/tmp/project-one"), storage, lambda payload: calls.append(payload))
            try:
                window.current_triage = {
                    "project": {"entry_points": [{"path": "app/main.py"}]},
                    "compute": {
                        "hot_files": [{"file_path": "app/service.py"}],
                        "regressions": [{"file_path": "app/service.py", "score_delta": 12.0}],
                    },
                }
                window._update_action_buttons()
                self.assertTrue(window.open_hot_file_button.isEnabled())
                self.assertTrue(window.open_regression_button.isEnabled())
                self.assertTrue(window.open_entry_button.isEnabled())
                window._open_top_hot_file()
            finally:
                window.close()

        self.assertEqual(calls[0]["file_path"], "app/service.py")
        self.assertEqual(calls[0]["preferred_tab"], "Compute")


if __name__ == "__main__":
    unittest.main()
