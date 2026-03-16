from __future__ import annotations

import io
import json
from pathlib import Path
import random
import tempfile
import time
import unittest

from backend.adapters.cli.commands import main as cli_main
from backend.adapters.cli.commands import _open_fd_count, _run_canonical_flow_iteration
from backend.history import load_experiment_records
from backend.instrumentation.storage import InstrumentationStorage


EXPECTED_TARGET = "backend/scanner/python_parser/python_scanner.py"


class CanonicalFlowStressTests(unittest.TestCase):
    def test_repeated_canonical_flow_stays_stable(self) -> None:
        with _stress_project() as (project_root, storage):
            current_run_id = "run-b"
            baseline_run_id = "run-a"
            initial_fd_count = _open_fd_count()
            runtimes: list[float] = []

            for index in range(75):
                started = time.perf_counter()
                flow = _run_canonical_flow_iteration(
                    project_root,
                    current_run_id,
                    baseline_run_id,
                    storage=storage,
                )
                runtimes.append(time.perf_counter() - started)

                self.assertEqual(flow["target"], EXPECTED_TARGET)
                self.assertEqual(flow["action_packet"]["primary_target"]["path"], EXPECTED_TARGET)
                self.assertEqual(flow["context_pack"]["compute"]["hot_files"][0]["file_path"], EXPECTED_TARGET)
                self.assertTrue(flow["recommendation"]["recommended_experiment"])

                if (index + 1) % 10 == 0:
                    print(
                        json.dumps(
                            {
                                "iteration": index + 1,
                                "avg_iteration_runtime_ms": round((sum(runtimes) / len(runtimes)) * 1000.0, 3),
                                "fd_count": _open_fd_count(),
                            },
                            sort_keys=True,
                        )
                    )

            first_window = sum(runtimes[:10]) / 10.0
            last_window = sum(runtimes[-10:]) / 10.0
            self.assertLessEqual(last_window, max(first_window * 4.0, first_window + 0.05))

            final_fd_count = _open_fd_count()
            if initial_fd_count is not None and final_fd_count is not None:
                self.assertLessEqual(final_fd_count, initial_fd_count + 8)

    def test_stress_canonical_cli_runs_repeated_flow(self) -> None:
        with _stress_project() as (project_root, _storage):
            stream = io.StringIO()
            exit_code = cli_main(
                ["stress-canonical", "--project-root", str(project_root), "--iterations", "25"],
                stdout=stream,
            )

        self.assertEqual(exit_code, 0)
        lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
        self.assertEqual(lines[-1]["status"], "ok")
        self.assertEqual(lines[-1]["target"], EXPECTED_TARGET)
        self.assertEqual(lines[-1]["iterations"], 25)

    def test_stress_canonical_cli_with_jitter_and_injected_failures_recovers(self) -> None:
        with _stress_project() as (project_root, _storage):
            stream = io.StringIO()
            exit_code = cli_main(
                [
                    "stress-canonical",
                    "--project-root",
                    str(project_root),
                    "--iterations",
                    "20",
                    "--jitter-ms",
                    "1",
                    "--inject-history-failure-every",
                    "7",
                    "--seed",
                    "7",
                ],
                stdout=stream,
            )

        self.assertEqual(exit_code, 0)
        lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
        self.assertTrue(any(line.get("status") == "expected_injected_failure" for line in lines))
        self.assertEqual(lines[-1]["status"], "ok")
        self.assertEqual(lines[-1]["target"], EXPECTED_TARGET)

    def test_repeated_canonical_flow_with_jitter_and_failure_injection_recovers(self) -> None:
        with _stress_project() as (project_root, storage):
            current_run_id = "run-b"
            baseline_run_id = "run-a"
            initial_fd_count = _open_fd_count()
            runtimes: list[float] = []
            rng = random.Random(7)
            injected_failures = 0
            recovery_verified = 0
            recovery_pending = False

            for index in range(1, 41):
                inject_failure = index % 9 == 0
                started = time.perf_counter()
                try:
                    flow = _run_canonical_flow_iteration(
                        project_root,
                        current_run_id,
                        baseline_run_id,
                        storage=storage,
                        jitter_seconds=0.001,
                        rng=rng,
                        fail_history_log=inject_failure,
                    )
                except RuntimeError as exc:
                    self.assertTrue(inject_failure)
                    self.assertEqual(str(exc), "injected history log failure")
                    injected_failures += 1
                    recovery_pending = True
                    continue
                except Exception as exc:  # pragma: no cover - regression guard
                    self.fail(f"unexpected exception during recovery stress loop: {exc}")

                runtimes.append(time.perf_counter() - started)
                self.assertEqual(flow["target"], EXPECTED_TARGET)
                self.assertEqual(flow["action_packet"]["primary_target"]["path"], EXPECTED_TARGET)
                self.assertTrue(flow["recommendation"]["recommended_experiment"])
                if recovery_pending:
                    recovery_verified += 1
                    recovery_pending = False

            self.assertEqual(injected_failures, 4)
            self.assertEqual(recovery_verified, 4)
            self.assertFalse(recovery_pending)

            records = load_experiment_records(project_root, target=EXPECTED_TARGET, experiment="compare_runs")
            self.assertEqual(len(records), 36)

            first_window = sum(runtimes[:10]) / 10.0
            last_window = sum(runtimes[-10:]) / 10.0
            self.assertLessEqual(last_window, max(first_window * 4.0, first_window + 0.05))

            final_fd_count = _open_fd_count()
            if initial_fd_count is not None and final_fd_count is not None:
                self.assertLessEqual(final_fd_count, initial_fd_count + 8)


