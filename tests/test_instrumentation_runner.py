from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from backend.instrumentation.storage import InstrumentationStorage


class InstrumentationRunnerTests(unittest.TestCase):
    def test_script_runner_executes_fixture_and_writes_summary(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        fixture_path = project_root / "tests" / "fixtures" / "instrumentation" / "recursive_workload.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            database_path = Path(tmp_dir) / "instrumentation.sqlite3"
            command = [
                sys.executable,
                "-m",
                "backend.instrumentation.script_runner",
                "--database",
                str(database_path),
                "--project-root",
                str(project_root),
                "--script-path",
                str(fixture_path),
                "--run-name",
                "runner-test",
                "--scenario-kind",
                "instrumented_script",
                "--hardware-profile",
                "test",
                "--",
                "--depth",
                "4",
                "--repeats",
                "2",
            ]
            completed = subprocess.run(command, cwd=project_root, check=True, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0)

            storage = InstrumentationStorage(database_path)
            run_id = storage.fetch_latest_run_id_by_name("runner-test")
            self.assertIsNotNone(run_id)
            if run_id is None:
                return

            for _ in range(20):
                if storage.fetch_run_summary(run_id) is not None:
                    break
                time.sleep(0.1)

            self.assertIsNotNone(storage.fetch_run_summary(run_id))
            self.assertTrue(storage.fetch_file_summaries(run_id, limit=5))
            report_path = project_root / "bb_performance_report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["run_name"], "runner-test")
            self.assertGreaterEqual(report["trace_events"], 1)
            self.assertGreaterEqual(report["functions_seen"], 1)
            self.assertGreaterEqual(report["instrumented_runtime_ms"], 0.0)
            self.assertIn("aggregation_time_ms", report)
            self.assertIn("sqlite_write_time_ms", report)
            self.assertIn("live_state_flush_time_ms", report)
            report_path.unlink(missing_ok=True)

    def test_script_runner_executes_project_style_app_main_from_project_root(self) -> None:
        bluebench_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sample_repo"
            app_dir = project_root / "app"
            app_dir.mkdir(parents=True)
            (project_root / "shared_value.py").write_text(
                'VALUE = "ok-from-project-root"\n',
                encoding="utf-8",
            )
            (app_dir / "main.py").write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "import shared_value",
                        "",
                        'Path("runner_output.txt").write_text(shared_value.VALUE, encoding="utf-8")',
                        'print(shared_value.VALUE)',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            database_path = Path(tmp_dir) / "instrumentation.sqlite3"
            command = [
                sys.executable,
                "-m",
                "backend.instrumentation.script_runner",
                "--database",
                str(database_path),
                "--project-root",
                str(project_root),
                "--script-path",
                str(app_dir / "main.py"),
                "--run-name",
                "project-root-runner-test",
                "--scenario-kind",
                "instrumented_script",
                "--hardware-profile",
                "test",
                "--",
            ]
            environment = dict(os.environ)
            environment["PYTHONPATH"] = (
                str(bluebench_root)
                if not environment.get("PYTHONPATH")
                else f"{bluebench_root}{os.pathsep}{environment['PYTHONPATH']}"
            )
            completed = subprocess.run(
                command,
                cwd=bluebench_root,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(
                (project_root / "runner_output.txt").read_text(encoding="utf-8"),
                "ok-from-project-root",
            )

    def test_script_runner_executes_module_target(self) -> None:
        bluebench_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "sample_repo"
            pkg_dir = project_root / "pkg"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
            (pkg_dir / "runner.py").write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        'Path("module_runner_output.txt").write_text("module-ok", encoding="utf-8")',
                        'print("module-ok")',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            database_path = Path(tmp_dir) / "instrumentation.sqlite3"
            command = [
                sys.executable,
                "-m",
                "backend.instrumentation.script_runner",
                "--database",
                str(database_path),
                "--project-root",
                str(project_root),
                "--module-name",
                "pkg.runner",
                "--run-name",
                "module-runner-test",
                "--scenario-kind",
                "instrumented_script",
                "--hardware-profile",
                "test",
                "--",
            ]
            environment = dict(os.environ)
            environment["PYTHONPATH"] = (
                str(bluebench_root)
                if not environment.get("PYTHONPATH")
                else f"{bluebench_root}{os.pathsep}{environment['PYTHONPATH']}"
            )
            completed = subprocess.run(
                command,
                cwd=bluebench_root,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(
                (project_root / "module_runner_output.txt").read_text(encoding="utf-8"),
                "module-ok",
            )


if __name__ == "__main__":
    unittest.main()
