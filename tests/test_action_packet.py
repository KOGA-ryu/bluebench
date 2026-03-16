from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from backend.adapters.cli.commands import main
from backend.adapters.codex.action_packet import generate_action_packet
from backend.instrumentation.storage import InstrumentationStorage


class ActionPacketTests(unittest.TestCase):
    def test_generate_action_packet_uses_canonical_run_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-a",
                    "run_name": "baseline",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T11:00:00+00:00",
                    "finished_at": "2026-03-16T11:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.insert_run(
                {
                    "run_id": "run-b",
                    "run_name": "current",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T12:00:00+00:00",
                    "finished_at": "2026-03-16T12:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-a",
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [],
                [
                    {
                        "file_path": "backend/scanner/python_parser/python_scanner.py",
                        "total_self_time_ms": 100.0,
                        "total_time_ms": 376.57,
                        "call_count": 30000,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 100.0,
                        "rolling_score": 95.0,
                    }
                ],
            )
            storage.replace_staged_summaries(
                "run-b",
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [],
                [
                    {
                        "file_path": "backend/scanner/python_parser/python_scanner.py",
                        "total_self_time_ms": 80.0,
                        "total_time_ms": 274.31,
                        "call_count": 28141,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 100.0,
                        "rolling_score": 91.4,
                    },
                    {
                        "file_path": "backend/core/graph_engine/graph_manager.py",
                        "total_self_time_ms": 10.0,
                        "total_time_ms": 23.84,
                        "call_count": 1550,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 8.7,
                        "rolling_score": 12.9,
                    },
                ],
            )
            (project_root / "bb_performance_report.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-b",
                        "run_name": "current",
                        "status": "completed",
                        "instrumented_runtime_ms": 1615.02,
                        "trace_overhead_estimate_ms": 256.22,
                        "run_quality": "strong",
                        "stage_timings_ms": {"triage_generate": 797.28},
                        "top_files_by_raw_ms": [
                            {
                                "file_path": "backend/scanner/python_parser/python_scanner.py",
                                "raw_ms": 274.31,
                                "call_count": 28141,
                                "rolling_score": 91.4,
                            },
                            {
                                "file_path": "backend/core/graph_engine/graph_manager.py",
                                "raw_ms": 23.84,
                                "call_count": 1550,
                                "rolling_score": 12.9,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            packet = generate_action_packet("run-b", project_root=project_root, storage=storage)

        self.assertEqual(packet["schema_version"], "1")
        self.assertEqual(packet["packet_type"], "hotspot_investigation")
        self.assertEqual(packet["run_id"], "run-b")
        self.assertEqual(packet["baseline_run_id"], "run-a")
        self.assertEqual(packet["primary_target"]["path"], "backend/scanner/python_parser/python_scanner.py")
        self.assertEqual(packet["recommended_actions"][1]["experiment"], "isolate_hotspot")
        self.assertTrue(packet["supporting_evidence"]["measured"])
        self.assertTrue(packet["supporting_evidence"]["derived"])

    def test_action_packet_cli_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-cli",
                    "run_name": "cli",
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
                        "run_name": "cli",
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
                ["action-packet", "--project-root", str(project_root), "--run", "run-cli"],
                stdout=stream,
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["run_id"], "run-cli")
        self.assertEqual(payload["primary_target"]["path"], "app/main.py")


if __name__ == "__main__":
    unittest.main()
