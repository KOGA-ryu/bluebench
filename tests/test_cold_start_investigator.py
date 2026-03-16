from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.adapters.cli.commands import cold_start_command
from backend.adapters.codex.cold_start_packet import build_cold_start_packet
from backend.governance.compression_rules import PACKET_BUDGETS, packet_size_bytes, validate_packet_budget


REPO_ROOT = Path(__file__).resolve().parents[1]


class ColdStartInvestigatorTests(unittest.TestCase):
    def test_project_type_detection(self) -> None:
        with _sample_repo() as repo_root:
            packet = build_cold_start_packet(repo_root)
        self.assertEqual(packet["project_type"], "python_tool")

    def test_entry_point_detection(self) -> None:
        with _sample_repo() as repo_root:
            packet = build_cold_start_packet(repo_root)
        self.assertEqual(packet["entry_points"], ["main.py", "engine/scanner_engine.py"])

    def test_primary_subsystem_mapping(self) -> None:
        with _sample_repo() as repo_root:
            packet = build_cold_start_packet(repo_root)
        self.assertEqual(packet["primary_subsystems"][:3], ["engine", "core", "profiles"])

    def test_first_review_target_ranking(self) -> None:
        with _sample_repo() as repo_root:
            packet = build_cold_start_packet(repo_root)
        first_target = packet["first_review_targets"][0]
        self.assertEqual(first_target["path"], "engine/scanner_engine.py")
        self.assertIn("likely control path", first_target["reason"])

    def test_packet_shape_and_budget(self) -> None:
        with _sample_repo() as repo_root:
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
        self.assertLessEqual(packet_size_bytes(packet), PACKET_BUDGETS["cold_start_packet"]["max_bytes"])
        self.assertEqual(validate_packet_budget("cold_start_packet", packet), [])

    def test_cli_summary_output(self) -> None:
        with _sample_repo() as repo_root:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "run_bluebench.py"),
                    "cold-start",
                    "--repo",
                    str(repo_root),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("BlueBench Cold Start", completed.stdout)
        self.assertIn("engine/scanner_engine.py", completed.stdout)

    def test_adapter_command_wraps_packet_and_summary(self) -> None:
        with _sample_repo() as repo_root:
            payload = cold_start_command(repo_root)
        self.assertEqual(sorted(payload.keys()), ["cold_start_packet", "formatted_summary"])
        self.assertIn("Suggested Next Actions:", payload["formatted_summary"])


class _sample_repo:
    def __init__(self) -> None:
        self.tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.repo_root: Path | None = None

    def __enter__(self) -> Path:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp_dir.name)
        for directory in ("engine", "core", "profiles", "tests"):
            (self.repo_root / directory).mkdir(parents=True, exist_ok=True)
        (self.repo_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
        (self.repo_root / "engine" / "scanner_engine.py").write_text("def run():\n    return 1\n", encoding="utf-8")
        (self.repo_root / "core" / "client.py").write_text("def fetch():\n    return 1\n", encoding="utf-8")
        (self.repo_root / "profiles" / "top_gainers.json").write_text(json.dumps({"name": "top_gainers"}), encoding="utf-8")
        (self.repo_root / "tests" / "test_engine.py").write_text("def test_engine():\n    assert True\n", encoding="utf-8")
        (self.repo_root / "pyproject.toml").write_text("[project]\nname='sample'\nversion='0.1.0'\n", encoding="utf-8")
        return self.repo_root

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.tmp_dir is not None
        self.tmp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
