from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

try:
    from backend.core.graph_engine.graph_manager import GraphManager
except ModuleNotFoundError:
    from core.graph_engine.graph_manager import GraphManager


class GraphBridge(QObject):
    nodeSelectionChanged = Signal("QVariant")
    layoutChanged = Signal(str)
    graphUpdated = Signal()
    focusRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.graph_manager = GraphManager()
        self.current_graph_view = self.graph_manager.get_graph()
        self.selected_node_id: str | None = None
        self.last_call_path_total_compute: dict[str, int] = {}

    @Slot(result="QVariant")
    def sendGraph(self) -> dict[str, list[dict[str, object]]]:
        return self.current_graph_view

    def set_graph_view(self, graph_data: dict[str, list[dict[str, object]]]) -> None:
        self.current_graph_view = graph_data
        self.selected_node_id = None

    @Slot(str)
    def setLayout(self, layout_mode: str) -> None:
        self.layoutChanged.emit(layout_mode)

    @Slot(str)
    def focusNode(self, node_id: str) -> None:
        self.focusRequested.emit(node_id)

    @Slot(str, result="QVariant")
    def traceCallPath(self, node_id: str) -> dict[str, object]:
        call_path = self.graph_manager.trace_call_path(node_id)
        total_compute = call_path.get("total_compute")
        if isinstance(total_compute, int):
            self.last_call_path_total_compute[node_id] = total_compute

        selected_node = self.graph_manager.get_node(node_id)
        if selected_node is not None:
            selected_node["call_path_total_compute"] = total_compute if isinstance(total_compute, int) else 0
            payload = {
                "id": node_id,
                "file_path": selected_node.get("file_path"),
                "line_number": selected_node.get("line_number"),
                "node": selected_node,
            }
            self.nodeSelectionChanged.emit(payload)

        return call_path

    @Slot(str, str)
    def addMarker(self, node_id: str, marker_type: str) -> None:
        self.graph_manager.add_marker(node_id, marker_type)
        self._refresh_current_graph_view()
        if self.selected_node_id == node_id:
            self.nodeSelected(node_id)
        self.graphUpdated.emit()

    @Slot(str, result="QVariant")
    def nodeSelected(self, node_id: str) -> dict[str, object] | None:
        self.selected_node_id = node_id

        selected_node = self.graph_manager.get_node(node_id)
        if selected_node is not None:
            selected_node["call_path_total_compute"] = self.last_call_path_total_compute.get(node_id)

        payload = {
            "id": node_id,
            "file_path": selected_node.get("file_path") if selected_node else None,
            "line_number": selected_node.get("line_number") if selected_node else None,
            "node": selected_node,
        }
        self.nodeSelectionChanged.emit(payload)
        return selected_node

    def _refresh_current_graph_view(self) -> None:
        refreshed_nodes = []
        for node in self.current_graph_view.get("nodes", []):
            node_id = str(node.get("id", ""))
            current_node = self.graph_manager.get_node(node_id)
            if current_node is not None:
                refreshed_nodes.append(current_node)

        self.current_graph_view = {
            "nodes": refreshed_nodes,
            "edges": [dict(edge) for edge in self.current_graph_view.get("edges", [])],
        }
