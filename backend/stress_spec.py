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
        "module_name": "",
        "args": ["--cheap-loops", "25000", "--expensive-size", "180", "--expensive-runs", "3"],
    },
    "file_processing": {
        "script_path": "tests/fixtures/instrumentation/external_bucket_workload.py",
        "module_name": "",
        "args": ["--items", "900", "--passes", "5"],
    },
    "compute_heavy": {
        "script_path": "tests/fixtures/instrumentation/recursive_workload.py",
        "module_name": "",
        "args": ["--depth", "10", "--repeats", "4"],
    },
    "custom_script": {
        "script_path": "",
        "module_name": "",
        "args": [],
    },
}

VERIFICATION_PROFILES: dict[str, dict[str, object]] = {
    "smoke": {
        "run": {"name": "bluebench_smoke_verify", "project_root": "", "interpreter_path": ""},
        "hardware": {"profile": "mini_pc_n100_16gb", "overrides": {"cpu_limit": 2, "memory_mb": 4096}},
        "scenario": {"kind": "compute_heavy"},
        "dashboard": {"priority": ["hot_files", "cpu_memory", "event_log", "timeline"]},
        "save_export": {"artifact_path": "runs/bluebench_smoke_verify.bbtest"},
    },
    "real": {
        "run": {"name": "bluebench_real_verify", "project_root": "", "interpreter_path": ""},
        "hardware": {"profile": "mini_pc_n100_16gb", "overrides": {"cpu_limit": 2, "memory_mb": 4096}},
        "scenario": {
            "kind": "custom_script",
            "script_path": "tools/verification/bluebench_real_verify.py",
            "module_name": "",
            "args": [],
        },
        "dashboard": {"priority": ["hot_files", "cpu_memory", "event_log", "timeline"]},
        "save_export": {"artifact_path": "runs/bluebench_real_verify.bbtest"},
    },
    "diagnostic": {
        "run": {"name": "bluebench_triage_diagnostic", "project_root": "", "interpreter_path": ""},
        "hardware": {"profile": "gigagodtier", "overrides": {"cpu_limit": 8, "memory_mb": 16384}},
        "scenario": {
            "kind": "custom_script",
            "script_path": "",
            "module_name": "backend.triage.cli",
            "args": ["--project-root", "", "--mode", "full"],
        },
        "dashboard": {"priority": ["event_log", "timeline", "hot_files", "cpu_memory"]},
        "save_export": {"artifact_path": "runs/bluebench_triage_diagnostic.bbtest"},
    },
}

VERIFICATION_PROFILE_METADATA: dict[str, dict[str, str]] = {
    "smoke": {
        "label": "Smoke · plumbing",
        "note": "Fast fixture-based trust check. Use this to verify runner, aggregation, and UI wiring.",
    },
    "real": {
        "label": "Real · bounded baseline",
        "note": "Recommended BlueBench self-check. Runs the bounded verification script against core backend areas.",
    },
    "diagnostic": {
        "label": "Diagnostic · broad triage",
        "note": "Broader bottleneck discovery path using module execution for triage-heavy investigation.",
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


SECTION_NAMES = ("Run", "Hardware", "Scenario", "Dashboard", "Save / Export")


def parse_yaml_subset(text: str, section_name: str | None = None) -> dict[str, object]:
    normalized_text = _normalize_yaml_subset_text(text, section_name=section_name)
    lines = [raw.rstrip() for raw in normalized_text.splitlines() if raw.strip() and not raw.strip().startswith("#")]
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


def _normalize_yaml_subset_text(text: str, section_name: str | None = None) -> str:
    raw_lines = text.splitlines()
    filtered_lines: list[str] = []
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            filtered_lines.append("")
            continue
        if stripped.startswith("```"):
            continue
        filtered_lines.append(raw.rstrip())

    if section_name:
        section_lines = _extract_named_section(filtered_lines, section_name)
        if section_lines:
            filtered_lines = section_lines

    nonempty_lines = [line for line in filtered_lines if line.strip()]
    if len(nonempty_lines) >= 2:
        first = nonempty_lines[0].strip().rstrip(":")
        second = nonempty_lines[1].strip()
        if first in SECTION_NAMES and ":" in second:
            first_index = filtered_lines.index(nonempty_lines[0])
            filtered_lines = filtered_lines[first_index + 1 :]

    return "\n".join(filtered_lines)


def _extract_named_section(lines: list[str], section_name: str) -> list[str]:
    matched_start: int | None = None
    for index, line in enumerate(lines):
        if _matches_section_heading(line, section_name):
            matched_start = index
            break
    if matched_start is None:
        return lines

    extracted: list[str] = []
    for index in range(matched_start + 1, len(lines)):
        line = lines[index]
        if _matches_any_section_heading(line) and index > matched_start + 1:
            break
        extracted.append(line)
    return extracted


def _matches_any_section_heading(line: str) -> bool:
    return any(_matches_section_heading(line, section_name) for section_name in SECTION_NAMES)


def _matches_section_heading(line: str, section_name: str) -> bool:
    stripped = line.strip()
    normalized = stripped.strip("*#").strip()
    normalized = normalized.rstrip(":").strip()
    return normalized == section_name


def default_section_texts(profile: str = "smoke") -> dict[str, str]:
    spec = verification_profile_spec(profile)
    return {
        "Run": dump_yaml_subset(spec["run"]),
        "Hardware": dump_yaml_subset(spec["hardware"]),
        "Scenario": dump_yaml_subset(spec["scenario"]),
        "Dashboard": dump_yaml_subset(spec["dashboard"]),
        "Save / Export": dump_yaml_subset(spec["save_export"]),
    }


def verification_profile_spec(profile: str) -> dict[str, object]:
    return dict(VERIFICATION_PROFILES.get(profile, VERIFICATION_PROFILES["smoke"]))


def verification_profile_note(profile: str) -> str:
    return str(VERIFICATION_PROFILE_METADATA.get(profile, VERIFICATION_PROFILE_METADATA["smoke"])["note"])


def verification_profile_label(profile: str) -> str:
    return str(VERIFICATION_PROFILE_METADATA.get(profile, VERIFICATION_PROFILE_METADATA["smoke"])["label"])
