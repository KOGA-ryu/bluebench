from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from backend.instrumentation.aggregator import BackgroundAggregator
from backend.instrumentation.collector import RunMetricsCollector
from backend.instrumentation.ranking import LiveRankingCalculator
from backend.instrumentation.storage import InstrumentationStorage


def traced_factorial(value: int) -> int:
    if value <= 1:
        return 1
    return value * traced_factorial(value - 1)


class _TrackedConnection:
    def __init__(self, connection: sqlite3.Connection, owner: "_TrackedStorage") -> None:
        self._connection = connection
        self._owner = owner
        self._closed = False

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def __enter__(self):
        return self._connection.__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._connection.__exit__(exc_type, exc, tb)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._owner.close_count += 1
        self._connection.close()


class _TrackedStorage(InstrumentationStorage):
    def __init__(self, database_path: str | Path) -> None:
        super().__init__(database_path)
        self.open_count = 0
        self.close_count = 0

    def _connect(self) -> sqlite3.Connection:
        self.open_count += 1
        connection = super()._connect()
        return _TrackedConnection(connection, self)

    def insert_run_then_fail(self, run_row: dict[str, object]) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runs
                (run_id, run_name, project_root, scenario_kind, hardware_profile, started_at, finished_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_row["run_id"],
                    run_row["run_name"],
                    str(Path(run_row["project_root"]).resolve()) if run_row.get("project_root") else None,
                    run_row["scenario_kind"],
                    run_row["hardware_profile"],
                    run_row["started_at"],
                    run_row.get("finished_at"),
                    run_row["status"],
                ),
            )
            raise RuntimeError("boom")


