from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.adapters.codex.action_packet import generate_action_packet
from backend.adapters.codex.cold_start_packet import build_cold_start_packet
from backend.context import build_context_pack
from backend.governance.compression_rules import PACKET_BUDGETS, packet_size_bytes, validate_packet_budget
from backend.history import log_experiment_result, summarize_experiment_history
from backend.instrumentation.storage import InstrumentationStorage
from backend.recommend import recommend_next_experiment


class ContextCompressionTests(unittest.TestCase):
    def test_action_packet_stays_under_budget(self) -> None:
        with _compression_project() as (project_root, storage):
            packet = generate_action_packet("run-b", project_root=project_root, storage=storage)
        self.assertLessEqual(packet_size_bytes(packet), PACKET_BUDGETS["action_packet"]["max_bytes"])
        self.assertEqual(validate_packet_budget("action_packet", packet), [])
        self.assertEqual(sorted(packet["primary_target"].keys()), ["path", "type"])

    def test_next_experiment_packet_stays_under_budget(self) -> None:
        with _compression_project() as (project_root, storage):
            packet = recommend_next_experiment(
                "app/main.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )
        self.assertLessEqual(packet_size_bytes(packet), PACKET_BUDGETS["next_experiment_packet"]["max_bytes"])
        self.assertEqual(validate_packet_budget("next_experiment_packet", packet), [])
        self.assertTrue(packet["recommended_experiment"])

    def test_history_summary_stays_under_budget(self) -> None:
        with _compression_project() as (project_root, _storage):
            log_experiment_result(project_root, _compare_payload())
            summary = summarize_experiment_history(project_root, target="app/main.py", experiment="compare_runs")
        self.assertLessEqual(packet_size_bytes(summary), PACKET_BUDGETS["history_summary"]["max_bytes"])
        self.assertEqual(validate_packet_budget("history_summary", summary), [])

    def test_context_pack_stays_under_budget(self) -> None:
        with _compression_project() as (project_root, storage):
            context_pack = build_context_pack(project_root, "run-b", "current", mode="tiny", storage=storage)
            governed_packet = _governed_context_pack(context_pack)
        self.assertLessEqual(packet_size_bytes(governed_packet), PACKET_BUDGETS["context_pack"]["max_bytes"])
        self.assertEqual(validate_packet_budget("context_pack", governed_packet), [])

    def test_run_comparison_stays_under_budget(self) -> None:
        with _compression_project() as (project_root, storage):
            compare_payload = _compare_payload()
            log_experiment_result(project_root, compare_payload)
            comparison = compare_payload["result"]["derived"]
        self.assertLessEqual(packet_size_bytes(comparison), PACKET_BUDGETS["run_comparison"]["max_bytes"])
        self.assertEqual(validate_packet_budget("run_comparison", comparison), [])

    def test_recommender_output_stays_under_budget(self) -> None:
        with _compression_project() as (project_root, storage):
            packet = recommend_next_experiment(
                "app/main.py",
                run_id="run-b",
                baseline_run_id="run-a",
                project_root=project_root,
                storage=storage,
            )
        self.assertLessEqual(packet_size_bytes(packet), PACKET_BUDGETS["recommender_output"]["max_bytes"])
        self.assertEqual(validate_packet_budget("recommender_output", packet), [])
        self.assertTrue(packet["recommended_experiment"])

    def test_cold_start_packet_stays_under_budget(self) -> None:
        with _cold_start_repo() as repo_root:
            packet = build_cold_start_packet(repo_root)
        self.assertLessEqual(packet_size_bytes(packet), PACKET_BUDGETS["cold_start_packet"]["max_bytes"])
        self.assertEqual(validate_packet_budget("cold_start_packet", packet), [])

    def test_missing_required_key_produces_validation_error(self) -> None:
        packet = {
            "schema_version": "1",
            "packet_type": "hotspot_investigation",
            "run_id": "run-b",
            "primary_target": {"type": "file", "path": "app/main.py"},
            "recommended_actions": [],
        }
        violations = validate_packet_budget("action_packet", packet)
        self.assertTrue(any("missing required key 'supporting_evidence'" in item for item in violations))

    def test_forbidden_key_produces_validation_error(self) -> None:
        packet = {
            "schema_version": "1",
            "packet_type": "hotspot_investigation",
            "run_id": "run-b",
            "primary_target": {"type": "file", "path": "app/main.py"},
            "supporting_evidence": {},
            "recommended_actions": [],
            "full_report_text": "bad",
        }
        violations = validate_packet_budget("action_packet", packet)
        self.assertTrue(any("forbidden key 'full_report_text'" in item for item in violations))

    def test_oversized_packet_produces_validation_error(self) -> None:
        packet = {
            "schema_version": "1",
            "packet_type": "hotspot_investigation",
            "run_id": "run-b",
            "primary_target": {"type": "file", "path": "app/main.py"},
            "supporting_evidence": {"measured": [{"key": "x", "value": "y" * 4000}], "derived": [], "inferred": []},
            "recommended_actions": [{"action": "inspect_file", "target": "app/main.py", "confidence": "high"}],
        }
        violations = validate_packet_budget("action_packet", packet)
        self.assertTrue(any("serialized size exceeds" in item for item in violations))

    def test_excessive_summary_lines_produce_validation_error(self) -> None:
        packet = {
            "schema_version": "1",
            "summary": {
                "summary_lines": ["one", "two", "three", "four", "five", "six", "seven"],
            },
        }
        violations = validate_packet_budget("context_pack", packet)
        self.assertTrue(any("summary line count exceeds" in item for item in violations))

    def test_excessive_recommended_actions_produce_validation_error(self) -> None:
        packet = {
            "schema_version": "1",
            "packet_type": "hotspot_investigation",
            "run_id": "run-b",
            "primary_target": {"type": "file", "path": "app/main.py"},
            "supporting_evidence": {"measured": [], "derived": [], "inferred": []},
            "recommended_actions": [
                {"action": "inspect_file", "target": "app/main.py", "confidence": "high"},
                {"action": "run_experiment", "target": "app/main.py", "confidence": "high"},
                {"action": "inspect_file", "target": "app/main.py", "confidence": "high"},
                {"action": "inspect_file", "target": "app/main.py", "confidence": "high"},
            ],
        }
        violations = validate_packet_budget("action_packet", packet)
        self.assertTrue(any("recommended action count exceeds" in item for item in violations))

    def test_excessive_hotspots_in_context_pack_produce_validation_error(self) -> None:
        packet = _governed_context_pack(
            {
                "compute": {"hot_files": [{"file_path": f"app/{index}.py"} for index in range(6)]},
                "canonical_summary": {"summary_lines": ["a"]},
                "evidence_types": {},
            }
        )
        violations = validate_packet_budget("context_pack", packet)
        self.assertTrue(any("hotspot count exceeds" in item for item in violations))


class _compression_project:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.project_root: Path | None = None
        self.storage: InstrumentationStorage | None = None

    def __enter__(self) -> tuple[Path, InstrumentationStorage]:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp_dir.name)
        self.storage = InstrumentationStorage(self.project_root / ".bluebench" / "instrumentation.sqlite3")
        self.storage.initialize_schema()
        for run_id, run_name, finished_at, total_time_ms, rolling_score in (
            ("run-a", "baseline", "2026-03-16T10:01:00+00:00", 45.0, 80.0),
            ("run-b", "current", "2026-03-16T11:01:00+00:00", 42.0, 76.0),
        ):
            self.storage.insert_run(
                {
                    "run_id": run_id,
                    "run_name": run_name,
                    "project_root": str(self.project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-16T10:00:00+00:00",
                    "finished_at": finished_at,
                    "status": "completed",
                }
            )
            self.storage.replace_staged_summaries(
                run_id,
                {"hottest_files": [], "biggest_score_deltas": [], "failure_count": 0},
                [
                    {
                        "symbol_key": "app/main.py::run",
                        "display_name": "run",
                        "file_path": "app/main.py",
                        "self_time_ms": 15.0,
                        "total_time_ms": total_time_ms,
                        "call_count": 4,
                        "exception_count": 0,
                        "last_exception_type": None,
                        "normalized_compute_score": 88.0,
                    }
                ],
                [
                    {
                        "file_path": "app/main.py",
                        "total_self_time_ms": 15.0,
                        "total_time_ms": total_time_ms,
                        "call_count": 4,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 88.0,
                        "rolling_score": rolling_score,
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
                    "run_quality": "weak",
                    "stage_timings_ms": {},
                    "top_files_by_raw_ms": [
                        {"file_path": "app/main.py", "raw_ms": 42.0, "call_count": 4, "rolling_score": 76.0}
                    ],
                }
            ),
            encoding="utf-8",
        )
        return self.project_root, self.storage

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()


def _governed_context_pack(context_pack: dict) -> dict:
    canonical_summary = dict(context_pack.get("canonical_summary") or {})
    return {
        "schema_version": "1",
        "summary": canonical_summary,
        "compute": dict(context_pack.get("compute") or {}),
        "evidence_types": dict(context_pack.get("evidence_types") or {}),
    }


def _compare_payload() -> dict[str, object]:
    return {
        "experiment": "compare_runs",
        "result": {
            "evidence": {
                "baseline": {"run_id": "run-a", "measured": {"runtime_ms": 100.0}},
                "current": {"run_id": "run-b", "measured": {"runtime_ms": 90.0}},
            },
            "derived": {
                "derive_version": "1",
                "runtime_delta_ms": -10.0,
                "trace_overhead_delta_ms": -2.0,
                "stage_deltas": {"triage_generate": -5.0},
                "file_deltas": [{"file_path": "app/main.py", "raw_ms_delta": -5.0}],
                "schema_compatible": True,
                "comparison_warnings": [],
            },
        },
    }


class _cold_start_repo:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        self.tmp_dir = tempfile.TemporaryDirectory()
        repo_root = Path(self.tmp_dir.name)
        for directory in ("engine", "core", "profiles", "tests"):
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
