from __future__ import annotations

from pathlib import Path
import unittest

from backend.stress_spec import default_section_texts, dump_yaml_subset, parse_yaml_subset

try:
    from backend.stress_engine import RunOutputStack
except ModuleNotFoundError:
    RunOutputStack = None


class StressEngineParsingTests(unittest.TestCase):
    def test_yaml_subset_round_trip_for_expected_spec_shapes(self) -> None:
        source = {
            "profile": "mini_pc_n100_16gb",
            "overrides": {"cpu_limit": 2, "memory_mb": 4096},
            "priority": ["hot_files", "cpu_memory", "timeline"],
        }
        dumped = dump_yaml_subset(source)
        parsed = parse_yaml_subset(dumped)
        self.assertEqual(parsed, source)

    def test_default_sections_are_parseable(self) -> None:
        for section_name, text in default_section_texts().items():
            parsed = parse_yaml_subset(text)
            self.assertIsInstance(parsed, dict, msg=section_name)

    def test_run_output_stack_uses_nested_run_project_root(self) -> None:
        if RunOutputStack is None:
            self.skipTest("PySide6 not available in test environment")
        stack = RunOutputStack.__new__(RunOutputStack)
        project_root = RunOutputStack._resolve_project_root(
            stack,
            {
                "run": {
                    "project_root": "/tmp/example-project",
                }
            },
            Path("/tmp/example-project/app/main.py"),
        )
        self.assertEqual(project_root, Path("/tmp/example-project"))


if __name__ == "__main__":
    unittest.main()
