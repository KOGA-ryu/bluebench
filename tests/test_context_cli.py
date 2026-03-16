from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from backend.context.cli import main
from backend.context.session_state import save_session_state
from backend.instrumentation.storage import InstrumentationStorage


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "triage" / "sample_app"


class ContextCliTests(unittest.TestCase):
    def test_cli_uses_saved_session_state_when_run_id_not_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            project_root = tmp_path / "sample_app"
            project_root.mkdir(parents=True, exist_ok=True)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-context-cli",
                    "run_name": "context_cli_run",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-context-cli",
                {
                    "hottest_files": [{"file_path": "app/service.py", "rolling_score": 70.0, "total_time_ms": 300.0}],
                    "biggest_score_deltas": [],
                    "failure_count": 0,
                },
                [
                    {
                        "symbol_key": "app/service.py::load_items",
                        "display_name": "load_items",
                        "file_path": "app/service.py",
                        "self_time_ms": 80.0,
                        "total_time_ms": 300.0,
                        "call_count": 10,
                        "exception_count": 0,
                        "last_exception_type": None,
                        "normalized_compute_score": 78.0,
                    }
                ],
                [
                    {
                        "file_path": "app/service.py",
                        "total_self_time_ms": 80.0,
                        "total_time_ms": 300.0,
                        "call_count": 10,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 78.0,
                        "rolling_score": 70.0,
                    }
                ],
            )
            save_session_state(
                project_root,
                {
                    "selected_run_id": "run-context-cli",
                    "display_run_id": "run-context-cli",
                    "run_view_mode": "current",
                    "open_files": ["app/service.py"],
                    "focus_targets": [{"file_path": "app/service.py", "reason": "hot_file", "confidence": "high"}],
                },
            )
            stream = StringIO()
            exit_code = main(["--project-root", str(project_root), "--mode", "tiny"], output=stream)

            self.assertEqual(exit_code, 0)
            self.assertIn("Selected Run: run-context-cli", stream.getvalue())
            json_path = project_root / ".bluebench" / "bb_context_tiny.json"
            self.assertTrue(json_path.is_file())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["session"]["selected_run_id"], "run-context-cli")
            self.assertEqual(loaded["session"]["open_files"][0], "app/service.py")


if __name__ == "__main__":
    unittest.main()
