from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def chain_artifact_path(project_root: Path, chain_id: str) -> Path:
    root = Path(project_root).expanduser().resolve() / ".benchchain"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{chain_id}.json"


def load_chain_artifact(project_root: Path, chain_id: str) -> dict[str, Any]:
    path = chain_artifact_path(project_root, chain_id)
    if not path.exists():
        return {
            "chain_id": chain_id,
            "diff_id": None,
            "review_target": None,
            "recommended_bluebench_action": None,
            "bluebench_run_id": None,
            "runtime_result": None,
            "status": "recommended",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def write_verified_chain_result(
    project_root: Path,
    *,
    chain_id: str,
    review_target: str,
    bluebench_run_id: str,
    comparison: dict[str, Any],
) -> Path:
    artifact = load_chain_artifact(project_root, chain_id)
    artifact["chain_id"] = chain_id
    artifact["review_target"] = review_target
    artifact["bluebench_run_id"] = bluebench_run_id
    artifact["runtime_result"] = {
        "runtime_delta_ms": comparison.get("runtime_delta_ms"),
        "verdict": _comparison_verdict(comparison),
    }
    artifact["status"] = "verified"
    path = chain_artifact_path(project_root, chain_id)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _comparison_verdict(comparison: dict[str, Any]) -> str:
    if not bool(comparison.get("schema_compatible", True)):
        return "inconclusive"
    runtime_delta_ms = comparison.get("runtime_delta_ms")
    try:
        delta = float(runtime_delta_ms)
    except (TypeError, ValueError):
        return "inconclusive"
    if delta < 0:
        return "confirmed"
    if delta > 0:
        return "rejected"
    return "inconclusive"
