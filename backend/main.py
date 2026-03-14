from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QRect, QRegularExpression, QSettings, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QTextCursor, QSyntaxHighlighter
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QPushButton,
    QComboBox,
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QTextEdit as QTextEditWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QHBoxLayout,
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

HOTKEY_REFERENCE = """Hotkeys

Click node -> select
Double click node -> focus mode
Shift + Click node -> inspect dependencies

Ctrl + T -> tile inspector windows
F -> focus selected node
Esc -> exit focus mode

Scroll -> zoom graph
Drag -> pan graph"""


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeViewer") -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        self.editor.lineNumberAreaPaintEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        line_number = self.editor.lineNumberAt(event.position().y() if hasattr(event, "position") else event.y())
        if line_number is not None:
            self.editor.openLineAnnotation(line_number)
        super().mousePressEvent(event)


class LineAnnotationDialog(QDialog):
    def __init__(self, marker: str, note: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Line Annotation")
        self.resize(320, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        marker_label = QLabel("Marker")
        self.marker_selector = QComboBox()
        self.marker_selector.addItem("note", "note")
        self.marker_selector.addItem("optimization", "optimization")
        self.marker_selector.addItem("refactor", "refactor")
        self.marker_selector.addItem("investigate", "investigate")
        current_index = self.marker_selector.findData(marker)
        if current_index >= 0:
            self.marker_selector.setCurrentIndex(current_index)

        note_label = QLabel("Note")
        self.note_editor = QTextEditWidget()
        self.note_editor.setPlainText(note)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)

        layout.addWidget(marker_label)
        layout.addWidget(self.marker_selector)
        layout.addWidget(note_label)
        layout.addWidget(self.note_editor, 1)
        layout.addWidget(save_button)

    def get_annotation(self) -> dict[str, str]:
        return {
            "marker": str(self.marker_selector.currentData()),
            "note": self.note_editor.toPlainText(),
        }


class CodeViewer(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.highlighter = PythonHighlighter(self.document())
        self.line_annotations: dict[str, dict[int, dict[str, str]]] = {}
        self.current_file_path: str = ""
        self.project_root: Path | None = None
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

    def lineNumberAreaWidth(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def updateLineNumberAreaWidth(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        contents_rect = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(
                contents_rect.left(),
                contents_rect.top(),
                self.lineNumberAreaWidth(),
                contents_rect.height(),
            )
        )

    def lineNumberAreaPaintEvent(self, event) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#111116"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line_number = block_number + 1
                number = str(line_number)
                if self.hasAnnotation(line_number):
                    painter.setPen(QColor("#4aa3ff"))
                else:
                    painter.setPen(QColor("#888888"))
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def highlightCurrentLine(self) -> None:
        if self.isReadOnly():
            return

    def highlightLine(self, line_number: int) -> None:
        self.setExtraSelections([])

        if line_number < 1:
            return

        block = self.document().findBlockByLineNumber(line_number - 1)
        if not block.isValid():
            return

        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)

        line_highlight = QTextEdit.ExtraSelection()
        line_highlight.cursor = cursor
        line_highlight.format = QTextCharFormat()
        line_highlight.format.setBackground(QColor("#2d1f45"))
        line_highlight.format.setProperty(
            QTextCharFormat.Property.FullWidthSelection,
            True,
        )
        self.setExtraSelections([line_highlight])

    def setAnnotationContext(self, project_root: Path | None, file_path: str) -> None:
        self.project_root = project_root
        self.current_file_path = file_path
        self._loadAnnotations()
        self.line_number_area.update()

    def lineNumberAt(self, y_position: float) -> int | None:
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid():
            if block.isVisible() and top <= y_position <= bottom:
                return block_number + 1

            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

        return None

    def openLineAnnotation(self, line_number: int) -> None:
        if not self.current_file_path:
            return

        existing = self.line_annotations.get(self.current_file_path, {}).get(
            line_number,
            {"marker": "note", "note": ""},
        )
        dialog = LineAnnotationDialog(
            str(existing.get("marker", "note")),
            str(existing.get("note", "")),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.line_annotations.setdefault(self.current_file_path, {})[line_number] = dialog.get_annotation()
        self._saveAnnotations()
        self.line_number_area.update()

    def hasAnnotation(self, line_number: int) -> bool:
        return bool(self.line_annotations.get(self.current_file_path, {}).get(line_number))

    def _annotationFilePath(self) -> Path | None:
        if self.project_root is None:
            return None
        return self.project_root / ".bluebench_annotations.json"

    def _loadAnnotations(self) -> None:
        annotation_path = self._annotationFilePath()
        if annotation_path is None or not annotation_path.exists():
            return

        try:
            raw_data = json.loads(annotation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        loaded: dict[str, dict[int, dict[str, str]]] = {}
        for file_path, annotations in raw_data.items():
            loaded[file_path] = {}
            if isinstance(annotations, dict):
                for line_number, annotation in annotations.items():
                    try:
                        loaded[file_path][int(line_number)] = {
                            "marker": str(annotation.get("marker", "note")),
                            "note": str(annotation.get("note", "")),
                        }
                    except (ValueError, AttributeError):
                        continue
        self.line_annotations = loaded

    def _saveAnnotations(self) -> None:
        annotation_path = self._annotationFilePath()
        if annotation_path is None:
            return

        serializable = {
            file_path: {
                str(line_number): annotation
                for line_number, annotation in annotations.items()
            }
            for file_path, annotations in self.line_annotations.items()
        }

        try:
            annotation_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        except OSError:
            return


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self.highlight_rules: list[tuple[QRegularExpression, QTextCharFormat, int | None]] = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#b56cff"))
        keyword_patterns = [
            "and", "as", "assert", "break", "class", "continue", "def", "del",
            "elif", "else", "except", "False", "finally", "for", "from", "global",
            "if", "import", "in", "is", "lambda", "None", "nonlocal", "not", "or",
            "pass", "raise", "return", "True", "try", "while", "with", "yield",
        ]
        for keyword in keyword_patterns:
            self.highlight_rules.append(
                (QRegularExpression(rf"\b{keyword}\b"), keyword_format, None)
            )

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#8fd3ff"))
        self.highlight_rules.append(
            (QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format, None)
        )
        self.highlight_rules.append(
            (QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format, None)
        )

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955"))
        self.highlight_rules.append((QRegularExpression(r"#.*"), comment_format, None))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#dcdcaa"))
        self.highlight_rules.append(
            (QRegularExpression(r"\b\d+(\.\d+)?\b"), number_format, None)
        )

        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#ffd700"))
        self.highlight_rules.append(
            (QRegularExpression(r"\bdef\s+(\w+)"), function_format, 1)
        )

        class_format = QTextCharFormat()
        class_format.setForeground(QColor("#4ec9b0"))
        self.highlight_rules.append(
            (QRegularExpression(r"\bclass\s+(\w+)"), class_format, 1)
        )

    def highlightBlock(self, text: str) -> None:
        for pattern, text_format, capture_group in self.highlight_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                if capture_group is None:
                    start = match.capturedStart()
                    length = match.capturedLength()
                else:
                    start = match.capturedStart(capture_group)
                    length = match.capturedLength(capture_group)

                if start >= 0 and length > 0:
                    self.setFormat(start, length, text_format)


class NodeInspectorWindow(QMainWindow):
    def __init__(
        self,
        graph_manager,
        project_path: Path,
        node: dict,
        on_close: Callable[[str], None],
    ) -> None:
        super().__init__()
        self.graph_manager = graph_manager
        self.project_path = project_path
        self.node = node
        self.node_id = str(node.get("id", ""))
        self.on_close = on_close
        self.layout_locked = False

        self.resize(860, 640)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        self.lock_button = QPushButton("🔒 Lock Layout")
        self.lock_button.clicked.connect(self._toggle_layout_lock)

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.lock_button)

        self.header_title = QLabel()
        self.header_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        self.header_meta = QLabel()
        self.header_meta.setStyleSheet("color: #aaaaaa; font-size: 12px;")

        header_widget = QWidget()
        header_widget.setMaximumHeight(60)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        header_layout.addWidget(self.header_title)
        header_layout.addWidget(self.header_meta)

        self.outline_selector = QComboBox()
        self.outline_selector.currentIndexChanged.connect(self._jump_to_outline_selection)

        self.code_viewer = CodeViewer()
        self.code_viewer.setReadOnly(True)

        code_font = QFont("Menlo")
        code_font.setStyleHint(QFont.StyleHint.Monospace)
        code_font.setPointSize(11)
        self.code_viewer.setFont(code_font)

        layout.addWidget(toolbar)
        layout.addWidget(header_widget)
        layout.addWidget(self.outline_selector)
        layout.addWidget(self.code_viewer, 1)

        self.setCentralWidget(central_widget)
        self.refresh(node)

    def refresh(self, node: dict) -> None:
        self.node = node
        self.node_id = str(node.get("id", ""))
        self.setWindowTitle(str(node.get("name") or self.node_id))

        self.header_title.setText(str(node.get("file_path") or node.get("name") or self.node_id))
        self.header_meta.setText(
            f"{node.get('type', '')} · {node.get('parent') or '-'} · line {node.get('line_number') or '-'}"
        )

        self._update_outline(node)
        self._update_code_viewer(
            str(node.get("file_path") or ""),
            node.get("line_number"),
        )

    def _update_outline(self, node: dict) -> None:
        self.outline_selector.blockSignals(True)
        self.outline_selector.clear()
        self.outline_selector.addItem("Jump to definition...")

        module_id = str(node.get("id") or "") if node.get("type") == "module" else str(node.get("parent") or "")
        if not module_id:
            self.outline_selector.blockSignals(False)
            return

        outline_nodes = [
            graph_node
            for graph_node in self.graph_manager.nodes
            if graph_node.get("parent") == module_id
            and graph_node.get("type") in {"function", "class"}
        ]
        outline_nodes.sort(key=lambda graph_node: int(graph_node.get("line_number") or 0))

        for outline_node in outline_nodes:
            display_name = str(outline_node.get("name") or "")
            if outline_node.get("type") == "function":
                display_name = f"{display_name}()"
            self.outline_selector.addItem(display_name, int(outline_node.get("line_number") or 0))

        self.outline_selector.setCurrentIndex(0)
        self.outline_selector.blockSignals(False)

    def _jump_to_outline_selection(self) -> None:
        line_number = self.outline_selector.currentData()
        if isinstance(line_number, int) and line_number > 0:
            self.code_viewer.highlightLine(line_number)

    def _toggle_layout_lock(self) -> None:
        self.layout_locked = not self.layout_locked
        if self.layout_locked:
            self.lock_button.setText("🔓 Unlock Layout")
        else:
            self.lock_button.setText("🔒 Lock Layout")

    def _update_code_viewer(self, relative_file_path: str, line_number: object) -> None:
        if not relative_file_path:
            self.code_viewer.setAnnotationContext(self.project_path, "")
            self.code_viewer.setPlainText("")
            self.code_viewer.setExtraSelections([])
            return

        source_path = self.project_path / relative_file_path
        self.code_viewer.setAnnotationContext(self.project_path, relative_file_path)
        try:
            code = source_path.read_text(encoding="utf-8")
        except OSError:
            self.code_viewer.setPlainText(f"Unable to load source: {source_path}")
            self.code_viewer.setExtraSelections([])
            return

        self.code_viewer.setPlainText(code)
        self.code_viewer.setExtraSelections([])

        if isinstance(line_number, int) and line_number > 0:
            self.code_viewer.highlightLine(line_number)
        else:
            cursor = self.code_viewer.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.code_viewer.setTextCursor(cursor)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.on_close(self.node_id)
        super().closeEvent(event)


def create_navigator_panel(title: str, width: int) -> tuple[QWidget, QLabel, QTreeWidget, QTreeWidget]:
    panel = QWidget()
    panel.setFixedWidth(width)

    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 18px; font-weight: 600;")

    body_label = QLabel(HOTKEY_REFERENCE)
    body_label.setWordWrap(True)
    body_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")

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


class BlueBenchWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Blue Bench")
        self.resize(1200, 700)
        self.settings = QSettings("BlueBench", "BlueBenchApp")
        self.graph_bridge = GraphBridge()
        self.project_discovery = ProjectDiscovery(DEV_ROOT)
        self.project_loader = ProjectLoader(
            self.graph_bridge.graph_manager,
            PythonRepoScanner,
        )
        self.current_project_path: Path | None = None
        self.node_windows: dict[str, NodeInspectorWindow] = {}

        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)

        navigator, self.navigator_body, self.project_list, self.module_list = create_navigator_panel(
            "Project Navigator",
            220,
        )

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        layout_controls = QWidget()
        layout_controls_layout = QHBoxLayout(layout_controls)
        layout_controls_layout.setContentsMargins(0, 0, 0, 0)
        layout_controls_layout.setSpacing(8)

        layout_label = QLabel("Layout")
        self.layout_selector = QComboBox()
        self.layout_selector.addItem("Horizontal", "horizontal")
        self.layout_selector.addItem("Vertical", "vertical")
        self.layout_selector.addItem("Radial", "radial")
        self.layout_selector.addItem("Grid", "grid")
        self.layout_selector.setCurrentIndex(1)

        layout_controls_layout.addWidget(layout_label)
        layout_controls_layout.addWidget(self.layout_selector)
        layout_controls_layout.addStretch()

        graph_view = QWebEngineView()
        graph_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.graph_view = graph_view
        self.web_channel = QWebChannel(graph_view.page())
        self.web_channel.registerObject("graphBridge", self.graph_bridge)
        graph_view.page().setWebChannel(self.web_channel)
        graph_view.load(QUrl.fromLocalFile(str(GRAPH_HTML_PATH)))

        center_layout.addWidget(layout_controls)
        center_layout.addWidget(graph_view, 1)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(True)
        self.main_splitter.addWidget(navigator)
        self.main_splitter.addWidget(center_panel)
        self.main_splitter.setSizes([250, 1000])
        if self.settings.contains("splitterState"):
            splitter_state = self.settings.value("splitterState")
            if splitter_state is not None:
                self.main_splitter.restoreState(splitter_state)

        main_layout.addWidget(self.main_splitter)

        self.setCentralWidget(central_widget)
        self._populate_projects()
        self.project_list.itemClicked.connect(self._load_selected_project)
        self.module_list.itemSelectionChanged.connect(self._load_selected_modules)
        self.graph_bridge.nodeSelectionChanged.connect(self._update_inspector)
        self.graph_bridge.layoutChanged.connect(self._apply_layout_to_renderer)
        self.graph_bridge.graphUpdated.connect(self._refresh_renderer)
        self.graph_bridge.focusRequested.connect(self._focus_node_in_renderer)
        self.layout_selector.currentIndexChanged.connect(self._handle_layout_change)

    def _populate_projects(self) -> None:
        self.project_list.clear()
        self.module_list.clear()
        for project_name in self.project_discovery.discover_projects():
            self.project_list.addTopLevelItem(QTreeWidgetItem([project_name]))

    def _load_selected_project(self, item: QTreeWidgetItem) -> None:
        project_path = DEV_ROOT / item.text(0)
        if not project_path.is_dir():
            return

        self._close_all_node_windows()
        file_paths = self.project_loader.load_project(project_path)
        self.current_project_path = project_path
        self._populate_module_tree(file_paths)

        self.graph_bridge.set_graph_view({"nodes": [], "edges": []})
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
            self._refresh_renderer()
            return

        self.graph_bridge.set_graph_view(self._merge_module_views(selected_paths))
        self._refresh_renderer()

    def _merge_module_views(self, module_ids: list[str]) -> dict[str, list[dict[str, object]]]:
        merged_nodes: dict[str, dict[str, object]] = {}
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

    def _handle_layout_change(self) -> None:
        layout_mode = self.layout_selector.currentData()
        if layout_mode:
            self.graph_bridge.setLayout(str(layout_mode))

    def _apply_layout_to_renderer(self, layout_mode: str) -> None:
        self.graph_view.page().runJavaScript(
            f"""
            if (typeof setLayout === 'function') {{
              setLayout({layout_mode!r});
            }}
            """
        )

    def _focus_node_in_renderer(self, node_id: str) -> None:
        self.graph_view.page().runJavaScript(
            f"""
            if (typeof focusNode === 'function') {{
              focusNode({node_id!r});
            }}
            """
        )

    def _update_inspector(self, payload: dict) -> None:
        node = payload.get("node") or payload
        if not node:
            return
        if not self.current_project_path:
            return

        node_id = str(node.get("id") or "")
        if not node_id:
            return

        existing_window = self.node_windows.get(node_id)
        if existing_window is not None:
            existing_window.refresh(node)
            existing_window.raise_()
            existing_window.activateWindow()
            return

        inspector_window = NodeInspectorWindow(
            self.graph_bridge.graph_manager,
            self.current_project_path,
            node,
            self._remove_node_window,
        )
        self.node_windows[node_id] = inspector_window
        inspector_window.show()

    def _remove_node_window(self, node_id: str) -> None:
        self.node_windows.pop(node_id, None)

    def _close_all_node_windows(self) -> None:
        for node_id, window in list(self.node_windows.items()):
            window.close()
            self.node_windows.pop(node_id, None)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.settings.setValue("splitterState", self.main_splitter.saveState())
        super().closeEvent(event)

def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = BlueBenchWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
