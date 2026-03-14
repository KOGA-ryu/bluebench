from __future__ import annotations

from pathlib import Path
import unittest

from backend.core.graph_engine.graph_manager import GraphManager


class GraphManagerTreeTests(unittest.TestCase):
    def test_build_codebase_tree_aggregates_folders_and_compute(self) -> None:
        manager = GraphManager()
        manager.clear()
        manager.add_node("repo", "repo", "subsystem")
        manager.add_node("pkg/a.py", "a", "module", parent="repo", file_path="pkg/a.py", line_number=1)
        manager.add_node("pkg/nested/b.py", "b", "module", parent="repo", file_path="pkg/nested/b.py", line_number=1)
        manager.add_node("pkg/a.py::fast", "fast", "function", parent="pkg/a.py", file_path="pkg/a.py", line_number=3)
        manager.add_node("pkg/nested/b.py::slow", "slow", "function", parent="pkg/nested/b.py", file_path="pkg/nested/b.py", line_number=7)
        manager.set_metadata("pkg/a.py::fast", "compute_score", 2)
        manager.set_metadata("pkg/nested/b.py::slow", "compute_score", 11)

        tree = manager.build_codebase_tree(Path("/tmp/repo"), ["pkg/a.py", "pkg/nested/b.py"])

        root_children = tree["children"]
        self.assertEqual(len(root_children), 1)
        pkg_folder = root_children[0]
        self.assertEqual(pkg_folder["name"], "pkg")
        self.assertEqual(pkg_folder["compute_tally"], 13)
        self.assertEqual(pkg_folder["compute_tier"], 9)

        child_names = [child["name"] for child in pkg_folder["children"]]
        self.assertEqual(child_names, ["nested", "a.py"])

        nested_folder = next(child for child in pkg_folder["children"] if child["name"] == "nested")
        b_file = nested_folder["children"][0]
        self.assertEqual(b_file["compute_tally"], 11)
        self.assertEqual(b_file["compute_tier"], 9)


if __name__ == "__main__":
    unittest.main()
