from __future__ import annotations

from typing import Any


VALID_EVIDENCE_TYPES = {"measured", "derived", "inferred", "missing"}


def make_evidence_label(label_type: str, key: str, value: Any) -> dict[str, Any]:
    normalized = label_type if label_type in VALID_EVIDENCE_TYPES else "missing"
    return {"type": normalized, "key": str(key), "value": value}
