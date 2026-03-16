from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from backend.instrumentation.stage_timing import clear_stage_timings, load_stage_timings, record_stage_timing, timed_stage


class StageTimingTests(unittest.TestCase):
    def test_stage_timing_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "stage_timings.json"
            original = os.environ.get("BLUEBENCH_STAGE_TIMINGS_PATH")
            os.environ["BLUEBENCH_STAGE_TIMINGS_PATH"] = str(path)
            try:
                clear_stage_timings()
                record_stage_timing("alpha", 12.5)
                with timed_stage("beta"):
                    pass
                loaded = load_stage_timings()
            finally:
                if original is None:
                    os.environ.pop("BLUEBENCH_STAGE_TIMINGS_PATH", None)
                else:
                    os.environ["BLUEBENCH_STAGE_TIMINGS_PATH"] = original

        self.assertIn("alpha", loaded)
        self.assertIn("beta", loaded)
        self.assertGreaterEqual(loaded["alpha"], 12.5)
