from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QRect, QRegularExpression, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QTextCharFormat, QTextCursor, QSyntaxHighlighter
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QPushButton,
    QComboBox,
    QDialog,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QScrollArea,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTextEdit as QTextEditWidget,
    QToolButton,
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

Header -> open file inspector
Top-left button -> collapse subtree
Top-right button -> expand node
Bottom-right button -> toggle metadata

Load more appears for large folders
Export writes the current layout document"""


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
        self._load_warning_shown = False
        self._pending_chunks: list[str] = []
        self._append_timer = QTimer(self)
        self._append_timer.setSingleShot(True)
        self._append_timer.timeout.connect(self._append_next_chunk)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
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
        self.scrollToLine(line_number)

    def scrollToLine(self, line_number: int) -> None:
        if not isinstance(line_number, int) or line_number <= 0:
            return

        block = self.document().findBlockByLineNumber(line_number - 1)
        if not block.isValid():
            return

        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

    def highlightNodeRegion(
        self,
        line_number: int | None,
        line_start: int | None,
        line_end: int | None,
        compute_score: int | None,
    ) -> None:
        selections: list[QTextEdit.ExtraSelection] = []

        if (
            isinstance(compute_score, int)
            and compute_score >= 4
            and isinstance(line_start, int)
            and isinstance(line_end, int)
            and line_start > 0
            and line_end >= line_start
        ):
            region_color = QColor("#d4a017" if compute_score <= 7 else "#c1440e")
            region_color.setAlpha(110)
            selections.extend(self._buildRegionSelections(line_start, line_end, region_color))

        if isinstance(line_number, int) and line_number > 0:
            block = self.document().findBlockByLineNumber(line_number - 1)
            if block.isValid():
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
                selections.append(line_highlight)

        self.setExtraSelections(selections)

    def _buildRegionSelections(
        self,
        line_start: int,
        line_end: int,
        color: QColor,
    ) -> list[QTextEdit.ExtraSelection]:
        selections: list[QTextEdit.ExtraSelection] = []
        for line_number in range(line_start, line_end + 1):
            block = self.document().findBlockByLineNumber(line_number - 1)
            if not block.isValid():
                continue

            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)

            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = QTextCharFormat()
            selection.format.setBackground(color)
            selection.format.setProperty(
                QTextCharFormat.Property.FullWidthSelection,
                True,
            )
            selections.append(selection)

        return selections

    def setAnnotationContext(self, project_root: Path | None, file_path: str) -> None:
        self.project_root = project_root
        self.current_file_path = file_path
        self._load_warning_shown = False
        self._loadAnnotations()
        self.line_number_area.update()

    def setComputeOverlay(self, line_start: int | None, line_end: int | None, compute_score: int | None) -> None:
        if (
            not isinstance(compute_score, int)
            or compute_score < 4
            or not isinstance(line_start, int)
            or not isinstance(line_end, int)
            or line_start <= 0
            or line_end < line_start
        ):
            self.setExtraSelections([])
            return

        region_color = QColor("#d4a017" if compute_score <= 7 else "#c1440e")
        region_color.setAlpha(110)
        self.setExtraSelections(self._buildRegionSelections(line_start, line_end, region_color))

    def loadSourceText(self, code: str) -> None:
        self._append_timer.stop()
        self._pending_chunks = []

        if len(code) <= 200_000:
            self.setPlainText(code)
            return

        lines = code.splitlines()
        first_chunk = "\n".join(lines[:1200])
        self.setPlainText(first_chunk)
        self._pending_chunks = [
            "\n".join(lines[index:index + 1200])
            for index in range(1200, len(lines), 1200)
        ]
        if self._pending_chunks:
            self._append_timer.start(0)

    def _append_next_chunk(self) -> None:
        if not self._pending_chunks:
            return

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\n" + self._pending_chunks.pop(0))
        if self._pending_chunks:
            self._append_timer.start(0)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()
        super().wheelEvent(event)

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
            if not self._load_warning_shown:
                QMessageBox.warning(
                    self,
                    "Annotation Warning",
                    "Unable to load .bluebench_annotations.json. The file is missing or corrupted.",
                )
                self._load_warning_shown = True
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


class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.clicked.connect(self._toggle_content)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 4, 0, 4)
        self.content_layout.setSpacing(6)
        self.content.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content)

    def _toggle_content(self) -> None:
        expanded = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)

    def setContentVisible(self, visible: bool) -> None:
        self.toggle_button.setChecked(visible)
        self._toggle_content()


class NodeInspectorWindow(QMainWindow):
    def __init__(
        self,
        graph_manager,
        project_path: Path,
        node: dict,
        on_close: Callable[[str], None],
        open_file_inspector: Callable[[dict[str, object]], None],
    ) -> None:
        super().__init__()
        self.graph_manager = graph_manager
        self.project_path = project_path
        self.node = node
        self.node_id = str(node.get("id", ""))
        self.on_close = on_close
        self.open_file_inspector = open_file_inspector
        self.layout_locked = False
        self.current_source_lines: list[str] = []

        self.setFixedSize(460, 640)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #1a1a22;
                top: -1px;
                background-color: #0b0b0e;
            }
            QTabBar::tab {
                background-color: #111116;
                color: #d8d8df;
                border: 1px solid #1a1a22;
                padding: 6px 10px;
                min-width: 80px;
            }
            QTabBar::tab:selected {
                background-color: #1a1a22;
                color: #f2e7d8;
            }
            """
        )

        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(4)

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

        code_layout.addWidget(toolbar)
        code_layout.addWidget(header_widget)
        code_layout.addWidget(self.outline_selector)
        code_layout.addWidget(self.code_viewer, 1)

        self.relationships_container = QWidget()
        self.relationships_layout = QVBoxLayout(self.relationships_container)
        self.relationships_layout.setContentsMargins(8, 8, 8, 8)
        self.relationships_layout.setSpacing(8)
        self.relationships_layout.addStretch()

        relationships_scroll = QScrollArea()
        relationships_scroll.setWidgetResizable(True)
        relationships_scroll.setFrameShape(QFrame.Shape.NoFrame)
        relationships_scroll.setWidget(self.relationships_container)

        self.metadata_container = QWidget()
        self.metadata_layout = QVBoxLayout(self.metadata_container)
        self.metadata_layout.setContentsMargins(8, 8, 8, 8)
        self.metadata_layout.setSpacing(8)
        self.metadata_layout.addStretch()

        metadata_scroll = QScrollArea()
        metadata_scroll.setWidgetResizable(True)
        metadata_scroll.setFrameShape(QFrame.Shape.NoFrame)
        metadata_scroll.setWidget(self.metadata_container)

        self.tabs.addTab(code_tab, "Code")
        self.tabs.addTab(relationships_scroll, "Relationships")
        self.tabs.addTab(metadata_scroll, "Metadata")
        layout.addWidget(self.tabs)

        self.setCentralWidget(central_widget)
        self.refresh(node)

    def refresh(self, node: dict) -> None:
        self.node = node
        self.node_id = str(node.get("id", ""))
        self.setWindowTitle(str(node.get("name") or self.node_id))

        self.header_title.setText(str(node.get("file_path") or node.get("name") or self.node_id))
        meta_parts = [
            str(node.get("type", "")),
            str(node.get("parent") or "-"),
            f"line {node.get('line_number') or '-'}",
        ]
        call_path_total_compute = node.get("call_path_total_compute")
        if isinstance(call_path_total_compute, int):
            meta_parts.append(f"call path compute {call_path_total_compute}")
        self.header_meta.setText(" · ".join(meta_parts))

        self._update_outline(node)
        loaded = self._update_code_viewer(
            str(node.get("file_path") or ""),
            node.get("line_number"),
            node.get("line_start"),
            node.get("line_end"),
            node.get("compute_score"),
        )
        self._populate_relationships_tab(node)
        self._populate_metadata_tab(node)
        if not loaded:
            QTimer.singleShot(0, self.close)

    def _update_outline(self, node: dict) -> None:
        self.outline_selector.blockSignals(True)
        self.outline_selector.clear()

        if node.get("type") in {"module", "file"}:
            module_id = str(node.get("file_path") or node.get("id") or "")
        else:
            module_id = str(node.get("parent") or "")
        if not module_id:
            self.outline_selector.setVisible(False)
            self.outline_selector.blockSignals(False)
            return

        outline_nodes = [
            graph_node
            for graph_node in self.graph_manager.nodes
            if graph_node.get("parent") == module_id
            and graph_node.get("type") in {"function", "class"}
        ]
        outline_nodes.sort(
            key=lambda graph_node: (
                int(graph_node.get("line_number") or 0),
                str(graph_node.get("name") or "").lower(),
            )
        )

        if not outline_nodes:
            self.outline_selector.setVisible(False)
            self.outline_selector.blockSignals(False)
            return

        self.outline_selector.addItem("Jump to definition...")

        for outline_node in outline_nodes:
            display_name = str(outline_node.get("name") or "")
            if outline_node.get("type") == "function":
                display_name = f"{display_name}()"
            self.outline_selector.addItem(display_name, int(outline_node.get("line_number") or 0))

        self.outline_selector.setCurrentIndex(0)
        self.outline_selector.setVisible(True)
        self.outline_selector.blockSignals(False)

    def _jump_to_outline_selection(self) -> None:
        line_number = self.outline_selector.currentData()
        if isinstance(line_number, int) and line_number > 0:
            self.code_viewer.scrollToLine(line_number)

    def _toggle_layout_lock(self) -> None:
        self.layout_locked = not self.layout_locked
        if self.layout_locked:
            self.lock_button.setText("🔓 Unlock Layout")
        else:
            self.lock_button.setText("🔒 Lock Layout")

    def _update_code_viewer(
        self,
        relative_file_path: str,
        line_number: object,
        line_start: object,
        line_end: object,
        compute_score: object,
    ) -> bool:
        if not relative_file_path:
            self.code_viewer.setAnnotationContext(self.project_path, "")
            self.code_viewer.setPlainText("")
            self.code_viewer.setExtraSelections([])
            return False

        source_path = self.project_path / relative_file_path
        self.code_viewer.setAnnotationContext(self.project_path, relative_file_path)
        try:
            code = source_path.read_text(encoding="utf-8")
        except OSError:
            self.code_viewer.setPlainText("")
            self.code_viewer.setExtraSelections([])
            return False

        self.code_viewer.loadSourceText(code)
        self.current_source_lines = code.splitlines()
        self.code_viewer.setComputeOverlay(
            line_start if isinstance(line_start, int) else None,
            line_end if isinstance(line_end, int) else None,
            compute_score if isinstance(compute_score, int) else None,
        )
        cursor = self.code_viewer.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.code_viewer.setTextCursor(cursor)
        return True

    def _populate_relationships_tab(self, node: dict) -> None:
        self._clear_dynamic_layout(self.relationships_layout)
        relationship_map = self._get_relationship_groups(node)
        for title, file_paths in relationship_map:
            section = CollapsibleSection(f"{title} ({len(file_paths)})")
            if not file_paths:
                empty_label = QLabel("No relationships")
                empty_label.setStyleSheet("color: #777777;")
                section.content_layout.addWidget(empty_label)
            else:
                for file_path in file_paths:
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(6)
                    label = QLabel(file_path)
                    open_button = QPushButton("open")
                    open_button.setFixedWidth(56)
                    open_button.clicked.connect(
                        lambda _checked=False, path=file_path: self.open_file_inspector({"file_path": path})
                    )
                    row_layout.addWidget(label, 1)
                    row_layout.addWidget(open_button)
                    section.content_layout.addWidget(row)
            self.relationships_layout.insertWidget(self.relationships_layout.count() - 1, section)

    def _populate_metadata_tab(self, node: dict) -> None:
        self._clear_dynamic_layout(self.metadata_layout)

        file_info = CollapsibleSection("File information")
        file_info.setContentVisible(True)
        for line in [
            f"Name: {node.get('name') or '-'}",
            f"Path: {node.get('file_path') or '-'}",
            f"Type: {node.get('type') or '-'}",
            f"Parent: {node.get('parent') or '-'}",
        ]:
            file_info.content_layout.addWidget(QLabel(line))

        compute_info = CollapsibleSection("Compute data")
        compute_info.setContentVisible(True)
        for line in [
            f"Compute score: {node.get('compute_score') if node.get('compute_score') is not None else '-'}",
            f"Line start: {node.get('line_start') or '-'}",
            f"Line end: {node.get('line_end') or '-'}",
            f"Call path total compute: {node.get('call_path_total_compute') if node.get('call_path_total_compute') is not None else '-'}",
        ]:
            compute_info.content_layout.addWidget(QLabel(line))

        notes_section = CollapsibleSection("Notes")
        notes_section.setContentVisible(True)
        note_entries = self._get_note_entries()
        if not note_entries:
            notes_section.content_layout.addWidget(QLabel("No notes"))
        else:
            for entry in note_entries:
                note_block = CollapsibleSection(entry["title"])
                note_block.content_layout.addWidget(QLabel(f"line {entry['line_number']}"))
                note_block.content_layout.addWidget(QLabel(entry["snippet"]))
                jump_button = QPushButton("Open In Code")
                jump_button.clicked.connect(
                    lambda _checked=False, line_number=entry["line_number"]: self._jump_to_note(line_number)
                )
                note_block.content_layout.addWidget(jump_button)
                notes_section.content_layout.addWidget(note_block)

        summary_section = CollapsibleSection("Relationships summary")
        summary_section.setContentVisible(True)
        for title, file_paths in self._get_relationship_groups(node):
            summary_section.content_layout.addWidget(QLabel(f"{title}: {len(file_paths)}"))

        for section in [file_info, compute_info, notes_section, summary_section]:
            self.metadata_layout.insertWidget(self.metadata_layout.count() - 1, section)

    def _get_relationship_groups(self, node: dict) -> list[tuple[str, list[str]]]:
        module_id = str(node.get("file_path") or node.get("id") or "")
        if not module_id:
            return [("Calls", []), ("Imports", []), ("Imported By", []), ("Used By", [])]

        calls: set[str] = set()
        imports: set[str] = set()
        imported_by: set[str] = set()
        used_by: set[str] = set()
        function_ids = {
            str(graph_node.get("id") or "")
            for graph_node in self.graph_manager.nodes
            if str(graph_node.get("parent") or "") == module_id
            and graph_node.get("type") in {"function", "class"}
        }

        for edge in self.graph_manager.edges:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            edge_type = str(edge.get("type") or "")

            if edge_type == "imports":
                if source == module_id:
                    target_node = self.graph_manager.get_node(target)
                    if target_node and target_node.get("file_path"):
                        imports.add(str(target_node.get("file_path")))
                if target == module_id:
                    source_node = self.graph_manager.get_node(source)
                    if source_node and source_node.get("file_path"):
                        imported_by.add(str(source_node.get("file_path")))

            if edge_type == "calls":
                if source in function_ids:
                    target_node = self.graph_manager.get_node(target)
                    if target_node and target_node.get("file_path"):
                        calls.add(str(target_node.get("file_path")))
                if target in function_ids:
                    source_node = self.graph_manager.get_node(source)
                    if source_node and source_node.get("file_path"):
                        used_by.add(str(source_node.get("file_path")))

        return [
            ("Calls", sorted(path for path in calls if path != module_id)),
            ("Imports", sorted(path for path in imports if path != module_id)),
            ("Imported By", sorted(path for path in imported_by if path != module_id)),
            ("Used By", sorted(path for path in used_by if path != module_id)),
        ]

    def _get_note_entries(self) -> list[dict[str, object]]:
        current_annotations = self.code_viewer.line_annotations.get(self.code_viewer.current_file_path, {})
        entries: list[dict[str, object]] = []
        for line_number, annotation in sorted(current_annotations.items()):
            marker = str(annotation.get("marker", "note")).strip() or "note"
            note_text = str(annotation.get("note", "")).strip()
            snippet = ""
            if 0 < line_number <= len(self.current_source_lines):
                snippet = self.current_source_lines[line_number - 1].strip()
            preview = snippet or note_text.splitlines()[0] if note_text else snippet
            entries.append(
                {
                    "title": marker.replace("_", " ").title(),
                    "line_number": line_number,
                    "snippet": preview or "(no preview)",
                }
            )
        return entries

    def _jump_to_note(self, line_number: int) -> None:
        self.tabs.setCurrentIndex(0)
        self.code_viewer.scrollToLine(line_number)

    def _clear_dynamic_layout(self, layout: QVBoxLayout) -> None:
        while layout.count() > 1:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.on_close(self.node_id)
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if self.tabs.currentIndex() == 0 and event.text().lower() in {"j", "k"}:
            if self.outline_selector.count() > 1:
                current_index = self.outline_selector.currentIndex()
                if current_index <= 0:
                    current_index = 1
                if event.text().lower() == "j":
                    next_index = min(self.outline_selector.count() - 1, current_index + 1)
                else:
                    next_index = max(1, current_index - 1)
                if next_index != self.outline_selector.currentIndex():
                    self.outline_selector.setCurrentIndex(next_index)
            return
        super().keyPressEvent(event)


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
        self._inspector_open_count = 0

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

        layout_label = QLabel("Explorer")
        self.export_button = QPushButton("Export Layout")
        self.export_button.clicked.connect(self._export_layout_document)

        layout_controls_layout.addWidget(layout_label)
        layout_controls_layout.addStretch()
        layout_controls_layout.addWidget(self.export_button)

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
        self.graph_bridge.nodeSelectionChanged.connect(self._update_inspector)
        self.graph_bridge.explorerInspectorRequested.connect(self.open_inspector_from_explorer)
        self.graph_bridge.layoutChanged.connect(self._apply_layout_to_renderer)
        self.graph_bridge.graphUpdated.connect(self._refresh_renderer)
        self.graph_bridge.focusRequested.connect(self._focus_node_in_renderer)

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
        self.graph_bridge.set_project_tree(
            project_path,
            self.graph_bridge.graph_manager.build_codebase_tree(project_path, file_paths),
        )
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
        return

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
            if (window.graphBridge && window.BlueBenchRenderer && typeof window.BlueBenchRenderer.updateGraph === 'function') {
              window.graphBridge.sendGraph(function(data) {
                window.BlueBenchRenderer.updateGraph(data);
              });
            }
            """
        )

    def _handle_layout_change(self) -> None:
        return

    def _apply_layout_to_renderer(self, layout_mode: str) -> None:
        self.graph_view.page().runJavaScript(
            f"""
            if (window.BlueBenchRenderer && typeof window.BlueBenchRenderer.setLayout === 'function') {{
              window.BlueBenchRenderer.setLayout({layout_mode!r});
            }}
            """
        )

    def _focus_node_in_renderer(self, node_id: str) -> None:
        self.graph_view.page().runJavaScript(
            f"""
            if (window.BlueBenchRenderer && typeof window.BlueBenchRenderer.focusNode === 'function') {{
              window.BlueBenchRenderer.focusNode({node_id!r});
            }}
            """
        )

    def _export_layout_document(self) -> None:
        self.graph_view.page().runJavaScript(
            """
            if (window.BlueBenchRenderer && typeof window.BlueBenchRenderer.exportCurrentView === 'function') {
              window.BlueBenchRenderer.exportCurrentView();
            } else if (window.graphBridge && typeof window.graphBridge.exportCurrentLayout === 'function') {
              window.graphBridge.exportCurrentLayout();
            }
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
            self.open_inspector_from_explorer,
        )
        self._position_inspector_window(inspector_window)
        self.node_windows[node_id] = inspector_window
        inspector_window.show()

    def open_inspector_from_explorer(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return

        file_path = payload.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            return

        node = self.graph_bridge.graph_manager.get_node_by_file_path(file_path)
        if node is None:
            return

        inspector_payload = {
            "id": node.get("id"),
            "name": node.get("name"),
            "type": node.get("type"),
            "file_path": node.get("file_path"),
            "line_number": node.get("line_number"),
            "line_start": node.get("line_start"),
            "line_end": node.get("line_end"),
            "compute_score": node.get("compute_score"),
            "parent": node.get("parent"),
            "call_path_total_compute": node.get("call_path_total_compute"),
        }
        self._update_inspector(inspector_payload)

    def _remove_node_window(self, node_id: str) -> None:
        self.node_windows.pop(node_id, None)

    def _close_all_node_windows(self) -> None:
        for node_id, window in list(self.node_windows.items()):
            window.close()
            self.node_windows.pop(node_id, None)

    def _position_inspector_window(self, inspector_window: NodeInspectorWindow) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        cascade_step = 28
        index = len(self.node_windows)
        x = max(geometry.left() + 16, geometry.left() + 120 - (index * cascade_step))
        y = geometry.top() + 48
        inspector_window.move(x, y)

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
