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

    def test_parser_accepts_markdown_fenced_section_block(self) -> None:
        text = """Run
```yaml
name: "bluebench_real_verify"
project_root: "/Users/kogaryu/dev/bluebench"
interpreter_path: "/Users/kogaryu/dev/bluebench/.venv/bin/python"
```"""
        parsed = parse_yaml_subset(text)
        self.assertEqual(parsed["name"], "bluebench_real_verify")
        self.assertEqual(parsed["project_root"], "/Users/kogaryu/dev/bluebench")

    def test_parser_accepts_fenced_list_content(self) -> None:
        text = """```yaml
kind: "custom_script"
script_path: "/Users/kogaryu/dev/bluebench/backend/triage/cli.py"
args:
  - "--project-root"
  - "/Users/kogaryu/dev/bluebench"
  - "--mode"
  - "full"
```"""
        parsed = parse_yaml_subset(text)
        self.assertEqual(parsed["kind"], "custom_script")
        self.assertEqual(parsed["args"][0], "--project-root")

    def test_parser_extracts_named_section_from_full_multi_section_response(self) -> None:
        pasted = """Run
```yaml
name: "bluebench_real_verify"
project_root: "/Users/kogaryu/dev/bluebench"
interpreter_path: "/Users/kogaryu/dev/bluebench/.venv/bin/python"
```

Hardware
```yaml
profile: "mini_pc_n100_16gb"
overrides:
  cpu_limit: 2
  memory_mb: 4096
```

Scenario
```yaml
kind: "custom_script"
script_path: "/Users/kogaryu/dev/bluebench/backend/triage/cli.py"
args:
  - "--project-root"
  - "/Users/kogaryu/dev/bluebench"
  - "--mode"
  - "full"
```"""
        run_section = parse_yaml_subset(pasted, section_name="Run")
        hardware_section = parse_yaml_subset(pasted, section_name="Hardware")
        scenario_section = parse_yaml_subset(pasted, section_name="Scenario")
        self.assertEqual(run_section["name"], "bluebench_real_verify")
        self.assertEqual(hardware_section["profile"], "mini_pc_n100_16gb")
        self.assertEqual(scenario_section["kind"], "custom_script")
        self.assertEqual(scenario_section["args"][3], "full")

    def test_parser_preserves_module_name_field(self) -> None:
        parsed = parse_yaml_subset(
            """Scenario
```yaml
kind: "custom_script"
module_name: "backend.triage.cli"
args:
  - "--project-root"
  - "/Users/kogaryu/dev/bluebench"
```""",
            section_name="Scenario",
        )
        self.assertEqual(parsed["module_name"], "backend.triage.cli")

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
