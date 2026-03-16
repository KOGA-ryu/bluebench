from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.triage.exporter import export_triage_json, export_triage_markdown


class TriageExporterTests(unittest.TestCase):
    def test_exporters_write_expected_files(self) -> None:
        triage = {
            "project": {
                "name": "sample_app",
                "root": "/tmp/sample_app",
                "app_type_guess": "desktop",
                "file_count": 4,
                "entry_points": [{"path": "app/main.py", "score": 100}],
            },
            "runtime_context": {
                "selected_run": {"run_name": "fixture_run", "scenario_kind": "custom_script", "hardware_profile": "mini_pc_n100_16gb"},
                "quality_warnings": ["Only 2 files were seen during instrumentation."],
            },
            "architecture": {
                "suspected_subsystems": [{"name": "app", "role": "hot_subsystem"}],
                "coupling_notes": ["app/service.py has the highest relationship load in the scanned graph."],
            },
            "compute": {
                "hot_files": [{"file_path": "app/service.py", "normalized_compute_score": 92.0, "total_time_ms": 420.0}],
            },
            "operational_risks": {
                "native_dependencies": ["PySide6"],
                "launch_assumptions": ["Top launch candidate is app/main.py"],
            },
            "hypotheses": [{"title": "Hotspot", "confidence": "high", "reasoning": "service dominates"}],
            "recommended_actions": [{"priority": 1, "title": "Inspect app/service.py", "confidence": "high", "reason": "it is hottest"}],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            json_path = export_triage_json(triage, tmp_path / "bb_triage_report.json")
            md_path = export_triage_markdown(triage, tmp_path / "bb_triage_report.md")

            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertIn("sample_app", md_path.read_text(encoding="utf-8"))
            self.assertIn("Inspect app/service.py", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
