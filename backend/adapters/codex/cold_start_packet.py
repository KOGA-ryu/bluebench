from __future__ import annotations

from pathlib import Path

from backend.derive.cold_start import derive_cold_start


def build_cold_start_packet(repo_root: Path) -> dict[str, object]:
    derived = derive_cold_start(repo_root)
    return {
        "schema_version": "1",
        "packet_type": "cold_start_investigation",
        "project_type": derived["project_type"],
        "entry_points": derived["entry_points"],
        "primary_subsystems": derived["primary_subsystems"],
        "first_review_targets": derived["first_review_targets"],
        "recommended_next_actions": derived["recommended_next_actions"],
        "confidence": derived["confidence"],
    }
