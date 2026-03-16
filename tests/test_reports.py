from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.reports import build_run_report, export_report_json, export_report_markdown


class ReportExporterTests(unittest.TestCase):
    def test_build_and_export_run_report(self) -> None:
        current = {
            "run_id": "run-1",
            "run_name": "run-1",
            "status": "completed",
            "quality": "strong",
            "measured": {"runtime_ms": 100.0, "trace_overhead_ms": 10.0},
            "files": [{"file_path": "a.py", "raw_ms": 20.0, "call_count": 3}],
        }
        previous = {
            "measured": {"runtime_ms": 120.0, "trace_overhead_ms": 11.0},
            "files": [{"file_path": "a.py", "raw_ms": 25.0, "call_count": 3}],
        }
        report = build_run_report(current, previous, title="Example Report")
        self.assertEqual(report["title"], "Example Report")
        self.assertEqual(report["hotspots"][0]["file_path"], "a.py")
        self.assertEqual(report["comparison"]["runtime_delta_ms"], -20.0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            json_path = export_report_json(report, tmp_path / "report.json")
            md_path = export_report_markdown(report, tmp_path / "report.md")
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertIn("Example Report", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
