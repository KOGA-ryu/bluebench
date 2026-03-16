from __future__ import annotations

import json
from pathlib import Path


def export_report_json(report: dict[str, object], target_path: Path) -> Path:
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return target_path
