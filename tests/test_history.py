from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from backend.history.confidence import summarize_confidence
from backend.history.experiment_log import (
    build_experiment_record,
    load_experiment_records,
    log_experiment_result,
)
from backend.history.history_summary import summarize_experiment_history


class HistoryTests(unittest.TestCase):
    def test_logging_experiment_outcomes_persists_records(self) -> None:
        payload = {
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
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            record = log_experiment_result(project_root, payload)
            loaded = load_experiment_records(project_root, target="app/main.py", experiment="compare_runs")

        self.assertEqual(record["result"], "improved")
        self.assertEqual(record["target"], "app/main.py")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["baseline_run_id"], "run-a")

    def test_compute_confidence_levels(self) -> None:
        records = [
            _record(runtime_delta_pct=-10.0, result="improved"),
            _record(runtime_delta_pct=-8.0, result="improved"),
            _record(runtime_delta_pct=-6.0, result="improved"),
            _record(runtime_delta_pct=-7.0, result="improved"),
        ]
        summary = summarize_confidence(records)
        self.assertEqual(summary["sample_count"], 4)
        self.assertEqual(summary["confidence"], "medium")
        self.assertGreater(summary["mean_runtime_gain_pct"], 0.0)

    def test_high_variance_lowers_confidence(self) -> None:
        records = [
            _record(runtime_delta_pct=-20.0, result="improved"),
            _record(runtime_delta_pct=-18.0, result="improved"),
            _record(runtime_delta_pct=-1.0, result="improved"),
            _record(runtime_delta_pct=-35.0, result="improved"),
            _record(runtime_delta_pct=-2.0, result="improved"),
            _record(runtime_delta_pct=-28.0, result="improved"),
            _record(runtime_delta_pct=-19.0, result="improved"),
        ]
        summary = summarize_confidence(records)
        self.assertEqual(summary["variance_level"], "high")
        self.assertEqual(summary["confidence"], "medium")

    def test_history_summaries_are_compact(self) -> None:
        payload_a = {
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
        payload_b = {
            "experiment": "compare_runs",
            "result": {
                "evidence": {
                    "baseline": {"run_id": "run-c", "measured": {"runtime_ms": 100.0}},
                    "current": {"run_id": "run-d", "measured": {"runtime_ms": 92.0}},
                },
                "derived": {
                    "runtime_delta_ms": -8.0,
                    "trace_overhead_delta_ms": -1.0,
                    "file_deltas": [{"file_path": "app/main.py", "raw_ms_delta": -4.0}],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            log_experiment_result(project_root, payload_a)
            log_experiment_result(project_root, payload_b)
            summary = summarize_experiment_history(project_root, target="app/main.py", experiment="compare_runs")

        self.assertEqual(summary["target"], "app/main.py")
        self.assertEqual(summary["experiment"], "compare_runs")
        self.assertEqual(summary["history"]["sample_count"], 2)
        self.assertIn("confidence", summary["history"])


def _record(*, runtime_delta_pct: float, result: str) -> dict[str, object]:
    payload = {
        "experiment": "compare_runs",
        "result": {
            "evidence": {
                "baseline": {"run_id": "run-a", "measured": {"runtime_ms": 100.0}},
                "current": {"run_id": "run-b", "measured": {"runtime_ms": 100.0 + runtime_delta_pct}},
            },
            "derived": {
                "runtime_delta_ms": runtime_delta_pct,
                "trace_overhead_delta_ms": 0.0,
                "file_deltas": [{"file_path": "app/main.py", "raw_ms_delta": runtime_delta_pct / 2.0}],
            },
        },
    }
    record = build_experiment_record(payload)
    record["result"] = result
    record["derived"]["runtime_delta_pct"] = runtime_delta_pct
    return record


if __name__ == "__main__":
    unittest.main()
