from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from backend.api.bridge import GraphBridge
except ModuleNotFoundError:
    from api.bridge import GraphBridge

try:
    from backend.scanner.python_parser.python_scanner import PythonRepoScanner
except ModuleNotFoundError:
    from scanner.python_parser.python_scanner import PythonRepoScanner

try:
    from backend.core.project_manager.project_discovery import ProjectDiscovery
    from backend.core.project_manager.project_loader import ProjectLoader
except ModuleNotFoundError:
    from core.project_manager.project_discovery import ProjectDiscovery
    from core.project_manager.project_loader import ProjectLoader


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_HTML_PATH = PROJECT_ROOT / "frontend" / "graph" / "renderer" / "bluebench_graph.html"
DEV_ROOT = Path("~/dev").expanduser()
APP_STYLESHEET = """
QWidget {
    background-color: #0b0b0e;
    color: #d8d8df;
}
QMainWindow {
    background-color: #0b0b0e;
}
QLabel {
    color: #d8d8df;
    background-color: transparent;
}
QListWidget {
    background-color: #0b0b0e;
    color: #d8d8df;
    border: 1px solid #1a1a22;
    outline: none;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 6px;
}
QListWidget::item:selected {
    background-color: #1a1a22;
    color: #b56cff;
}
QListWidget::item:hover {
    background-color: #14141b;
}
"""


def create_navigator_panel(title: str, width: int) -> tuple[QWidget, QLabel, QTreeWidget, QTreeWidget]:
    panel = QWidget()
    panel.setFixedWidth(width)

    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 18px; font-weight: 600;")

    body_label = QLabel("Select a project from ~/dev to scan and visualize its modules.")
    body_label.setWordWrap(True)
    body_label.setStyleSheet("color: #4b5563;")

    project_list = QTreeWidget()
    project_list.setHeaderHidden(True)
    project_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    module_label = QLabel("Modules")
    module_label.setStyleSheet("font-size: 14px; font-weight: 600;")
    module_list = QTreeWidget()
    module_list.setHeaderHidden(True)
    module_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

    layout.addWidget(title_label)
    layout.addWidget(body_label)
    layout.addWidget(project_list, 1)
    layout.addWidget(module_label)
    layout.addWidget(module_list, 1)

    panel.setStyleSheet(
        "background-color: #0b0b0e; border: 1px solid #1a1a22; border-radius: 10px;"
    )
    return panel, body_label, project_list, module_list


def create_placeholder_panel(title: str, body: str, width: int) -> QWidget:
    panel = QWidget()
    panel.setFixedWidth(width)

    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 18px; font-weight: 600;")

    body_label = QLabel(body)
    body_label.setWordWrap(True)
    body_label.setStyleSheet("color: #4b5563;")

    layout.addWidget(title_label)
    layout.addWidget(body_label)
    layout.addStretch()

    panel.setStyleSheet(
        "background-color: #0b0b0e; border: 1px solid #1a1a22; border-radius: 10px;"
    )
    return panel


def create_inspector_panel(title: str, width: int) -> tuple[QWidget, QLabel]:
    panel = QWidget()
    panel.setFixedWidth(width)

    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 18px; font-weight: 600;")

    body_label = QLabel(
        "Select a node in the graph to inspect its id, type, parent, and relationships."
    )
    body_label.setWordWrap(True)
    body_label.setStyleSheet("color: #4b5563;")

    detail_label = QLabel("No node selected.")
    detail_label.setWordWrap(True)
    detail_label.setStyleSheet("color: #122945;")

    layout.addWidget(title_label)
    layout.addWidget(body_label)
    layout.addWidget(detail_label)
    layout.addStretch()

    panel.setStyleSheet(
        "background-color: #0b0b0e; border: 1px solid #1a1a22; border-radius: 10px;"
    )
    return panel, detail_label


class BlueBenchWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Blue Bench")
        self.resize(1440, 900)
        self.graph_bridge = GraphBridge()
        self.project_discovery = ProjectDiscovery(DEV_ROOT)
        self.project_loader = ProjectLoader(
            self.graph_bridge.graph_manager,
            PythonRepoScanner,
        )
        self.current_project_path: Path | None = None

        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        navigator, self.navigator_body, self.project_list, self.module_list = create_navigator_panel(
            "Project Navigator",
            220,
        )

        inspector, self.inspector_detail = create_inspector_panel(
            "Node Inspector",
            260,
        )

        graph_view = QWebEngineView()
        graph_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.graph_view = graph_view
        self.web_channel = QWebChannel(graph_view.page())
        self.web_channel.registerObject("graphBridge", self.graph_bridge)
        graph_view.page().setWebChannel(self.web_channel)
        graph_view.load(QUrl.fromLocalFile(str(GRAPH_HTML_PATH)))

        main_layout.addWidget(navigator)
        main_layout.addWidget(graph_view, 1)
        main_layout.addWidget(inspector)

        self.setCentralWidget(central_widget)
        self._populate_projects()
        self.project_list.itemClicked.connect(self._load_selected_project)
        self.module_list.itemSelectionChanged.connect(self._load_selected_modules)
        self.graph_bridge.nodeSelectionChanged.connect(self._update_inspector)

    def _populate_projects(self) -> None:
        self.project_list.clear()
        self.module_list.clear()
        for project_name in self.project_discovery.discover_projects():
            self.project_list.addTopLevelItem(QTreeWidgetItem([project_name]))

    def _load_selected_project(self, item: QTreeWidgetItem) -> None:
        project_path = DEV_ROOT / item.text(0)
        if not project_path.is_dir():
            return

        file_paths = self.project_loader.load_project(project_path)
        self.current_project_path = project_path
        self.navigator_body.setText(
            f"Project loaded: {project_path.name}\nSelect a module to inspect its local architecture view."
        )
        self._populate_module_tree(file_paths)

        self.graph_bridge.set_graph_view({"nodes": [], "edges": []})
        self.inspector_detail.setText("No node selected.")
        self._refresh_renderer()

    def _populate_module_tree(self, file_paths: list[str]) -> None:
        self.module_list.clear()
        folders: dict[str, QTreeWidgetItem] = {}

        for file_path in file_paths:
            parts = file_path.split("/")
            parent_item: QTreeWidgetItem | None = None
            current_path_parts: list[str] = []

            for part in parts[:-1]:
                current_path_parts.append(part)
                folder_key = "/".join(current_path_parts)
                folder_item = folders.get(folder_key)
                if folder_item is None:
                    folder_item = QTreeWidgetItem([part])
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, None)
                    if parent_item is None:
                        self.module_list.addTopLevelItem(folder_item)
                    else:
                        parent_item.addChild(folder_item)
                    folders[folder_key] = folder_item
                parent_item = folder_item

            file_item = QTreeWidgetItem([parts[-1]])
            file_item.setData(0, Qt.ItemDataRole.UserRole, file_path)
            if parent_item is None:
                self.module_list.addTopLevelItem(file_item)
            else:
                parent_item.addChild(file_item)

        self.module_list.expandToDepth(0)

    def _load_selected_modules(self) -> None:
        selected_paths = []
        for item in self.module_list.selectedItems():
            module_id = item.data(0, Qt.ItemDataRole.UserRole)
            if module_id:
                selected_paths.append(str(module_id))

        if not selected_paths:
            self.graph_bridge.set_graph_view({"nodes": [], "edges": []})
            self.inspector_detail.setText("No node selected.")
            self._refresh_renderer()
            return

        self.graph_bridge.set_graph_view(self._merge_module_views(selected_paths))
        self.inspector_detail.setText("No node selected.")
        self._refresh_renderer()

    def _merge_module_views(self, module_ids: list[str]) -> dict[str, list[dict[str, str | None]]]:
        merged_nodes: dict[str, dict[str, str | None]] = {}
        merged_edges: dict[tuple[str, str, str], dict[str, str]] = {}

        for module_id in module_ids:
            module_view = self.graph_bridge.graph_manager.get_module_view(module_id)
            for node in module_view["nodes"]:
                merged_nodes[str(node["id"])] = node
            for edge in module_view["edges"]:
                edge_key = (edge["source"], edge["target"], edge["type"])
                merged_edges[edge_key] = edge

        return {
            "nodes": list(merged_nodes.values()),
            "edges": list(merged_edges.values()),
        }

    def _refresh_renderer(self) -> None:
        self.graph_view.page().runJavaScript(
            """
            if (window.graphBridge && typeof updateGraph === 'function') {
              window.graphBridge.sendGraph(function(data) {
                updateGraph(data);
              });
            }
            """
        )

    def _update_inspector(self, payload: dict) -> None:
        node = payload.get("node")
        if not node:
            self.inspector_detail.setText(f"Selected node: {payload.get('id', 'unknown')}")
            return

        detail_lines = [
            f"id: {node.get('id', '')}",
            f"name: {node.get('name', '')}",
            f"type: {node.get('type', '')}",
            f"parent: {node.get('parent') or '-'}",
        ]
        self.inspector_detail.setText("\n".join(detail_lines))


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = BlueBenchWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