class InstrumentationTests(unittest.TestCase):
    def test_live_ranking_prefers_recent_hot_file_activity(self) -> None:
        ranking = LiveRankingCalculator(decay_seconds=1.0)
        ranking.record("a.py", 30.0, now=1.0)
        ranking.record("b.py", 10.0, now=1.5)
        ranking.record("b.py", 40.0, now=1.6)

        snapshot = ranking.snapshot(limit=2, now=1.6)

        self.assertEqual(snapshot[0].file_path, "b.py")
        self.assertGreater(snapshot[0].rolling_score, snapshot[1].rolling_score)

    def test_collector_records_recursive_function_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(__file__).resolve().parents[1]
            database_path = Path(tmp_dir) / "instrumentation.sqlite3"
            storage = InstrumentationStorage(database_path)
            aggregator = BackgroundAggregator(storage)
            collector = RunMetricsCollector(
                project_root,
                storage,
                aggregator,
                run_name="recursive-test",
                scenario_kind="unit",
                hardware_profile="local",
            )

            run_id = collector.start()
            traced_factorial(4)
            collector.stop()
            aggregator.aggregate_run(run_id)

            rows = storage.fetch_function_rows(run_id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["function_name"], "traced_factorial")
            self.assertGreaterEqual(rows[0]["call_count"], 4)
            self.assertGreaterEqual(rows[0]["recursive_call_count"], 3)
            self.assertGreaterEqual(rows[0]["max_recursion_depth"], 4)

    def test_aggregator_writes_summary_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            database_path = project_root / "instrumentation.sqlite3"
            storage = InstrumentationStorage(database_path)
            storage.initialize_schema()
            run_id = "run-1"
            storage.insert_run(
                {
                    "run_id": run_id,
                    "run_name": "stress",
                    "project_root": str(project_root),
                    "scenario_kind": "stress",
                    "hardware_profile": "local",
                    "started_at": "2026-03-14T00:00:00+00:00",
                    "finished_at": "2026-03-14T00:00:10+00:00",
                    "status": "completed",
                }
            )
            storage.insert_function_rows(
                run_id,
                [
                    {
                        "symbol_key": "pkg/a.py::run",
                        "display_name": "a.py::run",
                        "file_path": "pkg/a.py",
                        "function_name": "run",
                        "self_time_ms": 40.0,
                        "total_time_ms": 70.0,
                        "call_count": 4,
                        "recursive_call_count": 0,
                        "max_recursion_depth": 1,
                        "exception_count": 1,
                        "last_exception_type": "ValueError",
                    },
                    {
                        "symbol_key": "pkg/b.py::scan",
                        "display_name": "b.py::scan",
                        "file_path": "pkg/b.py",
                        "function_name": "scan",
                        "self_time_ms": 10.0,
                        "total_time_ms": 20.0,
                        "call_count": 3,
                        "recursive_call_count": 0,
                        "max_recursion_depth": 1,
                        "exception_count": 0,
                        "last_exception_type": None,
                    },
                ],
            )
            storage.insert_resource_samples(
                run_id,
                [
                    {"sample_ts": time.time(), "cpu_percent": 25.0, "rss_mb": 128.0, "read_bytes": None, "write_bytes": None},
                    {"sample_ts": time.time(), "cpu_percent": 35.0, "rss_mb": 140.0, "read_bytes": None, "write_bytes": None},
                ],
            )
            storage.insert_external_bucket_rows(
                run_id,
                [
                    {"bucket_name": "external:stdlib", "total_time_ms": 11.0, "call_count": 2},
                ],
            )
            storage.insert_live_file_rows(
                run_id,
                [
                    {"file_path": "pkg/a.py", "rolling_score": 80.0, "raw_ms": 70.0, "call_count": 4},
                    {"file_path": "pkg/b.py", "rolling_score": 20.0, "raw_ms": 20.0, "call_count": 3},
                ],
            )

            aggregator = BackgroundAggregator(storage)
            aggregator.aggregate_run(run_id)

            run_summary = storage.fetch_run(run_id)
            self.assertIsNotNone(run_summary)
            file_scores = storage.fetch_file_summary_map(run_id)
            self.assertIn("pkg/a.py", file_scores)
            self.assertGreater(file_scores["pkg/a.py"], file_scores["pkg/b.py"])
            self.assertEqual(len(storage.list_completed_runs()), 1)
            self.assertEqual(len(storage.list_completed_runs(project_root=project_root)), 1)
            self.assertIsNotNone(storage.fetch_file_summary(run_id, "pkg/a.py"))
            self.assertEqual(
                [row["symbol_key"] for row in storage.fetch_function_summaries_for_file(run_id, "pkg/a.py")],
                ["pkg/a.py::run"],
            )

    def test_storage_repeated_operations_close_connections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = _TrackedStorage(project_root / "instrumentation.sqlite3")
            storage.initialize_schema()

            for index in range(50):
                run_id = f"run-{index}"
                storage.insert_run(
                    {
                        "run_id": run_id,
                        "run_name": run_id,
                        "project_root": str(project_root),
                        "scenario_kind": "stress",
                        "hardware_profile": "local",
                        "started_at": "2026-03-14T00:00:00+00:00",
                        "finished_at": "2026-03-14T00:00:10+00:00",
                        "status": "completed",
                    }
                )
                self.assertIsNotNone(storage.fetch_run(run_id))
                self.assertEqual(len(storage.list_completed_runs(project_root=project_root)), index + 1)

            self.assertEqual(storage.open_count, storage.close_count)

    def test_storage_connection_rolls_back_and_closes_on_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = _TrackedStorage(project_root / "instrumentation.sqlite3")
            storage.initialize_schema()
            with self.assertRaisesRegex(RuntimeError, "boom"):
                storage.insert_run_then_fail(
                    {
                        "run_id": "run-error",
                        "run_name": "run-error",
                        "project_root": str(project_root),
                        "scenario_kind": "stress",
                        "hardware_profile": "local",
                        "started_at": "2026-03-14T00:00:00+00:00",
                        "finished_at": "2026-03-14T00:00:10+00:00",
                        "status": "completed",
                    }
                )

            self.assertIsNone(storage.fetch_run("run-error"))
            self.assertEqual(storage.open_count, storage.close_count)


if __name__ == "__main__":
    unittest.main()
