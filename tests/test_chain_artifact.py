from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from backend.chain_artifact import write_verified_chain_result
from scripts.run_bluebench import main


class ChainArtifactTests(unittest.TestCase):
    def test_write_verified_chain_result_creates_compact_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            path = write_verified_chain_result(
                project_root,
                chain_id="chain-123",
                review_target="engine/scanner_engine.py",
                bluebench_run_id="run-b",
                comparison={"runtime_delta_ms": -12.5, "schema_compatible": True},
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["chain_id"], "chain-123")
            self.assertEqual(payload["bluebench_run_id"], "run-b")
            self.assertEqual(payload["runtime_result"]["verdict"], "confirmed")
            self.assertEqual(payload["status"], "verified")

    def test_compare_command_propagates_chain_id_and_writes_result(self) -> None:
        with _sample_bluebench_project() as project_root:
            exit_code = main(
                [
                    "compare",
                    "run-a",
                    "run-b",
                    "--project-root",
                    str(project_root),
                    "--chain-id",
                    "chain-compare",
                    "--target",
                    "backend/scanner/python_parser/python_scanner.py",
                ]
            )
            self.assertEqual(exit_code, 0)
            artifact = project_root / ".benchchain" / "chain-compare.json"
            self.assertTrue(artifact.is_file())
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(payload["chain_id"], "chain-compare")
            self.assertEqual(payload["review_target"], "backend/scanner/python_parser/python_scanner.py")
            self.assertEqual(payload["bluebench_run_id"], "run-b")
            self.assertIn("runtime_delta_ms", payload["runtime_result"])
            self.assertEqual(payload["runtime_result"]["verdict"], "confirmed")


class _sample_bluebench_project:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.project_root: Path | None = None

    def __enter__(self) -> Path:
        from backend.instrumentation.storage import InstrumentationStorage

        self.tmp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp_dir.name)
        storage = InstrumentationStorage(self.project_root / ".bluebench" / "instrumentation.sqlite3")
        storage.initialize_schema()
        for run_id, run_name, finished_at, scanner_ms, graph_ms in (
            ("run-a", "baseline", "2026-03-16T11:01:00+00:00", 376.57, 52.30),
            ("run-b", "current", "2026-03-16T12:01:00+00:00", 274.31, 23.84),
        ):
            storage.insert_run(
                {
                    "run_id": run_id,
                    "run_name": run_name,
                    "project_root": str(self.project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T12:00:00+00:00",
                    "finished_at": finished_at,
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                run_id,
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [],
                [
                    {
                        "file_path": "backend/scanner/python_parser/python_scanner.py",
                        "total_self_time_ms": scanner_ms / 2.0,
                        "total_time_ms": scanner_ms,
                        "call_count": 28141,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 100.0,
                        "rolling_score": 91.4 if run_id == "run-b" else 95.0,
                    },
                    {
                        "file_path": "backend/core/graph_engine/graph_manager.py",
                        "total_self_time_ms": graph_ms / 2.0,
                        "total_time_ms": graph_ms,
                        "call_count": 1550,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 8.7 if run_id == "run-b" else 13.9,
                        "rolling_score": 12.9 if run_id == "run-b" else 20.3,
                    },
                ],
            )
        storage.write_performance_report(
            self.project_root,
            {
                "run_id": "run-a",
                "run_name": "baseline",
                "status": "completed",
                "instrumented_runtime_ms": 2000.0,
                "trace_overhead_estimate_ms": 320.0,
                "run_quality": "strong",
                "stage_timings_ms": {"triage_generate": 900.0},
                "top_files_by_raw_ms": [
                    {
                        "file_path": "backend/scanner/python_parser/python_scanner.py",
                        "raw_ms": 376.57,
                        "call_count": 28141,
                        "rolling_score": 95.0,
                    }
                ],
            },
        )
        storage.write_performance_report(
            self.project_root,
            {
                "run_id": "run-b",
                "run_name": "current",
                "status": "completed",
                "instrumented_runtime_ms": 1500.0,
                "trace_overhead_estimate_ms": 120.0,
                "run_quality": "strong",
                "stage_timings_ms": {"triage_generate": 800.0},
                "top_files_by_raw_ms": [
                    {
                        "file_path": "backend/scanner/python_parser/python_scanner.py",
                        "raw_ms": 274.31,
                        "call_count": 28141,
                        "rolling_score": 91.4,
                    }
                ],
            },
        )
        return self.project_root

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()
