from __future__ import annotations


class GraphManager:
    def __init__(self) -> None:
        self.nodes: list[dict[str, object]] = []
        self.edges: list[dict[str, str]] = []
        self._node_index: dict[str, dict[str, object]] = {}
        self._edge_index: set[tuple[str, str, str]] = set()
        self.node_metadata: dict[str, dict[str, object]] = {}
        self._seed_example_graph()

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
        self.node_metadata.setdefault(
            node_id,
            {
                "markers": [],
                "notes": "",
                "compute_score": None,
                "runtime_stats": None,
                "experiments": [],
            },
        )

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

    def has_node(self, node_id: str) -> bool:
        return node_id in self._node_index

    def get_node(self, node_id: str) -> dict[str, object] | None:
        node = self._node_index.get(node_id)
        if node is None:
            return None
        merged = dict(node)
        merged.update(self.get_metadata(node_id))
        return merged

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

        metadata = self.node_metadata.setdefault(
            node_id,
            {
                "markers": [],
                "notes": "",
                "compute_score": None,
                "runtime_stats": None,
                "experiments": [],
            },
        )
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
            return {
                "markers": [],
                "notes": "",
                "compute_score": None,
                "runtime_stats": None,
                "experiments": [],
            }
        return {
            "markers": list(metadata.get("markers", [])) if isinstance(metadata.get("markers", []), list) else [],
            "notes": metadata.get("notes", ""),
            "compute_score": metadata.get("compute_score"),
            "runtime_stats": metadata.get("runtime_stats"),
            "experiments": list(metadata.get("experiments", [])) if isinstance(metadata.get("experiments", []), list) else [],
        }

    def set_metadata(self, node_id: str, key: str, value: object) -> None:
        if node_id not in self._node_index:
            return
        metadata = self.node_metadata.setdefault(
            node_id,
            {
                "markers": [],
                "notes": "",
                "compute_score": None,
                "runtime_stats": None,
                "experiments": [],
            },
        )
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
            dict(self._node_index[node_id])
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

    def _seed_example_graph(self) -> None:
        self.add_node("scanner", "scanner", "subsystem")
        self.add_node("frontend", "frontend", "module")
        self.add_node("backend", "backend", "module")
        self.add_node("repository", "repository", "module")
        self.add_node("models", "models", "module")

        self.add_edge("frontend", "repository", "planned_flow")
        self.add_edge("repository", "backend", "planned_flow")
        self.add_edge("backend", "models", "planned_flow")
