from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from backend.instrumentation.storage import InstrumentationStorage
from backend.triage.cli import main


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "triage" / "sample_app"


class TriageCliTests(unittest.TestCase):
    def test_cli_generates_reports_and_prints_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            storage = InstrumentationStorage(tmp_path / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-cli",
                    "run_name": "cli_run",
                    "project_root": str(FIXTURE_ROOT.resolve()),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-cli",
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
            stream = StringIO()
            exit_code = main(
                [
                    "--project-root",
                    str(FIXTURE_ROOT),
                    "--run-id",
                    "run-cli",
                    "--database",
                    str(tmp_path / "instrumentation.sqlite3"),
                    "--output-dir",
                    str(tmp_path),
                ],
                stdout=stream,
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("Project: sample_app", stream.getvalue())
            self.assertTrue((tmp_path / "bb_triage_report.json").is_file())
            self.assertTrue((tmp_path / "bb_triage_report.md").is_file())
            loaded = json.loads((tmp_path / "bb_triage_report.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["runtime_context"]["selected_run"]["run_name"], "cli_run")


if __name__ == "__main__":
    unittest.main()
