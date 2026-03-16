from __future__ import annotations


CANONICAL_PRODUCERS = {
    "hotspot": "backend/derive/hotspot_ranker.py",
    "bottleneck": "backend/derive/summary_builder.py",
    "run_quality": "backend/instrumentation/collector.py",
    "confidence": "backend/history/confidence.py",
    "verified": "tests/test_canonical_flow.py",
    "comparison": "backend/derive/run_comparator.py",
}


def validate_canonical_field(field_name: str, producer_path: str) -> None:
    canonical_path = CANONICAL_PRODUCERS.get(field_name)
    if canonical_path is None:
        raise ValueError(f"Unknown canonical field: {field_name}")
    normalized_path = producer_path.replace("\\", "/")
    if normalized_path != canonical_path:
        raise ValueError(
            f"Canonical field '{field_name}' must be produced by {canonical_path}, not {normalized_path}"
        )
