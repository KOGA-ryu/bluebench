from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.instrumentation.storage import InstrumentationStorage
from backend.triage.service import generate_triage


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "triage" / "sample_app"


class TriageServiceTests(unittest.TestCase):
    def test_generate_triage_without_run_returns_static_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = InstrumentationStorage(Path(tmp_dir) / "instrumentation.sqlite3")
            triage = generate_triage(FIXTURE_ROOT, storage=storage)

        self.assertEqual(triage["project"]["name"], "sample_app")
        self.assertEqual(triage["project"]["app_type_guess"], "desktop")
        self.assertTrue(triage["project"]["entry_points"])
        self.assertIn("PySide6", triage["operational_risks"]["native_dependencies"])
        self.assertEqual(triage["runtime_context"]["selected_run"], None)
        self.assertTrue(triage["recommended_actions"])

    def test_generate_triage_with_run_uses_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = InstrumentationStorage(Path(tmp_dir) / "instrumentation.sqlite3")
            storage.initialize_schema()
            run_row = {
                "run_id": "run-1",
                "run_name": "fixture_run",
                "project_root": str(FIXTURE_ROOT.resolve()),
                "scenario_kind": "custom_script",
                "hardware_profile": "mini_pc_n100_16gb",
                "started_at": "2026-03-15T10:00:00+00:00",
                "finished_at": "2026-03-15T10:01:00+00:00",
                "status": "completed",
            }
            storage.insert_run(run_row)
            storage.replace_staged_summaries(
                "run-1",
                {
                    "hottest_files": [
                        {
                            "file_path": "app/service.py",
                            "rolling_score": 81.5,
                            "total_time_ms": 420.0,
                        }
                    ],
                    "biggest_score_deltas": [
                        {
                            "file_path": "app/service.py",
                            "score_delta": 14.0,
                        }
                    ],
                    "failure_count": 1,
                },
                [
                    {
                        "symbol_key": "app/service.py::load_items",
                        "display_name": "load_items",
                        "file_path": "app/service.py",
                        "self_time_ms": 120.0,
                        "total_time_ms": 420.0,
                        "call_count": 15,
                        "exception_count": 1,
                        "last_exception_type": "RuntimeError",
                        "normalized_compute_score": 92.0,
                    }
                ],
                [
                    {
                        "file_path": "app/service.py",
                        "total_self_time_ms": 120.0,
                        "total_time_ms": 420.0,
                        "call_count": 15,
                        "exception_count": 1,
                        "external_pressure_summary": {
                            "external_buckets": {
                                "external:sqlite3": {
                                    "total_time_ms": 18.0,
                                    "call_count": 2,
                                }
                            }
                        },
                        "normalized_compute_score": 92.0,
                        "rolling_score": 81.5,
                    }
                ],
            )
            (FIXTURE_ROOT / "bb_performance_report.json").write_text(
                json.dumps(
                    {
                        "trace_events": 1200,
                        "functions_seen": 5,
                        "files_seen": 2,
                        "instrumented_runtime_ms": 500.0,
                        "trace_overhead_estimate_ms": 310.0,
                    }
                ),
                encoding="utf-8",
            )
            try:
                triage = generate_triage(FIXTURE_ROOT, run_id="run-1", mode="full", storage=storage)
            finally:
                report_path = FIXTURE_ROOT / "bb_performance_report.json"
                if report_path.exists():
                    report_path.unlink()

        self.assertEqual(triage["runtime_context"]["selected_run"]["run_name"], "fixture_run")
        self.assertTrue(triage["compute"]["hot_files"])
        self.assertEqual(triage["compute"]["hot_files"][0]["file_path"], "app/service.py")
        self.assertTrue(triage["compute"]["regressions"])
        self.assertTrue(triage["compute"]["canonical_summary"]["summary_lines"])
        self.assertTrue(triage["hypotheses"])
        self.assertTrue(triage["recommended_actions"])
        self.assertIn("native_risk_files", triage["operational_risks"])
        self.assertIn("app_type_signals", triage["project"])

    def test_generate_triage_filters_vendor_and_venv_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            (project_root / "app").mkdir(parents=True, exist_ok=True)
            (project_root / ".venv" / "lib" / "python3.14" / "site-packages" / "pkg").mkdir(parents=True, exist_ok=True)
            (project_root / "app" / "main.py").write_text(
                "from PySide6.QtWidgets import QApplication\n\nif __name__ == '__main__':\n    pass\n",
                encoding="utf-8",
            )
            (project_root / ".venv" / "lib" / "python3.14" / "site-packages" / "pkg" / "noise.py").write_text(
                "import requests\n",
                encoding="utf-8",
            )
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            triage = generate_triage(project_root, storage=storage)

        entry_paths = [item["path"] for item in triage["project"]["entry_points"]]
        hotspot_paths = [item["file_path"] for item in triage["architecture"]["relationship_hotspots"]]
        self.assertTrue(all(".venv" not in path for path in entry_paths))
        self.assertTrue(all("site-packages" not in path for path in hotspot_paths))


if __name__ == "__main__":
    unittest.main()
