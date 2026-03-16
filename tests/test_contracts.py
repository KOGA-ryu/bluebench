from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.adapters.codex.action_packet import generate_action_packet
from backend.adapters.codex.cold_start_packet import build_cold_start_packet
from backend.history import log_experiment_result, summarize_experiment_history
from backend.instrumentation.storage import InstrumentationStorage
from backend.recommend import recommend_next_experiment


class ContractTests(unittest.TestCase):
    def test_action_packet_contract(self) -> None:
        with _contract_project() as (project_root, storage):
            packet = generate_action_packet("run-b", project_root=project_root, storage=storage)
        self.assertEqual(
            sorted(packet.keys()),
            sorted(
                [
                    "schema_version",
                    "packet_type",
                    "run_id",
                    "baseline_run_id",
                    "primary_target",
                    "supporting_evidence",
                    "recommended_actions",
                    "constraints",
                ]
            ),
        )
        self.assertEqual(packet["packet_type"], "hotspot_investigation")

    def test_history_summary_contract(self) -> None:
        with _contract_project() as (project_root, _storage):
            log_experiment_result(project_root, _compare_payload())
            summary = summarize_experiment_history(project_root, target="app/main.py", experiment="compare_runs")
        self.assertEqual(sorted(summary.keys()), ["experiment", "history", "target"])
        self.assertEqual(sorted(summary["history"].keys()), ["confidence", "improvement_rate", "mean_runtime_gain_pct", "sample_count", "variance"])

    def test_recommendation_packet_contract(self) -> None:
        with _contract_project() as (project_root, storage):
            packet = recommend_next_experiment("app/main.py", run_id="run-b", baseline_run_id="run-a", project_root=project_root, storage=storage)
        self.assertEqual(
            sorted(packet.keys()),
            sorted(
                [
                    "schema_version",
                    "packet_type",
                    "target",
                    "run_id",
                    "recommended_experiment",
                    "reason",
                    "constraints",
                    "confidence",
                ]
            ),
        )
        self.assertEqual(packet["packet_type"], "next_experiment")

    def test_cold_start_packet_contract(self) -> None:
        with _cold_start_repo() as repo_root:
            packet = build_cold_start_packet(repo_root)
        self.assertEqual(
            sorted(packet.keys()),
            sorted(
                [
                    "schema_version",
                    "packet_type",
                    "project_type",
                    "entry_points",
                    "primary_subsystems",
                    "first_review_targets",
                    "recommended_next_actions",
                    "confidence",
                ]
            ),
        )
        self.assertEqual(packet["packet_type"], "cold_start_investigation")


class _contract_project:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.project_root: Path | None = None
        self.storage: InstrumentationStorage | None = None

    def __enter__(self) -> tuple[Path, InstrumentationStorage]:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp_dir.name)
        self.storage = InstrumentationStorage(self.project_root / ".bluebench" / "instrumentation.sqlite3")
        self.storage.initialize_schema()
        for run_id, run_name, runtime_ms in (("run-a", "baseline", 100.0), ("run-b", "current", 90.0)):
            self.storage.insert_run(
                {
                    "run_id": run_id,
                    "run_name": run_name,
                    "project_root": str(self.project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T10:00:00+00:00",
                    "finished_at": "2026-03-16T10:01:00+00:00",
                    "status": "completed",
                }
            )
            self.storage.replace_staged_summaries(
                run_id,
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [],
                [
                    {
                        "file_path": "app/main.py",
                        "total_self_time_ms": 12.0,
                        "total_time_ms": 42.0 if run_id == "run-b" else 45.0,
                        "call_count": 5,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 88.0,
                        "rolling_score": 76.0,
                    }
                ],
            )
        (self.project_root / "bb_performance_report.json").write_text(
            json.dumps(
                {
                    "run_id": "run-b",
                    "run_name": "current",
                    "status": "completed",
                    "instrumented_runtime_ms": 90.0,
                    "trace_overhead_estimate_ms": 10.0,
                    "run_quality": "strong",
                    "stage_timings_ms": {},
                    "top_files_by_raw_ms": [
                        {"file_path": "app/main.py", "raw_ms": 42.0, "call_count": 5, "rolling_score": 76.0}
                    ],
                }
            ),
            encoding="utf-8",
        )
        return self.project_root, self.storage

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()


def _compare_payload() -> dict[str, object]:
    return {
        "experiment": "compare_runs",
        "result": {
            "evidence": {
                "baseline": {"run_id": "run-a", "measured": {"runtime_ms": 100.0}},
                "current": {"run_id": "run-b", "measured": {"runtime_ms": 90.0}},
            },
            "derived": {
                "runtime_delta_ms": -10.0,
                "trace_overhead_delta_ms": -2.0,
                "file_deltas": [{"file_path": "app/main.py", "raw_ms_delta": -5.0}],
            },
        },
    }


class _cold_start_repo:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        self.tmp_dir = tempfile.TemporaryDirectory()
        repo_root = Path(self.tmp_dir.name)
        for directory in ("engine", "core", "profiles"):
            (repo_root / directory).mkdir(parents=True, exist_ok=True)
        (repo_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
        (repo_root / "engine" / "scanner_engine.py").write_text("def run():\n    return 1\n", encoding="utf-8")
        (repo_root / "pyproject.toml").write_text("[project]\nname='sample'\nversion='0.1.0'\n", encoding="utf-8")
        return repo_root

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
