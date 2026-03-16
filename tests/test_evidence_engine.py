from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.adapters.codex.context_pack import build_codex_context_pack
from backend.derive import build_file_compute_details, build_function_compute_details
from backend.derive.hotspot_ranker import rank_file_hotspots
from backend.derive.run_comparator import compare_runs
from backend.derive.summary_builder import build_run_summary
from backend.evidence.loaders.evidence_loader import load_run_evidence
from backend.instrumentation.storage import InstrumentationStorage


class EvidenceEngineTests(unittest.TestCase):
    def test_load_run_evidence_returns_canonical_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-1",
                    "run_name": "first",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-1",
                {
                    "hottest_files": [],
                    "biggest_score_deltas": [],
                    "failure_count": 0,
                },
                [],
                [
                    {
                        "file_path": "app/main.py",
                        "total_self_time_ms": 10.0,
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
                        "run_name": "first",
                        "status": "completed",
                        "instrumented_runtime_ms": 123.0,
                        "trace_overhead_estimate_ms": 12.0,
                        "run_quality": "strong",
                        "stage_timings_ms": {"triage_generate": 50.0},
                        "top_files_by_raw_ms": [
                            {"file_path": "app/main.py", "raw_ms": 42.0, "call_count": 5, "rolling_score": 76.0}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            evidence = load_run_evidence("run-1", project_root=project_root, storage=storage)

        assert evidence is not None
        self.assertEqual(evidence["schema_version"], "1")
        self.assertEqual(evidence["run_id"], "run-1")
        self.assertEqual(evidence["measured"]["runtime_ms"], 123.0)
        self.assertEqual(evidence["stages"]["triage_generate"], 50.0)
        self.assertEqual(evidence["files"][0]["file_path"], "app/main.py")

    def test_hotspot_ranker_and_comparator_are_stable(self) -> None:
        baseline = {
            "measured": {"runtime_ms": 100.0, "trace_overhead_ms": 10.0},
            "stages": {"triage_generate": 40.0},
            "files": [
                {"file_path": "a.py", "raw_ms": 20.0, "call_count": 2},
                {"file_path": "b.py", "raw_ms": 10.0, "call_count": 1},
            ],
        }
        current = {
            "measured": {"runtime_ms": 90.0, "trace_overhead_ms": 8.0},
            "stages": {"triage_generate": 35.0},
            "files": [
                {"file_path": "a.py", "raw_ms": 12.0, "call_count": 2},
                {"file_path": "b.py", "raw_ms": 18.0, "call_count": 1},
            ],
        }

        hotspots = rank_file_hotspots(current)
        comparison = compare_runs(baseline, current)

        self.assertEqual(hotspots[0]["file_path"], "b.py")
        self.assertEqual(comparison["derive_version"], "1")
        self.assertTrue(comparison["schema_compatible"])
        self.assertEqual(comparison["runtime_delta_ms"], -10.0)
        self.assertEqual(comparison["stage_deltas"]["triage_generate"], -5.0)

    def test_load_run_evidence_prefers_exact_run_report_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            for run_id, run_name, runtime_ms, trace_overhead_ms in (
                ("run-a", "baseline", 150.0, 20.0),
                ("run-b", "current", 100.0, 8.0),
            ):
                storage.insert_run(
                    {
                        "run_id": run_id,
                        "run_name": run_name,
                        "project_root": str(project_root),
                        "scenario_kind": "custom_script",
                        "hardware_profile": "mini_pc_n100_16gb",
                        "started_at": "2026-03-15T10:00:00+00:00",
                        "finished_at": "2026-03-15T10:01:00+00:00",
                        "status": "completed",
                    }
                )
                storage.replace_staged_summaries(
                    run_id,
                    {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                    [],
                    [
                        {
                            "file_path": "app/main.py",
                            "total_self_time_ms": 10.0,
                            "total_time_ms": 42.0,
                            "call_count": 5,
                            "exception_count": 0,
                            "external_pressure_summary": {"external_buckets": {}},
                            "normalized_compute_score": 88.0,
                            "rolling_score": 76.0,
                        }
                    ],
                )
                storage.write_performance_report(
                    project_root,
                    {
                        "run_id": run_id,
                        "run_name": run_name,
                        "status": "completed",
                        "instrumented_runtime_ms": runtime_ms,
                        "trace_overhead_estimate_ms": trace_overhead_ms,
                        "run_quality": "strong",
                        "stage_timings_ms": {"triage_generate": runtime_ms / 2.0},
                        "top_files_by_raw_ms": [
                            {"file_path": "app/main.py", "raw_ms": 42.0, "call_count": 5, "rolling_score": 76.0}
                        ],
                    },
                )

            baseline = load_run_evidence("run-a", project_root=project_root, storage=storage)
            current = load_run_evidence("run-b", project_root=project_root, storage=storage)

        assert baseline is not None
        assert current is not None
        self.assertEqual(baseline["measured"]["runtime_ms"], 150.0)
        self.assertEqual(current["measured"]["runtime_ms"], 100.0)
        comparison = compare_runs(baseline, current)
        self.assertEqual(comparison["runtime_delta_ms"], -50.0)

    def test_summary_builder_produces_compact_output(self) -> None:
        evidence = {
            "run_id": "run-1",
            "run_name": "first",
            "status": "completed",
            "quality": "strong",
            "measured": {"runtime_ms": 100.0, "trace_overhead_ms": 10.0},
            "files": [{"file_path": "a.py", "raw_ms": 20.0, "call_count": 2}],
        }
        previous = {
            "measured": {"runtime_ms": 110.0, "trace_overhead_ms": 11.0},
            "files": [{"file_path": "a.py", "raw_ms": 25.0, "call_count": 2}],
        }

        summary = build_run_summary(evidence, previous)

        self.assertEqual(summary["derive_version"], "1")
        self.assertEqual(summary["schema_version"], "1")
        self.assertEqual(summary["run"]["run_id"], "run-1")
        self.assertEqual(summary["hotspots"][0]["file_path"], "a.py")
        self.assertTrue(summary["summary_lines"])
        self.assertTrue(summary["evidence_types"]["measured"])

    def test_summary_builder_labels_schema_mismatch(self) -> None:
        current = {
            "schema_version": "2",
            "run_id": "run-2",
            "run_name": "current",
            "status": "completed",
            "measured": {"runtime_ms": 50.0},
            "files": [{"file_path": "a.py", "raw_ms": 10.0, "call_count": 1}],
        }
        previous = {
            "schema_version": "1",
            "run_id": "run-1",
            "run_name": "previous",
            "status": "completed",
            "measured": {"runtime_ms": 60.0},
            "files": [{"file_path": "a.py", "raw_ms": 11.0, "call_count": 1}],
        }

        summary = build_run_summary(current, previous)

        self.assertFalse(summary["comparison"]["schema_compatible"])
        self.assertTrue(summary["comparison"]["comparison_warnings"])
        self.assertTrue(any("Comparison warning:" in line for line in summary["summary_lines"]))

    def test_codex_context_pack_uses_canonical_derivation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            for run_id, runtime_ms, raw_ms, finished_at in (
                ("run-a", 120.0, 60.0, "2026-03-15T10:01:00+00:00"),
                ("run-b", 100.0, 40.0, "2026-03-15T10:02:00+00:00"),
            ):
                storage.insert_run(
                    {
                        "run_id": run_id,
                        "run_name": run_id,
                        "project_root": str(project_root),
                        "scenario_kind": "custom_script",
                        "hardware_profile": "mini_pc_n100_16gb",
                        "started_at": "2026-03-15T10:00:00+00:00",
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
                            "file_path": "app/main.py",
                            "total_self_time_ms": 10.0,
                            "total_time_ms": raw_ms,
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
                        "run_name": "run-b",
                        "status": "completed",
                        "instrumented_runtime_ms": 100.0,
                        "trace_overhead_estimate_ms": 8.0,
                        "run_quality": "strong",
                        "stage_timings_ms": {"triage_generate": 35.0},
                        "top_files_by_raw_ms": [
                            {"file_path": "app/main.py", "raw_ms": 40.0, "call_count": 5, "rolling_score": 76.0}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            pack = build_codex_context_pack(project_root, "run-b", "current", storage=storage)

        self.assertEqual(pack["summary"]["hotspots"][0]["file_path"], "app/main.py")
        self.assertIn("runtime_delta_ms", pack["summary"]["comparison"])

    def test_compute_detail_builders_return_canonical_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-c",
                    "run_name": "run-c",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:02:00+00:00",
                    "status": "completed",
                }
            )
            storage.insert_run(
                {
                    "run_id": "run-p",
                    "run_name": "run-p",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T09:00:00+00:00",
                    "finished_at": "2026-03-15T09:02:00+00:00",
                    "status": "completed",
                }
            )
            for run_id, score in (("run-c", 80.0), ("run-p", 70.0)):
                storage.replace_staged_summaries(
                    run_id,
                    {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                    [
                        {
                            "symbol_key": "app/main.py::run",
                            "display_name": "run",
                            "file_path": "app/main.py",
                            "self_time_ms": 15.0,
                            "total_time_ms": 30.0,
                            "call_count": 4,
                            "exception_count": 0,
                            "last_exception_type": None,
                            "normalized_compute_score": score,
                        }
                    ],
                    [
                        {
                            "file_path": "app/main.py",
                            "total_self_time_ms": 15.0,
                            "total_time_ms": 30.0,
                            "call_count": 4,
                            "exception_count": 0,
                            "external_pressure_summary": {"external_buckets": {}},
                            "normalized_compute_score": score,
                            "rolling_score": score,
                        }
                    ],
                )

            file_compute = build_file_compute_details(storage, "run-c", "app/main.py")
            function_compute = build_function_compute_details(storage, "run-c", "app/main.py")

        self.assertEqual(file_compute["compute_tier"], 9)
        self.assertEqual(file_compute["delta"], 10.0)
        self.assertEqual(function_compute[0]["display_name"], "run")


if __name__ == "__main__":
    unittest.main()
