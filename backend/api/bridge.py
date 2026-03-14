from __future__ import annotations

from copy import deepcopy
import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from layout.engine import compute_layout, invalidate_layout_cache

try:
    from backend.core.graph_engine.graph_manager import GraphManager
except ModuleNotFoundError:
    from core.graph_engine.graph_manager import GraphManager


LOGGER = logging.getLogger(__name__)
DEFAULT_BATCH_SIZE = 25
EXPORT_FILENAME = ".bluebench_layout_export.html"


class GraphBridge(QObject):
    nodeSelectionChanged = Signal("QVariant")
    layoutChanged = Signal(str)
    graphUpdated = Signal()
    focusRequested = Signal(str)
    explorerInspectorRequested = Signal("QVariant")

    def __init__(self) -> None:
        super().__init__()
        self.graph_manager = GraphManager()
        self.current_graph_view: dict[str, object] = {"nodes": [], "reserved_regions": []}
        self.selected_node_id: str | None = None
        self.last_call_path_total_compute: dict[str, int] = {}
        self.project_path: Path | None = None
        self.project_tree: dict[str, object] | None = None
        self.expansion_state: dict[str, bool] = {}
        self.metadata_state: dict[str, bool] = {}
        self.loaded_children: dict[str, int] = {}
        self.parent_index: dict[str, str] = {}

    @Slot(result="QVariant")
    def sendGraph(self) -> dict[str, object]:
        return self.current_graph_view

    def set_graph_view(self, graph_data: dict[str, object]) -> None:
        self.current_graph_view = graph_data
        self.selected_node_id = None

    def set_project_tree(self, project_path: str | Path, tree_data: dict[str, object]) -> None:
        self.project_path = Path(project_path)
        self.project_tree = deepcopy(tree_data)
        self.selected_node_id = None
        self.last_call_path_total_compute.clear()
        self.parent_index.clear()
        invalidate_layout_cache()

        roots = self._root_children()
        self.expansion_state = {
            str(node.get("id")): bool(node.get("type") == "folder")
            for node in roots
            if node.get("type") == "folder"
        }
        self.metadata_state.clear()
        self.loaded_children = {
            str(node.get("id")): DEFAULT_BATCH_SIZE
            for node in self._walk_tree(roots)
            if node.get("type") == "folder"
        }
        self._refresh_layout()

    def clear_project_tree(self) -> None:
        self.project_path = None
        self.project_tree = None
        self.expansion_state.clear()
        self.metadata_state.clear()
        self.loaded_children.clear()
        self.parent_index.clear()
        invalidate_layout_cache()
        self.current_graph_view = {"nodes": [], "reserved_regions": [], "grid_mode": False}

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
        return self._emit_inspector_payload({"id": node_id})

    @Slot("QVariant")
    def openInspectorFromExplorer(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        file_path = payload.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            return
        self.explorerInspectorRequested.emit({"file_path": file_path})

    @Slot(str)
    def expandNode(self, node_id: str) -> None:
        LOGGER.debug("expansion event", extra={"node_id": node_id, "action": "expand"})
        self.expansion_state[node_id] = True
        self.loaded_children[node_id] = max(self.loaded_children.get(node_id, 0), DEFAULT_BATCH_SIZE)
        self._refresh_layout()

    @Slot(str)
    def collapseSubtree(self, node_id: str) -> None:
        LOGGER.debug("expansion event", extra={"node_id": node_id, "action": "collapse"})
        self.expansion_state[node_id] = False
        self._collapse_descendants(node_id)
        self._refresh_layout()

    @Slot(str)
    def toggleMetadata(self, node_id: str) -> None:
        LOGGER.debug("expansion event", extra={"node_id": node_id, "action": "metadata"})
        self.metadata_state[node_id] = not self.metadata_state.get(node_id, False)
        self._refresh_layout()

    @Slot(str)
    def loadMore(self, node_id: str) -> None:
        LOGGER.debug("node batching", extra={"node_id": node_id, "current": self.loaded_children.get(node_id, DEFAULT_BATCH_SIZE)})
        self.loaded_children[node_id] = self.loaded_children.get(node_id, DEFAULT_BATCH_SIZE) + DEFAULT_BATCH_SIZE
        self.expansion_state[node_id] = True
        self._refresh_layout()

    @Slot(str)
    def openRootExclusive(self, node_id: str) -> None:
        if not node_id:
            return

        roots = [str(node.get("id") or "") for node in self._root_children() if str(node.get("id") or "")]
        for root_id in roots:
            self.expansion_state[root_id] = root_id == node_id
            if root_id != node_id:
                self._collapse_descendants(root_id)

        self.loaded_children[node_id] = max(self.loaded_children.get(node_id, 0), DEFAULT_BATCH_SIZE)
        self._refresh_layout()

    @Slot(result=str)
    def exportCurrentLayout(self) -> str:
        if self.project_path is None:
            return ""
        export_path = self.project_path / EXPORT_FILENAME
        export_path.write_text(json.dumps(self.current_graph_view, indent=2), encoding="utf-8")
        LOGGER.debug("layout export", extra={"path": str(export_path)})
        return str(export_path)

    @Slot(str, result=str)
    def exportLayoutDocument(self, document_html: str) -> str:
        if self.project_path is None:
            return ""
        export_path = self.project_path / EXPORT_FILENAME
        export_path.write_text(document_html, encoding="utf-8")
        LOGGER.debug("layout export", extra={"path": str(export_path)})
        return str(export_path)

    def _refresh_current_graph_view(self) -> None:
        if self.project_tree is not None:
            self._refresh_layout()
            return

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

    def _refresh_layout(self) -> None:
        if self.project_tree is None:
            self.current_graph_view = {"nodes": [], "reserved_regions": [], "grid_mode": False}
            return

        roots = self._prepare_roots()
        viewport = {"width": 1600, "height": 900}
        self.parent_index.clear()
        layout = compute_layout(
            roots,
            self.expansion_state,
            self.parent_index,
            viewport,
            False,
        )
        node_details = {str(node["id"]): node for node in self._walk_tree(roots)}
        self.current_graph_view = {
            "nodes": [
                {
                    **layout_node,
                    **node_details.get(str(layout_node["id"]), {}),
                }
                for layout_node in layout["nodes"]
            ],
            "reserved_regions": layout["reserved_regions"],
            "grid_mode": bool(layout.get("grid_mode", False)),
            "document_title": self.project_tree.get("name"),
        }
        self.graphUpdated.emit()

    def _root_children(self) -> list[dict[str, object]]:
        if self.project_tree is None:
            return []
        children = self.project_tree.get("children", [])
        if not isinstance(children, list):
            return []
        return children

    def _prepare_roots(self) -> list[dict[str, object]]:
        roots = deepcopy(self._root_children())
        for node in self._walk_tree(roots):
            node_id = str(node["id"])
            node["expanded"] = self.expansion_state.get(node_id, False)
            node["metadata_expanded"] = self.metadata_state.get(node_id, False)
            if node.get("type") == "folder":
                node["loaded_children"] = self.loaded_children.get(node_id, DEFAULT_BATCH_SIZE)
        return roots

    def _lookup_display_node(self, node_id: str) -> dict[str, object] | None:
        for node in self._walk_tree(self._root_children()):
            if str(node.get("id")) == node_id:
                return dict(node)
        return None

    def _emit_inspector_payload(self, request_payload: dict[str, object]) -> dict[str, object] | None:
        selected_node = self._resolve_canonical_node(request_payload)
        if selected_node is None:
            LOGGER.error(
                "inspector request ignored: node not found",
                extra={"request_payload": request_payload},
            )
            return None

        node_id = str(selected_node.get("id") or "")
        if not node_id:
            LOGGER.error(
                "inspector request ignored: canonical node missing id",
                extra={"request_payload": request_payload},
            )
            return None

        self.selected_node_id = node_id
        selected_node["call_path_total_compute"] = self.last_call_path_total_compute.get(node_id)
        payload = {
            "id": node_id,
            "file_path": selected_node.get("file_path"),
            "line_number": selected_node.get("line_number"),
            "node": selected_node,
        }
        self.nodeSelectionChanged.emit(payload)
        return selected_node

    def _resolve_canonical_node(self, request_payload: dict[str, object]) -> dict[str, object] | None:
        file_path = request_payload.get("file_path")
        if isinstance(file_path, str) and file_path:
            node = self.graph_manager.get_node(file_path)
            if node is not None:
                return node

            for graph_node in self.graph_manager.nodes:
                if str(graph_node.get("file_path") or "") != file_path:
                    continue
                graph_node_id = str(graph_node.get("id") or "")
                if not graph_node_id:
                    continue
                canonical = self.graph_manager.get_node(graph_node_id)
                if canonical is not None:
                    return canonical

        node_id = request_payload.get("id")
        if isinstance(node_id, str) and node_id:
            return self.graph_manager.get_node(node_id)

        return None

    def _collapse_descendants(self, node_id: str) -> None:
        descendants = []
        parent_lookup = {}
        for node in self._walk_tree(self._root_children()):
            current_id = str(node.get("id"))
            for child in node.get("children", []) if isinstance(node.get("children"), list) else []:
                parent_lookup[str(child.get("id"))] = current_id

        stack = [node_id]
        while stack:
            current = stack.pop()
            for child_id, parent_id in list(parent_lookup.items()):
                if parent_id != current:
                    continue
                descendants.append(child_id)
                stack.append(child_id)

        for descendant in descendants:
            self.expansion_state[descendant] = False

    def _walk_tree(self, nodes: list[dict[str, object]]) -> list[dict[str, object]]:
        walked: list[dict[str, object]] = []
        stack = list(reversed(nodes))
        while stack:
            node = stack.pop()
            walked.append(node)
            children = node.get("children", [])
            if isinstance(children, list):
                stack.extend(reversed(children))
        return walked
