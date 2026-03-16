from __future__ import annotations

import unittest

from backend.governance.semantic_rules import CANONICAL_PRODUCERS, validate_canonical_field


class SemanticProducerTests(unittest.TestCase):
    def test_hotspot_ranking_comes_from_canonical_derive_module(self) -> None:
        validate_canonical_field("hotspot", "backend/derive/hotspot_ranker.py")

    def test_run_quality_comes_from_collector(self) -> None:
        validate_canonical_field("run_quality", "backend/instrumentation/collector.py")

    def test_confidence_comes_from_history_confidence_module(self) -> None:
        validate_canonical_field("confidence", "backend/history/confidence.py")

    def test_comparison_comes_from_run_comparator(self) -> None:
        validate_canonical_field("comparison", "backend/derive/run_comparator.py")

    def test_canonical_producers_are_unique(self) -> None:
        producers = list(CANONICAL_PRODUCERS.values())
        self.assertEqual(len(producers), len(set(producers)))

    def test_wrong_producer_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be produced by"):
            validate_canonical_field("hotspot", "backend/main.py")


if __name__ == "__main__":
    unittest.main()
