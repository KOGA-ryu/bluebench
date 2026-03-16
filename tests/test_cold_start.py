from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from backend.instrumentation.storage import InstrumentationStorage


REPO_ROOT = Path(__file__).resolve().parents[1]


class ColdStartTests(unittest.TestCase):
    def test_console_scripts_are_declared_in_pyproject(self) -> None:
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = pyproject["project"]["scripts"]
        self.assertEqual(scripts["bluebench"], "scripts.run_bluebench:main")
        self.assertEqual(scripts["scanner"], "scripts.run_scanner:main")

    def test_product_wrappers_run_scanner_and_bluebench_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_scanner_root = _create_fake_scanner_root(tmp_path / "scanner")
            env = dict(os.environ)
            env["SCANNER_ROOT"] = str(fake_scanner_root)

            scanner = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "run_scanner.py"), "run"],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(scanner.returncode, 0, scanner.stderr)
            self.assertIn("scanner verify ok", scanner.stdout)

            with _sample_bluebench_project() as project_root:
                bluebench = subprocess.run(
                    [
                        sys.executable,
                        str(REPO_ROOT / "scripts" / "run_bluebench.py"),
                        "stress-canonical",
                        "--project-root",
                        str(project_root),
                        "--iterations",
                        "1",
                    ],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(bluebench.returncode, 0, bluebench.stderr)
                payload = json.loads(bluebench.stdout.strip().splitlines()[-1])
                self.assertEqual(payload["status"], "ok")
                self.assertIn("target", payload)


def _create_fake_scanner_root(root: Path) -> Path:
    (root / "core").mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (root / "main.py").write_text(
        "import sys\n"
        "if len(sys.argv) >= 3 and sys.argv[1] == 'verify' and sys.argv[2] == '--mode':\n"
        "    print('scanner verify ok')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    (root / "core" / "live_probe.py").write_text("print('live probe ok')\n", encoding="utf-8")
    return root


class _sample_bluebench_project:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.project_root: Path | None = None
        self.storage: InstrumentationStorage | None = None

    def __enter__(self) -> Path:
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
        (self.project_root / "bb_performance_report.json").write_text(
            json.dumps(
                {
                    "run_id": "run-b",
                    "run_name": "current",
                    "status": "completed",
                    "instrumented_runtime_ms": 1500.0,
                    "trace_overhead_estimate_ms": 120.0,
                    "run_quality": "strong",
                    "stage_timings_ms": {"triage_generate": 797.28, "context_build": 796.88},
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
        return self.project_root

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()
