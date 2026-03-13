from __future__ import annotations


class GraphManager:
    def __init__(self) -> None:
        self.nodes: list[dict[str, str | None]] = []
        self.edges: list[dict[str, str]] = []
        self._node_index: dict[str, dict[str, str | None]] = {}
        self._edge_index: set[tuple[str, str, str]] = set()
        self._seed_example_graph()

    def add_node(
        self,
        node_id: str,
        name: str,
        node_type: str,
        parent: str | None = None,
    ) -> None:
        node = {
            "id": node_id,
            "name": name,
            "type": node_type,
            "parent": parent,
        }
        existing = self._node_index.get(node_id)
        if existing is not None:
            existing.update(node)
            return

        self.nodes.append(node)
        self._node_index[node_id] = node

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

    def has_node(self, node_id: str) -> bool:
        return node_id in self._node_index

    def get_node(self, node_id: str) -> dict[str, str | None] | None:
        node = self._node_index.get(node_id)
        if node is None:
            return None
        return dict(node)

    def list_modules(self) -> list[dict[str, str | None]]:
        modules = [dict(node) for node in self.nodes if node["type"] == "module"]
        return sorted(modules, key=lambda node: str(node["name"]).lower())

    def get_code_modules(self) -> list[dict[str, str | None]]:
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

    def get_graph(self) -> dict[str, list[dict[str, str | None]]]:
        return {
            "nodes": [dict(node) for node in self.nodes],
            "edges": [dict(edge) for edge in self.edges],
        }

    def get_module_view(self, module_id: str) -> dict[str, list[dict[str, str | None]]]:
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
