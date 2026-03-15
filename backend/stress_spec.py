from __future__ import annotations

import json

BUILTIN_HARDWARE_PROFILES: dict[str, dict[str, object]] = {
    "raspberry_pi_5_8gb": {
        "cpu_limit": 4,
        "memory_mb": 8192,
        "notes": "arm64 edge device",
    },
    "mini_pc_n100_16gb": {
        "cpu_limit": 4,
        "memory_mb": 16384,
        "notes": "small x86 baseline",
    },
    "gigagodtier": {
        "cpu_limit": 32,
        "memory_mb": 131072,
        "notes": "max confidence desktop/server profile",
    },
}

SCENARIO_DEFAULTS: dict[str, dict[str, object]] = {
    "api_stress": {
        "script_path": "tests/fixtures/instrumentation/cheap_vs_expensive.py",
        "args": ["--cheap-loops", "25000", "--expensive-size", "180", "--expensive-runs", "3"],
    },
    "file_processing": {
        "script_path": "tests/fixtures/instrumentation/external_bucket_workload.py",
        "args": ["--items", "900", "--passes", "5"],
    },
    "compute_heavy": {
        "script_path": "tests/fixtures/instrumentation/recursive_workload.py",
        "args": ["--depth", "10", "--repeats", "4"],
    },
    "custom_script": {
        "script_path": "",
        "args": [],
    },
}


def _quote_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


def dump_yaml_subset(value: object, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(dump_yaml_subset(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_quote_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(dump_yaml_subset(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_quote_scalar(item)}")
        return "\n".join(lines)
    return f"{prefix}{_quote_scalar(value)}"


def parse_yaml_subset(text: str) -> dict[str, object]:
    lines = [raw.rstrip() for raw in text.splitlines() if raw.strip() and not raw.strip().startswith("#")]
    if not lines:
        return {}

    def scalar(raw: str) -> object:
        value = raw.strip()
        if not value:
            return ""
        if value.startswith(("'", '"')):
            return json.loads(value)
        if value in {"true", "false"}:
            return value == "true"
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def parse_block(index: int, indent: int) -> tuple[object, int]:
        mapping: dict[str, object] = {}
        sequence: list[object] | None = None
        while index < len(lines):
            line = lines[index]
            current_indent = len(line) - len(line.lstrip(" "))
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"invalid indentation near: {line.strip()}")
            stripped = line.strip()
            if stripped.startswith("- "):
                if sequence is None:
                    sequence = []
                item_text = stripped[2:].strip()
                if item_text:
                    sequence.append(scalar(item_text))
                    index += 1
                    continue
                item_value, index = parse_block(index + 1, indent + 2)
                sequence.append(item_value)
                continue
            if ":" not in stripped:
                raise ValueError(f"expected key/value pair near: {stripped}")
            key, raw_value = stripped.split(":", 1)
            value_text = raw_value.strip()
            if value_text:
                mapping[key.strip()] = scalar(value_text)
                index += 1
                continue
            next_index = index + 1
            if next_index >= len(lines):
                mapping[key.strip()] = {}
                index = next_index
                continue
            next_indent = len(lines[next_index]) - len(lines[next_index].lstrip(" "))
            if next_indent <= indent:
                mapping[key.strip()] = {}
                index = next_index
                continue
            child_value, index = parse_block(next_index, indent + 2)
            mapping[key.strip()] = child_value
        if sequence is not None:
            if mapping:
                raise ValueError("cannot mix mapping and list at same indentation level")
            return sequence, index
        return mapping, index

    parsed, final_index = parse_block(0, 0)
    if final_index != len(lines):
        raise ValueError("unable to parse complete document")
    if not isinstance(parsed, dict):
        raise ValueError("top-level value must be a mapping")
    return parsed


def default_section_texts() -> dict[str, str]:
    return {
        "Run": dump_yaml_subset({"name": "verify_run", "project_root": "", "interpreter_path": ""}),
        "Hardware": dump_yaml_subset(
            {"profile": "mini_pc_n100_16gb", "overrides": {"cpu_limit": 2, "memory_mb": 4096}}
        ),
        "Scenario": dump_yaml_subset({"kind": "compute_heavy"}),
        "Dashboard": dump_yaml_subset({"priority": ["hot_files", "cpu_memory", "event_log", "timeline"]}),
        "Save / Export": dump_yaml_subset({"artifact_path": "runs/verify_run.bbtest"}),
    }
