from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

try:
    from backend.core.graph_engine.graph_manager import GraphManager
except ModuleNotFoundError:
    from core.graph_engine.graph_manager import GraphManager


class GraphBridge(QObject):
    nodeSelectionChanged = Signal("QVariant")

    def __init__(self) -> None:
        super().__init__()
        self.graph_manager = GraphManager()
        self.current_graph_view = self.graph_manager.get_graph()
        self.selected_node_id: str | None = None

    @Slot(result="QVariant")
    def sendGraph(self) -> dict[str, list[dict[str, str | None]]]:
        return self.current_graph_view

    def set_graph_view(self, graph_data: dict[str, list[dict[str, str | None]]]) -> None:
        self.current_graph_view = graph_data
        self.selected_node_id = None

    @Slot(str)
    def nodeSelected(self, node_id: str) -> None:
        self.selected_node_id = node_id

        selected_node = self.graph_manager.get_node(node_id)

        payload = {
            "id": node_id,
            "node": selected_node,
        }
        self.nodeSelectionChanged.emit(payload)
