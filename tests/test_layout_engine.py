from __future__ import annotations

import unittest

from layout.engine import compute_layout, invalidate_layout_cache
from layout.interval_map import ColumnIntervalMap


def make_node(
    node_id: str,
    *,
    name: str | None = None,
    node_type: str = "folder",
    compute_tier: int = 3,
    compute_tally: int = 0,
    children: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "name": name or node_id,
        "type": node_type,
        "compute_tier": compute_tier,
        "compute_tally": compute_tally,
        "children": children or [],
        "expanded": False,
        "metadata_expanded": False,
    }


class IntervalMapTests(unittest.TestCase):
    def test_find_free_start_skips_reserved_intervals(self) -> None:
        intervals = ColumnIntervalMap()
        intervals.reserve(1, 0, 120)
        intervals.reserve(1, 240, 360)

        self.assertEqual(intervals.find_free_start(1, 0, 120), 120)
        self.assertEqual(intervals.find_free_start(1, 120, 120), 120)
        self.assertEqual(intervals.find_free_start(1, 150, 120), 360)


class LayoutEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        invalidate_layout_cache()

    def test_children_sorted_by_compute_tier(self) -> None:
        tree = [
            make_node(
                "root",
                children=[
                    make_node("low", node_type="file", compute_tier=3),
                    make_node("high", node_type="file", compute_tier=9),
                    make_node("mid", node_type="file", compute_tier=6),
                ],
            )
        ]

        layout = compute_layout(tree, {"root": True}, {}, (1280, 720), False)
        child_nodes = [node for node in layout["nodes"] if node["parent_id"] == "root"]

        self.assertEqual([node["id"] for node in child_nodes], ["high", "mid", "low"])
        self.assertEqual([node["y"] for node in child_nodes], [0, 210, 420])

    def test_root_lanes_alternate_between_column_one_and_two(self) -> None:
        tree = [
            make_node("a", children=[make_node("a1", node_type="file")]),
            make_node("b", children=[make_node("b1", node_type="file")]),
            make_node("c", children=[make_node("c1", node_type="file")]),
        ]

        layout = compute_layout(tree, {"a": True, "b": True, "c": True}, {}, (1280, 720), False)
        columns = {node["id"]: node["column"] for node in layout["nodes"]}

        self.assertEqual(columns["a1"], 1)
        self.assertEqual(columns["b1"], 2)
        self.assertEqual(columns["c1"], 1)

    def test_collapsing_does_not_reclaim_reserved_space(self) -> None:
        tree = [
            make_node("root", compute_tier=9, children=[make_node("child1", node_type="file"), make_node("child2", node_type="file")]),
            make_node("middle", compute_tier=6, children=[make_node("middle_child", node_type="file")]),
            make_node("later", compute_tier=3, children=[make_node("later_child", node_type="file")]),
        ]

        expanded_layout = compute_layout(tree, {"root": True}, {}, (1280, 720), False)
        child1_y = next(node["y"] for node in expanded_layout["nodes"] if node["id"] == "child1")

        collapsed_layout = compute_layout(tree, {}, {}, (1280, 720), False)
        self.assertFalse(any(node["id"] == "child1" for node in collapsed_layout["nodes"]))

        reopened_layout = compute_layout(tree, {"root": True, "later": True}, {}, (1280, 720), False)
        reopened_child1_y = next(node["y"] for node in reopened_layout["nodes"] if node["id"] == "child1")
        later_child_y = next(node["y"] for node in reopened_layout["nodes"] if node["id"] == "later_child")

        self.assertEqual(child1_y, reopened_child1_y)
        self.assertGreaterEqual(later_child_y, 240)

    def test_batch_loading_limits_children_to_twenty_five(self) -> None:
        children = [make_node(f"child-{index}", node_type="file", compute_tier=9) for index in range(30)]
        tree = [make_node("root", children=children)]

        layout = compute_layout(tree, {"root": True}, {}, (1280, 720), False)
        child_nodes = [node for node in layout["nodes"] if node["parent_id"] == "root"]

        self.assertEqual(len(child_nodes), 25)

    def test_grid_mode_locks_after_depth_threshold(self) -> None:
        current = make_node("depth-0")
        root = current
        for depth in range(1, 43):
            child = make_node(f"depth-{depth}")
            current["children"] = [child]
            current = child

        expansion_state = {f"depth-{depth}": True for depth in range(42)}
        layout = compute_layout([root], expansion_state, {}, (800, 600), False)

        self.assertTrue(all("x" in node and "y" in node for node in layout["nodes"]))
        self.assertEqual(max(node["column"] for node in layout["nodes"]), 3)

        follow_up = compute_layout([make_node("other", children=[make_node("leaf", node_type="file")])], {"other": True}, {}, (800, 600), False)
        self.assertEqual(max(node["column"] for node in follow_up["nodes"]), 1)

    def test_grid_mode_can_be_requested_explicitly(self) -> None:
        tree = [make_node("root", children=[make_node("child", node_type="file")])]

        layout = compute_layout(tree, {"root": True}, {}, (800, 600), True)

        self.assertEqual([node["column"] for node in layout["nodes"]], [0, 1])


if __name__ == "__main__":
    unittest.main()
