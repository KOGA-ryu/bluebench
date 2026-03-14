from __future__ import annotations

from collections import deque
from pathlib import Path


class GraphManager:
    def __init__(self) -> None:
        self.nodes: list[dict[str, object]] = []
        self.edges: list[dict[str, str]] = []
        self._node_index: dict[str, dict[str, object]] = {}
        self._edge_index: set[tuple[str, str, str]] = set()
        self.node_metadata: dict[str, dict[str, object]] = {}
        self.relationship_index: dict[str, dict[str, set[str]]] = self._empty_relationship_index()
        self.relationship_file_metrics: dict[str, dict[str, int]] = {}
        self.chapter_index: dict[str, str] = {}
        self._seed_example_graph()

    def _empty_relationship_index(self) -> dict[str, dict[str, set[str]]]:
        return {
            "calls": {},
            "imports": {},
            "called_by": {},
            "imported_by": {},
        }

    def _default_metadata(self) -> dict[str, object]:
        return {
            "markers": [],
            "notes": "",
            "compute_score": None,
            "line_start": None,
            "line_end": None,
            "runtime_stats": None,
            "experiments": [],
        }

    def add_node(
        self,
        node_id: str,
        name: str,
        node_type: str,
        parent: str | None = None,
        file_path: str | None = None,
        line_number: int | None = None,
    ) -> None:
        existing = self._node_index.get(node_id)
        existing_file_path = str(existing.get("file_path")) if existing is not None and existing.get("file_path") is not None else None
        existing_line_number = int(existing.get("line_number")) if existing is not None and existing.get("line_number") is not None else None

        node: dict[str, object] = {
            "id": node_id,
            "name": name,
            "type": node_type,
            "parent": parent,
            "file_path": file_path if file_path is not None else existing_file_path,
            "line_number": line_number if line_number is not None else existing_line_number,
        }
        if existing is not None:
            existing.update(node)
            return

        self.nodes.append(node)
        self._node_index[node_id] = node
        self.node_metadata.setdefault(node_id, self._default_metadata())

    def add_edge(self, source: str, target: str, edge_type: str) -> None:
        edge_key = (source, target, edge_type)
        if edge_key in self._edge_index:
            return

        edge = {
            "source": source,
            "target": target,
            "type": edge_type,
        }
        self.edges.append(edge)
        self._edge_index.add(edge_key)

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self._node_index.clear()
        self._edge_index.clear()
        self.node_metadata.clear()
        self.relationship_index = self._empty_relationship_index()
        self.relationship_file_metrics = {}
        self.chapter_index = {}

    def has_node(self, node_id: str) -> bool:
        return node_id in self._node_index

    def get_node(self, node_id: str) -> dict[str, object] | None:
        node = self._node_index.get(node_id)
        if node is None:
            return None
        merged = dict(node)
        merged.update(self.get_metadata(node_id))
        return merged

    def get_node_by_file_path(self, file_path: str) -> dict[str, object] | None:
        normalized = Path(file_path).as_posix()
        for node in self.nodes:
            if str(node.get("file_path") or "") != normalized:
                continue
            node_id = str(node.get("id") or "")
            if not node_id:
                continue
            return self.get_node(node_id)
        return None

    def build_relationship_index(self) -> None:
        relationship_index = self._empty_relationship_index()
        file_metrics = self._file_metrics()

        for file_path in file_metrics:
            for relation_name in relationship_index:
                relationship_index[relation_name].setdefault(file_path, set())

        node_to_file_path: dict[str, str] = {}
        for node in self.nodes:
            node_type = str(node.get("type") or "")
            file_path = node.get("file_path")
            if node_type not in {"module", "function", "class"} or not isinstance(file_path, str) or not file_path:
                continue
            node_to_file_path[str(node.get("id") or "")] = Path(file_path).as_posix()

        for edge in self.edges:
            edge_type = str(edge.get("type") or "")
            source_path = node_to_file_path.get(str(edge.get("source") or ""))
            target_path = node_to_file_path.get(str(edge.get("target") or ""))
            if not source_path or not target_path or source_path == target_path:
                continue

            if edge_type == "calls":
                relationship_index["calls"].setdefault(source_path, set()).add(target_path)
                relationship_index["called_by"].setdefault(target_path, set()).add(source_path)
            elif edge_type == "imports":
                relationship_index["imports"].setdefault(source_path, set()).add(target_path)
                relationship_index["imported_by"].setdefault(target_path, set()).add(source_path)

        self.relationship_index = relationship_index
        self.relationship_file_metrics = file_metrics

    def get_file_calls(self, file_path: str) -> list[str]:
        return self._sorted_relationships("calls", file_path)

    def get_file_imports(self, file_path: str) -> list[str]:
        return self._sorted_relationships("imports", file_path)

    def get_file_called_by(self, file_path: str) -> list[str]:
        return self._sorted_relationships("called_by", file_path)

    def get_file_imported_by(self, file_path: str) -> list[str]:
        return self._sorted_relationships("imported_by", file_path)

    def get_chapter_index(self, file_path: str) -> str | None:
        return self.chapter_index.get(Path(file_path).as_posix())

    def list_modules(self) -> list[dict[str, object]]:
        modules = [dict(node) for node in self.nodes if node["type"] == "module"]
        return sorted(modules, key=lambda node: str(node["name"]).lower())

    def get_code_modules(self) -> list[dict[str, object]]:
        code_module_ids = {
            edge["source"]
            for edge in self.edges
            if edge["type"] == "contains"
            and self._node_index.get(edge["target"], {}).get("type") in {"class", "function"}
        }
        modules = [
            dict(self._node_index[module_id])
            for module_id in code_module_ids
            if module_id in self._node_index and self._node_index[module_id]["type"] == "module"
        ]
        return sorted(modules, key=lambda node: str(node["name"]).lower())

    def add_marker(self, node_id: str, marker_type: str) -> None:
        if node_id not in self._node_index:
            return

        metadata = self.node_metadata.setdefault(node_id, self._default_metadata())
        markers = metadata.setdefault("markers", [])
        if isinstance(markers, list) and marker_type not in markers:
            markers.append(marker_type)

    def remove_marker(self, node_id: str, marker_type: str) -> None:
        if node_id not in self._node_index:
            return

        markers = self.node_metadata.get(node_id, {}).get("markers", [])
        if isinstance(markers, list) and marker_type in markers:
            markers.remove(marker_type)

    def get_markers(self, node_id: str) -> list[str]:
        if node_id not in self._node_index:
            return []

        markers = self.node_metadata.get(node_id, {}).get("markers", [])
        if not isinstance(markers, list):
            return []
        return list(markers)

    def get_metadata(self, node_id: str) -> dict[str, object]:
        metadata = self.node_metadata.get(node_id)
        if metadata is None:
            return self._default_metadata()
        return {
            "markers": list(metadata.get("markers", [])) if isinstance(metadata.get("markers", []), list) else [],
            "notes": metadata.get("notes", ""),
            "compute_score": metadata.get("compute_score"),
            "line_start": metadata.get("line_start"),
            "line_end": metadata.get("line_end"),
            "runtime_stats": metadata.get("runtime_stats"),
            "experiments": list(metadata.get("experiments", [])) if isinstance(metadata.get("experiments", []), list) else [],
        }

    def set_metadata(self, node_id: str, key: str, value: object) -> None:
        if node_id not in self._node_index:
            return
        metadata = self.node_metadata.setdefault(node_id, self._default_metadata())
        metadata[key] = value

    def get_graph(self) -> dict[str, list[dict[str, object]]]:
        return {
            "nodes": [dict(node) for node in self.nodes],
            "edges": [dict(edge) for edge in self.edges],
        }

    def get_module_view(self, module_id: str) -> dict[str, list[dict[str, object]]]:
        module_node = self._node_index.get(module_id)
        if module_node is None or module_node["type"] != "module":
            return {"nodes": [], "edges": []}

        visible_node_ids = {module_id}
        visible_edge_keys: set[tuple[str, str, str]] = set()

        for edge in self.edges:
            if edge["type"] == "contains" and edge["source"] == module_id:
                visible_node_ids.add(edge["target"])
                visible_edge_keys.add((edge["source"], edge["target"], edge["type"]))

            if edge["type"] == "imports" and edge["source"] == module_id:
                visible_node_ids.add(edge["target"])
                visible_edge_keys.add((edge["source"], edge["target"], edge["type"]))

            if edge["type"] == "imports" and edge["target"] == module_id:
                visible_node_ids.add(edge["source"])
                visible_edge_keys.add((edge["source"], edge["target"], edge["type"]))

        for edge in self.edges:
            edge_key = (edge["source"], edge["target"], edge["type"])
            if edge["type"] == "calls" and edge["source"] in visible_node_ids and edge["target"] in visible_node_ids:
                visible_edge_keys.add(edge_key)

        visible_nodes = [
            self.get_node(node_id)
            for node_id in visible_node_ids
            if node_id in self._node_index
        ]
        visible_edges = [
            dict(edge)
            for edge in self.edges
            if (edge["source"], edge["target"], edge["type"]) in visible_edge_keys
        ]

        return {
            "nodes": sorted(
                visible_nodes,
                key=lambda node: (str(node["type"]), str(node["name"]).lower()),
            ),
            "edges": visible_edges,
        }

    def trace_call_path(self, start_node_id: str, max_depth: int = 5) -> dict[str, object]:
        if not self.has_node(start_node_id):
            return {"nodes": [], "edges": [], "total_compute": 0, "view_mode": "call_path"}

        visited_nodes: set[str] = set()
        discovered_edges: list[dict[str, str]] = []
        discovered_edge_keys: set[tuple[str, str, str]] = set()
        ordered_nodes: list[dict[str, object]] = []
        total_compute = 0
        queue: deque[tuple[str, int]] = deque([(start_node_id, 0)])

        while queue:
            current_node_id, depth = queue.popleft()
            if current_node_id in visited_nodes or depth > max_depth:
                continue

            current_node = self.get_node(current_node_id)
            if current_node is None:
                continue

            visited_nodes.add(current_node_id)
            current_node["call_path_order"] = len(ordered_nodes)
            ordered_nodes.append(current_node)

            compute_score = self.get_metadata(current_node_id).get("compute_score")
            if isinstance(compute_score, int):
                total_compute += compute_score

            if depth == max_depth:
                continue

            for edge in self.edges:
                if edge["type"] != "calls" or edge["source"] != current_node_id:
                    continue

                target_node_id = edge["target"]
                if not self.has_node(target_node_id):
                    continue

                edge_key = (edge["source"], edge["target"], edge["type"])
                if edge_key not in discovered_edge_keys:
                    discovered_edge_keys.add(edge_key)
                    discovered_edges.append(dict(edge))

                if target_node_id not in visited_nodes:
                    queue.append((target_node_id, depth + 1))

        return {
            "nodes": ordered_nodes,
            "edges": discovered_edges,
            "total_compute": total_compute,
            "view_mode": "call_path",
        }

    def build_codebase_tree(self, project_path: str | Path, file_paths: list[str] | None = None) -> dict[str, object]:
        self.build_relationship_index()
        project_root = Path(project_path)
        root_id = project_root.name
        file_node_ids = {
            str(node["id"])
            for node in self.nodes
            if node.get("type") == "module"
            and isinstance(node.get("file_path"), str)
        }
        visible_file_paths = set(file_paths or [])
        if visible_file_paths:
            file_node_ids = {
                node_id
                for node_id in file_node_ids
                if str(self._node_index.get(node_id, {}).get("file_path") or node_id) in visible_file_paths
            }

        root: dict[str, object] = {
            "id": root_id,
            "name": project_root.name,
            "type": "folder",
            "children": [],
            "child_count": 0,
            "expanded": True,
            "metadata_expanded": False,
            "file_path": None,
            "line_number": None,
            "relationship_summary": {
                "calls": 0,
                "imports": 0,
                "called_by": 0,
                "imported_by": 0,
            },
        }
        folders: dict[str, dict[str, object]] = {"": root}

        def ensure_folder(folder_path: str) -> dict[str, object]:
            if folder_path in folders:
                return folders[folder_path]

            parts = folder_path.split("/")
            current_path = []
            parent_folder = root
            for part in parts:
                current_path.append(part)
                joined = "/".join(current_path)
                existing = folders.get(joined)
                if existing is not None:
                    parent_folder = existing
                    continue

                folder_node = {
                    "id": joined,
                    "name": part,
                    "type": "folder",
                    "children": [],
                    "child_count": 0,
                    "expanded": False,
                    "metadata_expanded": False,
                    "file_path": None,
                    "line_number": None,
                    "relationship_summary": {
                        "calls": 0,
                        "imports": 0,
                        "called_by": 0,
                        "imported_by": 0,
                    },
                }
                parent_folder["children"].append(folder_node)
                folders[joined] = folder_node
                parent_folder = folder_node

            return parent_folder

        for node_id in sorted(file_node_ids):
            file_node = self._node_index.get(node_id)
            if file_node is None:
                continue

            relative_path = str(file_node.get("file_path") or node_id)
            parent_path = str(Path(relative_path).parent.as_posix())
            parent_folder = root if parent_path in {".", ""} else ensure_folder(parent_path)
            tally = self._compute_file_tally(node_id)
            parent_folder["children"].append(
                {
                    "id": relative_path,
                    "name": Path(relative_path).name,
                    "type": "file",
                    "children": [],
                    "child_count": 0,
                    "expanded": False,
                    "metadata_expanded": False,
                    "file_path": relative_path,
                    "line_number": 1,
                    "compute_tally": tally,
                    "compute_tier": self._tier_for_tally(tally),
                    "relationship_summary": {
                        "calls": len(self.get_file_calls(relative_path)),
                        "imports": len(self.get_file_imports(relative_path)),
                        "called_by": len(self.get_file_called_by(relative_path)),
                        "imported_by": len(self.get_file_imported_by(relative_path)),
                    },
                }
            )

        self._hydrate_folder_compute(root)
        self._sort_tree_children(root)
        self._build_chapter_index(root)
        return root

    def _compute_file_tally(self, file_node_id: str) -> int:
        tally = 0
        for node in self.nodes:
            if node.get("parent") != file_node_id:
                continue
            compute_score = self.get_metadata(str(node.get("id") or "")).get("compute_score")
            if isinstance(compute_score, int):
                tally += compute_score
        return tally

    def _tier_for_tally(self, tally: int) -> int:
        if tally >= 9:
            return 9
        if tally >= 4:
            return 6
        return 3

    def _hydrate_folder_compute(self, node: dict[str, object]) -> tuple[int, int]:
        children = node.get("children", [])
        if not isinstance(children, list) or not children:
            tally = int(node.get("compute_tally") or 0)
            tier = int(node.get("compute_tier") or self._tier_for_tally(tally))
            node["compute_tally"] = tally
            node["compute_tier"] = tier
            return tally, tier

        total_tally = 0
        highest_tier = 3
        node["child_count"] = len(children)
        for child in children:
            child_tally, child_tier = self._hydrate_folder_compute(child)
            total_tally += child_tally
            highest_tier = max(highest_tier, child_tier)

        node["compute_tally"] = total_tally
        node["compute_tier"] = highest_tier if total_tally > 0 else 3
        return total_tally, int(node["compute_tier"])

    def _sort_tree_children(self, node: dict[str, object]) -> None:
        children = node.get("children", [])
        if not isinstance(children, list):
            return

        children.sort(
            key=lambda child: (
                -int(child.get("compute_tier") or 0),
                str(child.get("type") != "folder"),
                str(child.get("name") or "").lower(),
            )
        )
        for child in children:
            self._sort_tree_children(child)

    def _build_chapter_index(self, root: dict[str, object]) -> None:
        chapter_index: dict[str, str] = {}
        chapter_number = 1

        for child in root.get("children", []) if isinstance(root.get("children"), list) else []:
            files = self._collect_files_in_display_order(child)
            if not files:
                continue
            for file_number, file_path in enumerate(files, start=1):
                chapter_index[file_path] = f"{chapter_number}.{file_number}"
            chapter_number += 1

        self.chapter_index = chapter_index

    def _collect_files_in_display_order(self, node: dict[str, object]) -> list[str]:
        node_type = str(node.get("type") or "")
        if node_type == "file":
            file_path = node.get("file_path")
            if isinstance(file_path, str) and file_path:
                return [Path(file_path).as_posix()]
            return []

        ordered_files: list[str] = []
        children = node.get("children", [])
        if not isinstance(children, list):
            return ordered_files
        for child in children:
            ordered_files.extend(self._collect_files_in_display_order(child))
        return ordered_files

    def _sorted_relationships(self, relation_name: str, file_path: str) -> list[str]:
        normalized_file_path = Path(file_path).as_posix()
        related_paths = self.relationship_index.get(relation_name, {}).get(normalized_file_path, set())
        return sorted(
            related_paths,
            key=lambda path: (
                -int(self.relationship_file_metrics.get(path, {}).get("compute_tier", 3)),
                -int(self.relationship_file_metrics.get(path, {}).get("compute_tally", 0)),
                path.lower(),
            ),
        )

    def _file_metrics(self) -> dict[str, dict[str, int]]:
        metrics: dict[str, dict[str, int]] = {}
        for node in self.nodes:
            if node.get("type") != "module":
                continue
            file_path = node.get("file_path")
            node_id = str(node.get("id") or "")
            if not isinstance(file_path, str) or not file_path or not node_id:
                continue
            normalized_path = Path(file_path).as_posix()
            tally = self._compute_file_tally(node_id)
            metrics[normalized_path] = {
                "compute_tally": tally,
                "compute_tier": self._tier_for_tally(tally),
            }
        return metrics

    def _seed_example_graph(self) -> None:
        self.add_node("scanner", "scanner", "subsystem")
        self.add_node("frontend", "frontend", "module")
        self.add_node("backend", "backend", "module")
        self.add_node("repository", "repository", "module")
        self.add_node("models", "models", "module")

        self.add_edge("frontend", "repository", "planned_flow")
        self.add_edge("repository", "backend", "planned_flow")
        self.add_edge("backend", "models", "planned_flow")
        self.build_relationship_index()
