from __future__ import annotations

import json
from typing import Any


PACKET_BUDGETS = {
    "action_packet": {
        "max_bytes": 2500,
        "max_top_level_keys": 8,
        "max_summary_lines": 3,
        "max_recommended_actions": 3,
        "required_keys": [
            "schema_version",
            "packet_type",
            "run_id",
            "primary_target",
            "supporting_evidence",
            "recommended_actions",
        ],
        "forbid_keys": [
            "display_run",
            "selected_run",
            "full_report_text",
            "full_file_table",
            "full_stage_table",
        ],
    },
    "next_experiment_packet": {
        "max_bytes": 2200,
        "max_top_level_keys": 8,
        "max_summary_lines": 2,
        "max_reason_items_per_bucket": 3,
        "required_keys": [
            "schema_version",
            "packet_type",
            "target",
            "recommended_experiment",
            "reason",
            "constraints",
            "confidence",
        ],
        "forbid_keys": [
            "full_history_log",
            "full_run_dump",
            "all_hotspots",
            "all_file_deltas",
        ],
    },
    "history_summary": {
        "max_bytes": 2400,
        "max_top_level_keys": 6,
        "max_summary_lines": 3,
        "max_history_metrics": 6,
        "required_keys": [
            "target",
            "experiment",
            "history",
        ],
        "forbid_keys": [
            "raw_records",
            "full_experiment_log",
            "all_timestamps",
            "all_run_ids",
        ],
    },
    "context_pack": {
        "max_bytes": 6000,
        "max_top_level_keys": 6,
        "max_summary_lines": 6,
        "max_hotspots": 5,
        "max_evidence_items_per_type": 5,
        "required_keys": [
            "summary",
            "schema_version",
        ],
        "forbid_keys": [
            "full_source_code",
            "full_report_text",
            "full_history_log",
        ],
    },
    "run_comparison": {
        "max_bytes": 3000,
        "max_top_level_keys": 7,
        "max_file_deltas": 5,
        "max_stage_deltas": 5,
        "max_warnings": 4,
        "required_keys": [
            "derive_version",
            "runtime_delta_ms",
            "trace_overhead_delta_ms",
            "file_deltas",
            "stage_deltas",
            "schema_compatible",
        ],
        "forbid_keys": [
            "baseline_full_run",
            "current_full_run",
            "raw_trace_dump",
        ],
    },
    "recommender_output": {
        "max_bytes": 2200,
        "max_top_level_keys": 8,
        "max_constraints": 4,
        "max_reason_items_total": 6,
        "required_keys": [
            "schema_version",
            "packet_type",
            "target",
            "recommended_experiment",
            "reason",
            "confidence",
        ],
        "forbid_keys": [
            "full_context_pack",
            "full_hotspot_list",
            "full_history_summary",
        ],
    },
    "cold_start_packet": {
        "max_bytes": 2400,
        "max_top_level_keys": 8,
        "max_entry_points": 5,
        "max_subsystems": 5,
        "max_review_targets": 3,
        "max_recommended_actions": 3,
        "required_keys": [
            "schema_version",
            "packet_type",
            "project_type",
            "entry_points",
            "primary_subsystems",
            "first_review_targets",
            "recommended_next_actions",
            "confidence",
        ],
        "forbid_keys": [
            "full_source_code",
            "full_repo_tree",
            "full_report_text",
        ],
    },
}


