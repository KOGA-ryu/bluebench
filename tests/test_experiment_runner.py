from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from backend.adapters.cli.commands import main
from backend.experiments.runner import run_experiment
from backend.instrumentation.storage import InstrumentationStorage


class ExperimentRunnerTests(unittest.TestCase):
    def test_unknown_experiment_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown experiment"):
            run_experiment("not_real", project_root=Path("/tmp"))

    def test_missing_required_args_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing required args"):
            run_experiment("isolate_hotspot", project_root=Path("/tmp"))

    def test_successful_dispatch_returns_canonical_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-1",
                    "run_name": "run-1",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T12:00:00+00:00",
                    "finished_at": "2026-03-16T12:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-1",
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [],
                [
                    {
                        "file_path": "app/main.py",
                        "total_self_time_ms": 12.0,
                        "total_time_ms": 42.0,
                        "call_count": 5,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 88.0,
                        "rolling_score": 76.0,
                    }
                ],
            )
            (project_root / "bb_performance_report.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "run_name": "run-1",
                        "status": "completed",
                        "instrumented_runtime_ms": 120.0,
                        "trace_overhead_estimate_ms": 12.0,
                        "run_quality": "strong",
                        "stage_timings_ms": {},
                        "top_files_by_raw_ms": [
                            {"file_path": "app/main.py", "raw_ms": 42.0, "call_count": 5, "rolling_score": 76.0}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = run_experiment("isolate_hotspot", project_root=project_root, run_id="run-1", storage=storage)

        self.assertEqual(result["experiment"], "isolate_hotspot")
        self.assertEqual(result["result_type"], "hotspot_isolation")
        self.assertEqual(result["result"]["name"], "isolate_hotspot")
        self.assertEqual(result["result"]["derived"]["top_hotspot"]["file_path"], "app/main.py")

    def test_cli_experiment_run_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-cli",
                    "run_name": "run-cli",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T12:00:00+00:00",
                    "finished_at": "2026-03-16T12:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-cli",
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [],
                [
                    {
                        "file_path": "app/main.py",
                        "total_self_time_ms": 12.0,
                        "total_time_ms": 42.0,
                        "call_count": 5,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 88.0,
                        "rolling_score": 76.0,
                    }
                ],
            )
            (project_root / "bb_performance_report.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-cli",
                        "run_name": "run-cli",
                        "status": "completed",
                        "instrumented_runtime_ms": 120.0,
                        "trace_overhead_estimate_ms": 12.0,
                        "run_quality": "strong",
                        "stage_timings_ms": {},
                        "top_files_by_raw_ms": [
                            {"file_path": "app/main.py", "raw_ms": 42.0, "call_count": 5, "rolling_score": 76.0}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stream = StringIO()
            exit_code = main(
                ["experiment", "run", "isolate_hotspot", "--project-root", str(project_root), "--run-id", "run-cli"],
                stdout=stream,
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["experiment"], "isolate_hotspot")
        self.assertEqual(payload["result"]["derived"]["top_hotspot"]["file_path"], "app/main.py")


if __name__ == "__main__":
    unittest.main()
