from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.history.experiment_log import log_experiment_result
from backend.instrumentation.storage import InstrumentationStorage
from backend.recommend import recommend_next_experiment


class RecommendNextTests(unittest.TestCase):
    def test_hotspot_with_no_prior_isolation_recommends_isolate_hotspot(self) -> None:
        with _project_with_runs(trace_overhead_ms=50.0) as (project_root, storage):
            packet = recommend_next_experiment(
                "backend/scanner/python_parser/python_scanner.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )
        self.assertEqual(packet["recommended_experiment"], "isolate_hotspot")

    def test_low_confidence_history_recommends_rerun_repeatability(self) -> None:
        with _project_with_runs(trace_overhead_ms=50.0) as (project_root, storage):
            log_experiment_result(project_root, _isolate_payload("backend/scanner/python_parser/python_scanner.py"))
            packet = recommend_next_experiment(
                "backend/scanner/python_parser/python_scanner.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )
        self.assertEqual(packet["recommended_experiment"], "rerun_repeatability")

    def test_missing_comparison_after_change_recommends_compare_runs(self) -> None:
        with _project_with_runs(trace_overhead_ms=50.0) as (project_root, storage):
            for _ in range(3):
                log_experiment_result(project_root, _isolate_payload("backend/scanner/python_parser/python_scanner.py"))
            packet = recommend_next_experiment(
                "backend/scanner/python_parser/python_scanner.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )
        self.assertEqual(packet["recommended_experiment"], "compare_runs")

    def test_high_overhead_ratio_recommends_trace_overhead(self) -> None:
        with _project_with_runs(trace_overhead_ms=900.0) as (project_root, storage):
            packet = recommend_next_experiment(
                "backend/scanner/python_parser/python_scanner.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )
        self.assertEqual(packet["recommended_experiment"], "trace_overhead")

    def test_stable_hotspot_with_prior_evidence_recommends_inspect_file(self) -> None:
        with _project_with_runs(trace_overhead_ms=50.0) as (project_root, storage):
            for _ in range(7):
                log_experiment_result(project_root, _isolate_payload("backend/scanner/python_parser/python_scanner.py"))
            log_experiment_result(project_root, _compare_payload("backend/scanner/python_parser/python_scanner.py"))
            packet = recommend_next_experiment(
                "backend/scanner/python_parser/python_scanner.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )
        self.assertEqual(packet["recommended_experiment"], "inspect_file")


class _project_with_runs:
    def __init__(self, *, trace_overhead_ms: float) -> None:
        self.trace_overhead_ms = trace_overhead_ms
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.project_root: Path | None = None
        self.storage: InstrumentationStorage | None = None

    def __enter__(self) -> tuple[Path, InstrumentationStorage]:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp_dir.name)
        self.storage = InstrumentationStorage(self.project_root / ".bluebench" / "instrumentation.sqlite3")
        self.storage.initialize_schema()
        for run_id, run_name, runtime_ms in (
            ("run-a", "baseline", 2000.0),
            ("run-b", "current", 1500.0),
        ):
            self.storage.insert_run(
                {
                    "run_id": run_id,
                    "run_name": run_name,
                    "project_root": str(self.project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T12:00:00+00:00",
                    "finished_at": "2026-03-16T12:01:00+00:00",
                    "status": "completed",
                }
            )
            self.storage.replace_staged_summaries(
                run_id,
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [],
                [
                    {
                        "file_path": "backend/scanner/python_parser/python_scanner.py",
                        "total_self_time_ms": 80.0,
                        "total_time_ms": 274.31 if run_id == "run-b" else 376.57,
                        "call_count": 28141,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 100.0,
                        "rolling_score": 91.4 if run_id == "run-b" else 95.0,
                    }
                ],
            )
        (self.project_root / "bb_performance_report.json").write_text(
            json.dumps(
                {
                    "run_id": "run-b",
                    "run_name": "current",
                    "status": "completed",
                    "instrumented_runtime_ms": 1500.0,
                    "trace_overhead_estimate_ms": self.trace_overhead_ms,
                    "run_quality": "strong",
                    "stage_timings_ms": {"triage_generate": 797.28},
                    "top_files_by_raw_ms": [
                        {
                            "file_path": "backend/scanner/python_parser/python_scanner.py",
                            "raw_ms": 274.31,
                            "call_count": 28141,
                            "rolling_score": 91.4,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return self.project_root, self.storage

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()


def _isolate_payload(target: str) -> dict[str, object]:
    return {
        "experiment": "isolate_hotspot",
        "result": {
            "evidence": {"run": {"run_id": "run-b", "measured": {"runtime_ms": 1500.0}}},
            "derived": {
                "top_hotspot": {"file_path": target},
                "note": "placeholder",
            },
        },
    }


def _compare_payload(target: str) -> dict[str, object]:
    return {
        "experiment": "compare_runs",
        "result": {
            "evidence": {
                "baseline": {"run_id": "run-a", "measured": {"runtime_ms": 2000.0}},
                "current": {"run_id": "run-b", "measured": {"runtime_ms": 1500.0}},
            },
            "derived": {
                "runtime_delta_ms": -500.0,
                "trace_overhead_delta_ms": -100.0,
                "file_deltas": [{"file_path": target, "raw_ms_delta": -100.0}],
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