class _stress_project:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.project_root: Path | None = None
        self.storage: InstrumentationStorage | None = None

    def __enter__(self) -> tuple[Path, InstrumentationStorage]:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp_dir.name)
        self.storage = InstrumentationStorage(self.project_root / ".bluebench" / "instrumentation.sqlite3")
        self.storage.initialize_schema()

        for run_id, run_name, finished_at, runtime_ms, trace_overhead_ms, scanner_ms, graph_ms in (
            ("run-a", "baseline", "2026-03-16T11:01:00+00:00", 2000.0, 320.0, 376.57, 52.30),
            ("run-b", "current", "2026-03-16T12:01:00+00:00", 1500.0, 120.0, 274.31, 23.84),
        ):
            self.storage.insert_run(
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
            self.storage.replace_staged_summaries(
                run_id,
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [
                    {
                        "symbol_key": "backend/scanner/python_parser/python_scanner.py::scan",
                        "display_name": "scan",
                        "file_path": EXPECTED_TARGET,
                        "self_time_ms": scanner_ms / 2.0,
                        "total_time_ms": scanner_ms,
                        "call_count": 100,
                        "exception_count": 0,
                        "last_exception_type": None,
                        "normalized_compute_score": 100.0,
                    }
                ],
                [
                    {
                        "file_path": EXPECTED_TARGET,
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
            if run_id == "run-b":
                (self.project_root / "bb_performance_report.json").write_text(
                    json.dumps(
                        {
                            "run_id": run_id,
                            "run_name": run_name,
                            "status": "completed",
                            "instrumented_runtime_ms": runtime_ms,
                            "trace_overhead_estimate_ms": trace_overhead_ms,
                            "run_quality": "strong",
                            "stage_timings_ms": {"triage_generate": 797.28, "context_build": 796.88},
                            "top_files_by_raw_ms": [
                                {
                                    "file_path": EXPECTED_TARGET,
                                    "raw_ms": scanner_ms,
                                    "call_count": 28141,
                                    "rolling_score": 91.4,
                                },
                                {
                                    "file_path": "backend/core/graph_engine/graph_manager.py",
                                    "raw_ms": graph_ms,
                                    "call_count": 1550,
                                    "rolling_score": 12.9,
                                },
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
        return self.project_root, self.storage

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
