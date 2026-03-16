from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.context import build_context_pack, build_context_pack_from_session, export_context_json, export_context_markdown, save_session_state
from backend.instrumentation.storage import InstrumentationStorage


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "triage" / "sample_app"


class ContextPackTests(unittest.TestCase):
    def test_build_context_pack_tiny_short_full(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = InstrumentationStorage(Path(tmp_dir) / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-context",
                    "run_name": "context_run",
                    "project_root": str(FIXTURE_ROOT.resolve()),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-context",
                {
                    "hottest_files": [{"file_path": "app/service.py", "rolling_score": 70.0, "total_time_ms": 300.0}],
                    "biggest_score_deltas": [{"file_path": "app/service.py", "score_delta": 8.0}],
                    "failure_count": 0,
                },
                [
                    {
                        "symbol_key": "app/service.py::load_items",
                        "display_name": "load_items",
                        "file_path": "app/service.py",
                        "self_time_ms": 80.0,
                        "total_time_ms": 300.0,
                        "call_count": 10,
                        "exception_count": 0,
                        "last_exception_type": None,
                        "normalized_compute_score": 78.0,
                    }
                ],
                [
                    {
                        "file_path": "app/service.py",
                        "total_self_time_ms": 80.0,
                        "total_time_ms": 300.0,
                        "call_count": 10,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 78.0,
                        "rolling_score": 70.0,
                    }
                ],
            )
            tiny = build_context_pack(
                FIXTURE_ROOT,
                "run-context",
                "current",
                mode="tiny",
                storage=storage,
                focus_targets=[{"file_path": "app/service.py", "reason": "top_hot_file", "confidence": "high"}],
                open_files=["app/service.py"],
            )
            short = build_context_pack(FIXTURE_ROOT, "run-context", "current", mode="short", storage=storage)
            full = build_context_pack(FIXTURE_ROOT, "run-context", "current", mode="full", storage=storage)

        self.assertEqual(tiny["mode"], "tiny")
        self.assertEqual(short["mode"], "short")
        self.assertEqual(full["mode"], "full")
        self.assertLessEqual(len(tiny["compute"]["hot_files"]), 5)
        self.assertLessEqual(len(tiny["actions"]), 3)
        self.assertIn("triage", full)
        self.assertEqual(tiny["session"]["focus_targets"][0]["file_path"], "app/service.py")
        self.assertTrue(tiny["evidence_types"]["measured"])

    def test_context_exporters_write_files(self) -> None:
        context_pack = {
            "mode": "short",
            "project": {"name": "sample_app", "root": "/tmp/sample_app", "app_type_guess": "desktop", "entry_points": []},
            "session": {"selected_run_id": None, "display_run_id": None, "run_view_mode": "current"},
            "runtime": {"quality_warnings": []},
            "compute": {"hot_files": [], "hot_functions": []},
            "risks": [{"label": "PySide6", "evidence_type": "heuristic"}],
            "actions": [{"title": "Inspect app/main.py", "confidence": "medium"}],
            "hypotheses": [],
            "evidence_types": {"measured": [], "heuristic": [], "inferred": [], "missing": []},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            json_path = export_context_json(context_pack, tmp_path / "bb_context_short.json")
            md_path = export_context_markdown(context_pack, tmp_path / "bb_context_short.md")
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertTrue((tmp_path / "bb_context_short_run_report.md").is_file())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["mode"], "short")
            self.assertIn("sample_app", md_path.read_text(encoding="utf-8"))

    def test_build_context_pack_from_session_uses_saved_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sample_app"
            project_root.mkdir(parents=True, exist_ok=True)
            storage = InstrumentationStorage(project_root / ".bluebench" / "instrumentation.sqlite3")
            storage.initialize_schema()
            storage.insert_run(
                {
                    "run_id": "run-session",
                    "run_name": "session_run",
                    "project_root": str(project_root),
                    "scenario_kind": "custom_script",
                    "hardware_profile": "mini_pc_n100_16gb",
                    "started_at": "2026-03-15T10:00:00+00:00",
                    "finished_at": "2026-03-15T10:01:00+00:00",
                    "status": "completed",
                }
            )
            storage.replace_staged_summaries(
                "run-session",
                {
                    "hottest_files": [{"file_path": "app/main.py", "rolling_score": 55.0, "total_time_ms": 200.0}],
                    "biggest_score_deltas": [],
                    "failure_count": 0,
                },
                [],
                [
                    {
                        "file_path": "app/main.py",
                        "total_self_time_ms": 30.0,
                        "total_time_ms": 200.0,
                        "call_count": 5,
                        "exception_count": 0,
                        "external_pressure_summary": {"external_buckets": {}},
                        "normalized_compute_score": 55.0,
                        "rolling_score": 55.0,
                    }
                ],
            )
            save_session_state(
                project_root,
                {
                    "selected_run_id": "run-session",
                    "run_view_mode": "current",
                    "open_files": ["app/main.py"],
                    "focus_targets": [{"file_path": "app/main.py", "reason": "hot_file", "confidence": "high"}],
                },
            )
            context_pack = build_context_pack_from_session(project_root, mode="tiny", storage=storage)

        self.assertEqual(context_pack["session"]["selected_run_id"], "run-session")
        self.assertEqual(context_pack["session"]["open_files"][0], "app/main.py")


if __name__ == "__main__":
    unittest.main()
