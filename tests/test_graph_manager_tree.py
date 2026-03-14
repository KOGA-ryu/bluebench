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

    def test_relationship_index_builds_file_level_forward_and_reverse_maps(self) -> None:
        manager = GraphManager()
        manager.clear()
        manager.add_node("repo", "repo", "subsystem")
        manager.add_node("pkg/engine.py", "engine", "module", parent="repo", file_path="pkg/engine.py", line_number=1)
        manager.add_node("pkg/scanner.py", "scanner", "module", parent="repo", file_path="pkg/scanner.py", line_number=1)
        manager.add_node("pkg/util.py", "util", "module", parent="repo", file_path="pkg/util.py", line_number=1)
        manager.add_node("pkg/engine.py::run", "run", "function", parent="pkg/engine.py", file_path="pkg/engine.py", line_number=3)
        manager.add_node("pkg/scanner.py::scan", "scan", "function", parent="pkg/scanner.py", file_path="pkg/scanner.py", line_number=4)
        manager.add_node("pkg/util.py::clean", "clean", "function", parent="pkg/util.py", file_path="pkg/util.py", line_number=5)
        manager.set_metadata("pkg/engine.py::run", "compute_score", 2)
        manager.set_metadata("pkg/scanner.py::scan", "compute_score", 12)
        manager.set_metadata("pkg/util.py::clean", "compute_score", 5)
        manager.add_edge("pkg/engine.py::run", "pkg/scanner.py::scan", "calls")
        manager.add_edge("pkg/engine.py::run", "pkg/util.py::clean", "calls")
        manager.add_edge("pkg/engine.py", "pkg/util.py", "imports")
        manager.add_edge("pkg/scanner.py", "pkg/util.py", "imports")

        manager.build_relationship_index()

        self.assertEqual(manager.get_file_calls("pkg/engine.py"), ["pkg/scanner.py", "pkg/util.py"])
        self.assertEqual(manager.get_file_called_by("pkg/scanner.py"), ["pkg/engine.py"])
        self.assertEqual(manager.get_file_imports("pkg/engine.py"), ["pkg/util.py"])
        self.assertEqual(manager.get_file_imported_by("pkg/util.py"), ["pkg/scanner.py", "pkg/engine.py"])

    def test_build_codebase_tree_includes_relationship_summary_counts(self) -> None:
        manager = GraphManager()
        manager.clear()
        manager.add_node("repo", "repo", "subsystem")
        manager.add_node("pkg/a.py", "a", "module", parent="repo", file_path="pkg/a.py", line_number=1)
        manager.add_node("pkg/b.py", "b", "module", parent="repo", file_path="pkg/b.py", line_number=1)
        manager.add_node("pkg/a.py::entry", "entry", "function", parent="pkg/a.py", file_path="pkg/a.py", line_number=2)
        manager.add_node("pkg/b.py::helper", "helper", "function", parent="pkg/b.py", file_path="pkg/b.py", line_number=6)
        manager.set_metadata("pkg/a.py::entry", "compute_score", 1)
        manager.set_metadata("pkg/b.py::helper", "compute_score", 7)
        manager.add_edge("pkg/a.py::entry", "pkg/b.py::helper", "calls")
        manager.add_edge("pkg/a.py", "pkg/b.py", "imports")

        tree = manager.build_codebase_tree(Path("/tmp/repo"), ["pkg/a.py", "pkg/b.py"])
        pkg_folder = tree["children"][0]
        a_file = next(child for child in pkg_folder["children"] if child["name"] == "a.py")

        self.assertEqual(
            a_file["relationship_summary"],
            {"calls": 1, "imports": 1, "called_by": 0, "imported_by": 0},
        )

    def test_build_codebase_tree_creates_chapter_index_from_top_level_groups(self) -> None:
        manager = GraphManager()
        manager.clear()
        manager.add_node("repo", "repo", "subsystem")
        manager.add_node("backend/a.py", "a", "module", parent="repo", file_path="backend/a.py", line_number=1)
        manager.add_node("backend/nested/b.py", "b", "module", parent="repo", file_path="backend/nested/b.py", line_number=1)
        manager.add_node("tests/test_a.py", "test_a", "module", parent="repo", file_path="tests/test_a.py", line_number=1)
        manager.add_node("backend/a.py::fast", "fast", "function", parent="backend/a.py", file_path="backend/a.py", line_number=2)
        manager.add_node("backend/nested/b.py::slow", "slow", "function", parent="backend/nested/b.py", file_path="backend/nested/b.py", line_number=5)
        manager.add_node("tests/test_a.py::case", "case", "function", parent="tests/test_a.py", file_path="tests/test_a.py", line_number=3)
        manager.set_metadata("backend/a.py::fast", "compute_score", 3)
        manager.set_metadata("backend/nested/b.py::slow", "compute_score", 9)
        manager.set_metadata("tests/test_a.py::case", "compute_score", 1)

        manager.build_codebase_tree(Path("/tmp/repo"), ["backend/a.py", "backend/nested/b.py", "tests/test_a.py"])

        self.assertEqual(manager.get_chapter_index("backend/nested/b.py"), "1.1")
        self.assertEqual(manager.get_chapter_index("backend/a.py"), "1.2")
        self.assertEqual(manager.get_chapter_index("tests/test_a.py"), "2.1")


if __name__ == "__main__":
    unittest.main()
