from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.adapters.codex.action_packet import generate_action_packet
from backend.context import build_context_pack
from backend.experiments.runner import run_experiment
from backend.governance.semantic_rules import validate_canonical_field
from backend.history import log_experiment_result, summarize_experiment_history
from backend.instrumentation.storage import InstrumentationStorage
from backend.recommend import recommend_next_experiment
from backend.reports import build_run_report


class CanonicalFlowTests(unittest.TestCase):
    def test_canonical_producers_match_governance_registry(self) -> None:
        validate_canonical_field("hotspot", "backend/derive/hotspot_ranker.py")
        validate_canonical_field("run_quality", "backend/instrumentation/collector.py")
        validate_canonical_field("confidence", "backend/history/confidence.py")
        validate_canonical_field("comparison", "backend/derive/run_comparator.py")

    def test_end_to_end_canonical_flow_stays_coherent(self) -> None:
        with _sample_project() as (project_root, storage):
            compare_payload = run_experiment(
                "compare_runs",
                project_root=project_root,
                baseline_run_id="run-a",
                current_run_id="run-b",
                storage=storage,
            )
            logged_record = log_experiment_result(
                project_root,
                compare_payload,
                baseline_run_id="run-a",
                current_run_id="run-b",
            )
            history_summary = summarize_experiment_history(
                project_root,
                target="backend/scanner/python_parser/python_scanner.py",
                experiment="compare_runs",
            )
            action_packet = generate_action_packet("run-b", project_root=project_root, storage=storage)
            context_pack = build_context_pack(project_root, "run-b", "current", mode="short", storage=storage)
            recommendation = recommend_next_experiment(
                "backend/scanner/python_parser/python_scanner.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )

            report = build_run_report(
                context_pack["runtime"]["display_run"],
                context_pack["runtime"]["selected_run"] if context_pack["runtime"]["display_run"] != context_pack["runtime"]["selected_run"] else None,
                title="Canonical Flow Report",
            )

        expected_target = "backend/scanner/python_parser/python_scanner.py"
        self.assertEqual(compare_payload["result"]["derived"]["file_deltas"][0]["file_path"], expected_target)
        self.assertEqual(logged_record["target"], expected_target)
        self.assertEqual(history_summary["target"], expected_target)
        self.assertEqual(action_packet["primary_target"]["path"], expected_target)
        self.assertEqual(context_pack["compute"]["hot_files"][0]["file_path"], expected_target)
        self.assertEqual(context_pack["canonical_summary"]["hotspots"][0]["file_path"], expected_target)
        self.assertEqual(report["hotspots"][0]["file_path"], expected_target)
        self.assertEqual(recommendation["target"], expected_target)


class _sample_project:
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
                        "file_path": "backend/scanner/python_parser/python_scanner.py",
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
                                    "file_path": "backend/scanner/python_parser/python_scanner.py",
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