def packet_size_bytes(packet: dict) -> int:
    return len(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def count_top_level_keys(packet: dict) -> int:
    return len(packet.keys())


def contains_forbidden_key(packet: dict | list | Any, key: str) -> bool:
    if isinstance(packet, dict):
        if key in packet:
            return True
        return any(contains_forbidden_key(value, key) for value in packet.values())
    if isinstance(packet, list):
        return any(contains_forbidden_key(item, key) for item in packet)
    return False


def validate_packet_budget(packet_type: str, packet: dict) -> list[str]:
    budget = PACKET_BUDGETS.get(packet_type)
    if budget is None:
        return [f"Unknown packet type: {packet_type}"]

    violations: list[str] = []

    if packet_size_bytes(packet) > int(budget["max_bytes"]):
        violations.append(f"{packet_type}: serialized size exceeds {budget['max_bytes']} bytes")

    if count_top_level_keys(packet) > int(budget["max_top_level_keys"]):
        violations.append(f"{packet_type}: top-level key count exceeds {budget['max_top_level_keys']}")

    for key in budget["required_keys"]:
        if key not in packet:
            violations.append(f"{packet_type}: missing required key '{key}'")

    for key in budget["forbid_keys"]:
        if contains_forbidden_key(packet, key):
            violations.append(f"{packet_type}: includes forbidden key '{key}'")

    if "max_summary_lines" in budget:
        summary_line_count = _summary_line_count(packet)
        if summary_line_count > int(budget["max_summary_lines"]):
            violations.append(f"{packet_type}: summary line count exceeds {budget['max_summary_lines']}")

    if "max_recommended_actions" in budget:
        action_count = len(list(packet.get("recommended_actions") or packet.get("recommended_next_actions") or []))
        if action_count > int(budget["max_recommended_actions"]):
            violations.append(f"{packet_type}: recommended action count exceeds {budget['max_recommended_actions']}")

    if "max_entry_points" in budget:
        entry_points = list(packet.get("entry_points") or [])
        if len(entry_points) > int(budget["max_entry_points"]):
            violations.append(f"{packet_type}: entry point count exceeds {budget['max_entry_points']}")

    if "max_subsystems" in budget:
        subsystems = list(packet.get("primary_subsystems") or [])
        if len(subsystems) > int(budget["max_subsystems"]):
            violations.append(f"{packet_type}: subsystem count exceeds {budget['max_subsystems']}")

    if "max_review_targets" in budget:
        review_targets = list(packet.get("first_review_targets") or [])
        if len(review_targets) > int(budget["max_review_targets"]):
            violations.append(f"{packet_type}: review target count exceeds {budget['max_review_targets']}")

    if "max_reason_items_per_bucket" in budget:
        reason = dict(packet.get("reason") or {})
        for bucket_name, items in reason.items():
            if isinstance(items, list) and len(items) > int(budget["max_reason_items_per_bucket"]):
                violations.append(
                    f"{packet_type}: reason bucket '{bucket_name}' exceeds {budget['max_reason_items_per_bucket']} items"
                )

    if "max_history_metrics" in budget:
        history = dict(packet.get("history") or {})
        if len(history) > int(budget["max_history_metrics"]):
            violations.append(f"{packet_type}: history metric count exceeds {budget['max_history_metrics']}")

    if "max_hotspots" in budget:
        compute = dict(packet.get("compute") or {})
        hotspots = list(compute.get("hot_files") or [])
        if len(hotspots) > int(budget["max_hotspots"]):
            violations.append(f"{packet_type}: hotspot count exceeds {budget['max_hotspots']}")

    if "max_evidence_items_per_type" in budget:
        evidence_types = dict(packet.get("evidence_types") or {})
        for evidence_type, items in evidence_types.items():
            if isinstance(items, list) and len(items) > int(budget["max_evidence_items_per_type"]):
                violations.append(
                    f"{packet_type}: evidence bucket '{evidence_type}' exceeds {budget['max_evidence_items_per_type']} items"
                )

    if "max_file_deltas" in budget:
        file_deltas = list(packet.get("file_deltas") or [])
        if len(file_deltas) > int(budget["max_file_deltas"]):
            violations.append(f"{packet_type}: file delta count exceeds {budget['max_file_deltas']}")

    if "max_stage_deltas" in budget:
        stage_deltas = dict(packet.get("stage_deltas") or {})
        if len(stage_deltas) > int(budget["max_stage_deltas"]):
            violations.append(f"{packet_type}: stage delta count exceeds {budget['max_stage_deltas']}")

    if "max_warnings" in budget:
        warnings = list(packet.get("comparison_warnings") or [])
        if len(warnings) > int(budget["max_warnings"]):
            violations.append(f"{packet_type}: warning count exceeds {budget['max_warnings']}")

    if "max_constraints" in budget:
        constraints = list(packet.get("constraints") or [])
        if len(constraints) > int(budget["max_constraints"]):
            violations.append(f"{packet_type}: constraint count exceeds {budget['max_constraints']}")

    if "max_reason_items_total" in budget:
        reason = dict(packet.get("reason") or {})
        total_reason_items = sum(len(items) for items in reason.values() if isinstance(items, list))
        if total_reason_items > int(budget["max_reason_items_total"]):
            violations.append(f"{packet_type}: total reason items exceed {budget['max_reason_items_total']}")

    return violations


def _summary_line_count(packet: dict) -> int:
    if "summary" in packet and isinstance(packet.get("summary"), dict):
        return len(list(dict(packet.get("summary") or {}).get("summary_lines") or []))
    if "canonical_summary" in packet and isinstance(packet.get("canonical_summary"), dict):
        return len(list(dict(packet.get("canonical_summary") or {}).get("summary_lines") or []))
    return 0
