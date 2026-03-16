from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.context import default_session_path, load_session_state, save_session_state


class ContextSessionStateTests(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sample_app"
            project_root.mkdir(parents=True, exist_ok=True)
            state = {
                "project_root": str(project_root),
                "selected_run_id": "run-123",
                "display_run_id": "run-122",
                "run_view_mode": "previous",
                "open_files": ["app/main.py"],
                "focus_targets": [{"file_path": "app/main.py", "reason": "entry_point"}],
            }
            session_path = save_session_state(project_root, state)
            loaded = load_session_state(project_root)

        self.assertEqual(session_path, default_session_path(project_root))
        self.assertEqual(loaded["selected_run_id"], "run-123")
        self.assertEqual(loaded["run_view_mode"], "previous")
        self.assertEqual(loaded["open_files"][0], "app/main.py")

    def test_load_missing_or_invalid_file_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sample_app"
            project_root.mkdir(parents=True, exist_ok=True)
            self.assertEqual(load_session_state(project_root), {})
            session_path = default_session_path(project_root)
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text("{not-valid-json", encoding="utf-8")
            self.assertEqual(load_session_state(project_root), {})


if __name__ == "__main__":
    unittest.main()
