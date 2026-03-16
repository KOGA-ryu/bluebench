from __future__ import annotations

import json
import shlex
import sys
from datetime import datetime
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QRect, QProcess, QRegularExpression, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QTextCharFormat, QTextCursor, QSyntaxHighlighter
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractButton,
    QApplication,
    QPushButton,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QLineEdit,
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

try:
    from backend.instrumentation import InstrumentationStorage
except ModuleNotFoundError:
    from instrumentation import InstrumentationStorage

try:
    from backend.stress_engine import StressEngineWindow
except ModuleNotFoundError:
    from stress_engine import StressEngineWindow

try:
    from backend.triage_window import TriageWindow
except ModuleNotFoundError:
    from triage_window import TriageWindow

try:
    from backend.context import build_context_pack, export_context_json, export_context_markdown, save_session_state
except ModuleNotFoundError:
    from context import build_context_pack, export_context_json, export_context_markdown, save_session_state

GRAPH_HTML_PATH = PROJECT_ROOT / "frontend" / "graph" / "renderer" / "bluebench_graph.html"
INSTRUMENTATION_DB_PATH = PROJECT_ROOT / ".bluebench" / "instrumentation.sqlite3"
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
        self.current_file_compute: dict[str, object] = {}
        self.current_function_compute: list[dict[str, object]] = []
        self.current_run_provenance: dict[str, object] = {}

        self.setFixedSize(460, 640)
        self.setStyleSheet(
            """
            QToolTip {
                background-color: #4a1616;
                color: #f5dada;
                border: 1px solid #7a2b2b;
                padding: 6px;
            }
            """
        )

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
        self.header_run = QLabel()
        self.header_run.setStyleSheet("color: #d9c18b; font-size: 11px; font-weight: 700;")

        header_widget = QWidget()
        header_widget.setMaximumHeight(78)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        header_layout.addWidget(self.header_title)
        header_layout.addWidget(self.header_meta)
        header_layout.addWidget(self.header_run)

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
        self.relationship_file_buttons: list[QAbstractButton] = []

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

        self.compute_container = QWidget()
        self.compute_layout = QVBoxLayout(self.compute_container)
        self.compute_layout.setContentsMargins(8, 8, 8, 8)
        self.compute_layout.setSpacing(8)
        self.compute_layout.addStretch()

        compute_scroll = QScrollArea()
        compute_scroll.setWidgetResizable(True)
        compute_scroll.setFrameShape(QFrame.Shape.NoFrame)
        compute_scroll.setWidget(self.compute_container)

        self.tabs.addTab(code_tab, "Code")
        self.tabs.addTab(compute_scroll, "Compute")
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
        active_run_name = str(node.get("active_run_name") or "").strip()
        if active_run_name:
            active_run_suffix = " · ".join(
                [
                    part
                    for part in [
                        str(node.get("active_run_scenario") or "").strip(),
                        str(node.get("active_run_hardware") or "").strip(),
                    ]
                    if part
                ]
            )
            self.header_run.setText(
                f"Active Run: {active_run_name}" + (f" · {active_run_suffix}" if active_run_suffix else "")
            )
            self.header_run.setVisible(True)
        else:
            self.header_run.setVisible(False)
        self.current_file_compute = dict(node.get("file_compute") or {}) if isinstance(node.get("file_compute"), dict) else {}
        self.current_function_compute = [
            dict(entry)
            for entry in node.get("function_compute", [])
            if isinstance(entry, dict)
        ] if isinstance(node.get("function_compute"), list) else []
        self.current_run_provenance = {
            "run_id": node.get("active_run_id"),
            "run_name": node.get("active_run_name"),
            "scenario": node.get("active_run_scenario"),
            "hardware": node.get("active_run_hardware"),
            "status": node.get("active_run_status"),
            "finished_at": node.get("active_run_finished_at"),
            "failure_count": node.get("active_run_failure_count"),
            "previous_run_name": node.get("previous_run_name"),
            "previous_run_id": node.get("previous_run_id"),
            "previous_finished_at": node.get("previous_run_finished_at"),
        }

        self._update_outline(node)
        loaded = self._update_code_viewer(
            str(node.get("file_path") or ""),
            node.get("line_number"),
            node.get("line_start"),
            node.get("line_end"),
            node.get("compute_score"),
        )
        self._populate_relationships_tab(node)
        self._populate_compute_tab(node)
        self._populate_metadata_tab(node)
        self._set_requested_tab(str(node.get("preferred_tab") or "Code"))
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

        function_lookup = self._function_compute_lookup()

        for outline_node in outline_nodes:
            display_name = str(outline_node.get("name") or "")
            if outline_node.get("type") == "function":
                display_name = f"{display_name}()"
            compute_entry = function_lookup.get(str(outline_node.get("name") or ""))
            if compute_entry is not None:
                display_name = (
                    f"{display_name} · {int(round(float(compute_entry.get('normalized_compute_score') or 0.0)))}"
                    f" · {float(compute_entry.get('total_time_ms') or 0.0):.1f} ms"
                )
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
        self.relationship_file_buttons = []
        file_path = str(node.get("file_path") or "")
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        expand_all = QPushButton("Expand All")
        collapse_all = QPushButton("Collapse All")
        expand_all.clicked.connect(lambda: self._set_relationship_expansion(True))
        collapse_all.clicked.connect(lambda: self._set_relationship_expansion(False))
        controls_layout.addWidget(expand_all)
        controls_layout.addWidget(collapse_all)
        controls_layout.addStretch()
        self.relationships_layout.insertWidget(self.relationships_layout.count() - 1, controls)

        relationship_map = self._get_relationship_groups(file_path)
        for title, file_paths, getter, recurse in relationship_map:
            total_count = self._relationship_total_count(file_path, getter, recurse)
            section = CollapsibleSection(f"{title} ({total_count} total)")
            if not file_paths:
                empty_label = QLabel("No relationships")
                empty_label.setStyleSheet("color: #777777;")
                section.content_layout.addWidget(empty_label)
            else:
                top_level_indexes = {
                    related_path: self.graph_manager.get_chapter_index(related_path) or f"{index + 1}"
                    for index, related_path in enumerate(file_paths)
                }
                rendered_indexes = dict(top_level_indexes)
                for related_path in file_paths:
                    section.content_layout.addWidget(
                        self._create_relationship_entry_widget(
                            related_path,
                            getter,
                            recurse,
                            ancestry={file_path},
                            display_index=top_level_indexes[related_path],
                            top_level_indexes=top_level_indexes,
                            rendered_indexes=rendered_indexes,
                            allow_cross_reference=False,
                        )
                    )
            self.relationships_layout.insertWidget(self.relationships_layout.count() - 1, section)

    def _populate_compute_tab(self, node: dict) -> None:
        self._clear_dynamic_layout(self.compute_layout)

        compute_info = CollapsibleSection("Compute data")
        compute_info.setContentVisible(True)
        summary_widget = self._compute_summary_widget(node)
        compute_info.content_layout.addWidget(summary_widget)
        for line in self._file_compute_detail_lines(node):
            detail_label = QLabel(line)
            detail_label.setWordWrap(True)
            compute_info.content_layout.addWidget(detail_label)

        investigation_section = CollapsibleSection("Investigation summary")
        investigation_section.setContentVisible(True)
        for line in self._investigation_summary_lines():
            label = QLabel(line)
            label.setWordWrap(True)
            investigation_section.content_layout.addWidget(label)

        function_rankings = CollapsibleSection("Function ranking")
        function_rankings.setContentVisible(True)
        if not self.current_function_compute:
            function_rankings.content_layout.addWidget(QLabel("No function compute for the active run"))
        else:
            for entry in self.current_function_compute:
                function_rankings.content_layout.addWidget(self._function_ranking_widget(entry))

        provenance_section = CollapsibleSection("Run provenance")
        provenance_section.setContentVisible(True)
        for line in self._run_provenance_lines():
            label = QLabel(line)
            label.setWordWrap(True)
            provenance_section.content_layout.addWidget(label)

        external_section = CollapsibleSection("External pressure")
        external_section.setContentVisible(True)
        external_lines = self._external_pressure_lines()
        if not external_lines:
            external_section.content_layout.addWidget(QLabel("No external pressure data for the active run"))
        else:
            for line in external_lines:
                external_section.content_layout.addWidget(QLabel(line))

        diagnostics_section = CollapsibleSection("Diagnostic callouts")
        diagnostics_section.setContentVisible(True)
        for line in self._diagnostic_callout_lines():
            label = QLabel(line)
            label.setWordWrap(True)
            diagnostics_section.content_layout.addWidget(label)

        for section in [
            compute_info,
            investigation_section,
            function_rankings,
            provenance_section,
            external_section,
            diagnostics_section,
        ]:
            self.compute_layout.insertWidget(self.compute_layout.count() - 1, section)

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
        for title, file_paths, _getter, _recurse in self._get_relationship_groups(str(node.get("file_path") or "")):
            summary_section.content_layout.addWidget(QLabel(f"{title}: {len(file_paths)}"))

        for section in [
            file_info,
            notes_section,
            summary_section,
        ]:
            self.metadata_layout.insertWidget(self.metadata_layout.count() - 1, section)

    def _file_compute_detail_lines(self, node: dict[str, object]) -> list[str]:
        if not self.current_file_compute:
            return [
                "No active run compute selected",
                f"Line start: {node.get('line_start') or '-'}",
                f"Line end: {node.get('line_end') or '-'}",
                f"Call path total compute: {node.get('call_path_total_compute') if node.get('call_path_total_compute') is not None else '-'}",
            ]

        lines = [
            f"Compute tier: {int(self.current_file_compute.get('compute_tier') or 3)}",
            f"Normalized score: {float(self.current_file_compute.get('normalized_compute_score') or 0.0):.1f}",
            f"Total self time: {float(self.current_file_compute.get('total_self_time_ms') or 0.0):.1f} ms",
            f"Total time: {float(self.current_file_compute.get('total_time_ms') or 0.0):.1f} ms",
            f"Call count: {int(self.current_file_compute.get('call_count') or 0)}",
            f"Exception count: {int(self.current_file_compute.get('exception_count') or 0)}",
        ]
        delta = self.current_file_compute.get("delta")
        if isinstance(delta, (int, float)):
            lines.append(f"Delta vs previous: {delta:+.1f}")
        lines.extend(
            [
                f"Line start: {node.get('line_start') or '-'}",
                f"Line end: {node.get('line_end') or '-'}",
                f"Call path total compute: {node.get('call_path_total_compute') if node.get('call_path_total_compute') is not None else '-'}",
            ]
        )
        return lines

    def _compute_summary_widget(self, node: dict[str, object]) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("Measured Compute")
        title.setStyleSheet("font-size: 12px; font-weight: 700; color: #f2e7d8; text-transform: uppercase;")
        layout.addWidget(title)

        if not self.current_file_compute:
            empty = QLabel("No active run selected for this file.")
            empty.setStyleSheet("color: #aaaaaa;")
            layout.addWidget(empty)
            return widget

        score = float(self.current_file_compute.get("normalized_compute_score") or 0.0)
        total_time_ms = float(self.current_file_compute.get("total_time_ms") or 0.0)
        total_self_time_ms = float(self.current_file_compute.get("total_self_time_ms") or 0.0)
        score_line = QLabel(f"Score {score:.1f} · Total {total_time_ms:.1f} ms · Self {total_self_time_ms:.1f} ms")
        score_line.setStyleSheet("font-size: 14px; font-weight: 700; color: #d9c18b;")
        layout.addWidget(score_line)

        sub_line = QLabel(
            f"Tier {int(self.current_file_compute.get('compute_tier') or 3)} · "
            f"Calls {int(self.current_file_compute.get('call_count') or 0)} · "
            f"Exceptions {int(self.current_file_compute.get('exception_count') or 0)}"
        )
        sub_line.setStyleSheet("font-size: 11px; color: #cdbfae;")
        layout.addWidget(sub_line)

        delta = self.current_file_compute.get("delta")
        if isinstance(delta, (int, float)):
            delta_label = QLabel(f"Delta vs previous: {delta:+.1f}")
            delta_label.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: "
                + ("#d9f0ba;" if delta >= 0 else "#f0c3b8;")
            )
            layout.addWidget(delta_label)

        return widget

    def _function_ranking_widget(self, entry: dict[str, object]) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        name_label = QLabel(str(entry.get("display_name") or "-"))
        name_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #f2e7d8;")
        perf_label = QLabel(
            (
                f"Score {float(entry.get('normalized_compute_score') or 0.0):.1f} · "
                f"self {float(entry.get('self_time_ms') or 0.0):.1f} ms · "
                f"total {float(entry.get('total_time_ms') or 0.0):.1f} ms · "
                f"calls {int(entry.get('call_count') or 0)}"
            )
        )
        perf_label.setStyleSheet("font-size: 11px; color: #d9c18b;")
        failure_text = f"Exceptions {int(entry.get('exception_count') or 0)}"
        if entry.get("last_exception_type"):
            failure_text += f" · last {entry.get('last_exception_type')}"
        failure_label = QLabel(failure_text)
        failure_label.setStyleSheet("font-size: 10px; color: #aaaaaa;")
        layout.addWidget(name_label)
        layout.addWidget(perf_label)
        layout.addWidget(failure_label)
        return widget

    def _investigation_summary_lines(self) -> list[str]:
        if not self.current_file_compute:
            return ["No measured compute is active for this file."]

        lines = [
            f"Last measured run: {self._run_display_name()}",
            f"Primary signal: {self._primary_signal_line()}",
        ]
        top_functions = self.current_function_compute[:3]
        if top_functions:
            top_names = ", ".join(
                f"{str(entry.get('display_name') or '-')}"
                f" ({float(entry.get('normalized_compute_score') or 0.0):.0f})"
                for entry in top_functions
            )
            lines.append(f"Top functions: {top_names}")
        dominant_external = self._dominant_external_bucket()
        if dominant_external:
            lines.append(f"Dominant external: {dominant_external}")
        lines.append(f"Exceptions in file: {int(self.current_file_compute.get('exception_count') or 0)}")
        return lines

    def _run_provenance_lines(self) -> list[str]:
        run_name = str(self.current_run_provenance.get("run_name") or "").strip()
        if not run_name:
            return ["No active run selected."]

        lines = [f"Run: {run_name}"]
        scenario = str(self.current_run_provenance.get("scenario") or "").strip()
        hardware = str(self.current_run_provenance.get("hardware") or "").strip()
        if scenario or hardware:
            lines.append("Context: " + " · ".join(part for part in [scenario, hardware] if part))
        status = str(self.current_run_provenance.get("status") or "").strip()
        if status:
            lines.append(f"Status: {status}")
        finished_at = str(self.current_run_provenance.get("finished_at") or "").strip()
        if finished_at:
            lines.append(f"Finished: {finished_at}")
        failure_count = self.current_run_provenance.get("failure_count")
        if isinstance(failure_count, int):
            lines.append(f"Run failures: {failure_count}")
        previous_run_name = str(self.current_run_provenance.get("previous_run_name") or "").strip()
        if previous_run_name:
            previous_finished_at = str(self.current_run_provenance.get("previous_finished_at") or "").strip()
            previous_line = f"Previous comparable: {previous_run_name}"
            if previous_finished_at:
                previous_line += f" · {previous_finished_at}"
            lines.append(previous_line)
        return lines

    def _diagnostic_callout_lines(self) -> list[str]:
        if not self.current_file_compute:
            return ["No diagnostics without an active measured run."]

        lines: list[str] = []
        exception_count = int(self.current_file_compute.get("exception_count") or 0)
        if exception_count > 0:
            lines.append(f"Failure signal: {exception_count} exceptions were recorded in this file.")

        dominant_external = self._dominant_external_bucket()
        if dominant_external:
            lines.append(f"External pressure: {dominant_external} dominates non-project time.")

        if self.current_function_compute:
            total_time = float(self.current_file_compute.get("total_time_ms") or 0.0)
            hottest_function = self.current_function_compute[0]
            hottest_total = float(hottest_function.get("total_time_ms") or 0.0)
            if total_time > 0.0 and hottest_total / total_time >= 0.6:
                lines.append("Hotspot concentration: one function dominates at least 60% of this file's measured time.")
            hottest_calls = int(hottest_function.get("call_count") or 0)
            if hottest_calls >= 1000:
                lines.append(
                    f"Call pressure: {str(hottest_function.get('display_name') or '-')} was called {hottest_calls:,} times."
                )

        delta = self.current_file_compute.get("delta")
        if isinstance(delta, (int, float)):
            if delta >= 10.0:
                lines.append(f"Regression: score increased by {delta:+.1f} vs the previous comparable run.")
            elif delta <= -10.0:
                lines.append(f"Improvement: score changed by {delta:+.1f} vs the previous comparable run.")

        if not lines:
            lines.append("No unusual signals detected for the active run.")
        return lines

    def _run_display_name(self) -> str:
        run_name = str(self.current_run_provenance.get("run_name") or "").strip()
        if not run_name:
            return "none"
        scenario = str(self.current_run_provenance.get("scenario") or "").strip()
        return f"{run_name} · {scenario}" if scenario else run_name

    def _primary_signal_line(self) -> str:
        if not self.current_function_compute:
            return "file-level timing only"
        hottest_function = self.current_function_compute[0]
        return (
            f"{str(hottest_function.get('display_name') or '-')} leads with "
            f"{float(hottest_function.get('total_time_ms') or 0.0):.1f} ms total time"
        )

    def _dominant_external_bucket(self) -> str:
        summary = self.current_file_compute.get("external_pressure_summary")
        if not isinstance(summary, dict):
            return ""
        buckets = summary.get("external_buckets")
        if not isinstance(buckets, dict):
            return ""
        best_name = ""
        best_time = 0.0
        for bucket_name, bucket_values in buckets.items():
            if not isinstance(bucket_values, dict):
                continue
            bucket_time = float(bucket_values.get("total_time_ms") or 0.0)
            if bucket_time > best_time:
                best_name = str(bucket_name)
                best_time = bucket_time
        if not best_name or best_time <= 0.0:
            return ""
        return f"{best_name.replace('external:', '')} {best_time:.1f} ms"

    def _function_compute_lookup(self) -> dict[str, dict[str, object]]:
        lookup: dict[str, dict[str, object]] = {}
        for entry in self.current_function_compute:
            raw_symbol = str(entry.get("symbol_name") or "")
            if raw_symbol:
                lookup[raw_symbol] = entry
            fallback = raw_symbol.split(".")[-1] if raw_symbol else ""
            if fallback and fallback not in lookup:
                lookup[fallback] = entry
        return lookup

    def _external_pressure_lines(self) -> list[str]:
        summary = self.current_file_compute.get("external_pressure_summary")
        if not isinstance(summary, dict):
            return []
        buckets = summary.get("external_buckets")
        if not isinstance(buckets, dict):
            return []
        ordered = sorted(
            (
                (bucket_name, bucket_values)
                for bucket_name, bucket_values in buckets.items()
                if isinstance(bucket_values, dict)
            ),
            key=lambda item: -float(item[1].get("total_time_ms") or 0.0),
        )
        return [
            (
                f"{bucket_name.replace('external:', '')}   "
                f"{float(bucket_values.get('total_time_ms') or 0.0):.1f} ms"
            )
            for bucket_name, bucket_values in ordered
            if float(bucket_values.get("total_time_ms") or 0.0) > 0.0
        ]

    def _get_relationship_groups(
        self,
        file_path: str,
    ) -> list[tuple[str, list[str], Callable[[str], list[str]], bool]]:
        if not file_path:
            empty: list[tuple[str, list[str], Callable[[str], list[str]], bool]] = []
            for title, getter, recurse in self._relationship_specs():
                empty.append((title, [], getter, recurse))
            return empty

        return [
            (title, getter(file_path), getter, recurse)
            for title, getter, recurse in self._relationship_specs()
        ]

    def _relationship_specs(self) -> list[tuple[str, Callable[[str], list[str]], bool]]:
        return [
            ("Calls", self.graph_manager.get_file_calls, True),
            ("Imports", self.graph_manager.get_file_imports, False),
            ("Called By", self.graph_manager.get_file_called_by, False),
            ("Imported By", self.graph_manager.get_file_imported_by, False),
        ]

    def _create_relationship_entry_widget(
        self,
        file_path: str,
        getter: Callable[[str], list[str]],
        recurse: bool,
        ancestry: set[str],
        display_index: str,
        top_level_indexes: dict[str, str],
        rendered_indexes: dict[str, str],
        allow_cross_reference: bool,
    ) -> QWidget:
        cycle_detected = file_path in ancestry
        if cycle_detected:
            return self._relationship_cross_reference_row("↺ cycle detected", file_path, clickable=False)

        if allow_cross_reference and file_path in top_level_indexes:
            reference_index = top_level_indexes[file_path]
            return self._relationship_cross_reference_row(
                f"↳ see {reference_index} {Path(file_path).name}",
                file_path,
            )

        existing_index = rendered_indexes.get(file_path)
        if allow_cross_reference and existing_index is not None:
            return self._relationship_cross_reference_row(
                f"↳ see {existing_index} {Path(file_path).name}",
                file_path,
            )

        rendered_indexes.setdefault(file_path, display_index)
        child_paths = [] if not recurse else [path for path in getter(file_path) if path != file_path]
        label_text = self._relationship_entry_label(display_index, file_path)
        if not child_paths:
            return self._relationship_leaf_row(label_text, file_path, show_open=True)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        toggle_button = QToolButton()
        toggle_button.setText(">")
        toggle_button.setCheckable(True)
        toggle_button.setChecked(False)
        toggle_button.setFixedWidth(28)

        entry_button = self._relationship_file_button(label_text, file_path)

        content = QWidget()
        content.setVisible(False)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 0, 0, 0)
        content_layout.setSpacing(4)

        def toggle_children() -> None:
            expanded = toggle_button.isChecked()
            toggle_button.setText("v" if expanded else ">")
            content.setVisible(expanded)

        toggle_button.clicked.connect(toggle_children)
        toggle_button._apply_relationship_expanded = lambda expanded: self._apply_relationship_toggle(  # type: ignore[attr-defined]
            toggle_button,
            content,
            expanded,
        )
        header_layout.addWidget(toggle_button)
        header_layout.addWidget(entry_button, 1)
        container_layout.addWidget(header)
        container_layout.addWidget(content)

        next_ancestry = set(ancestry)
        next_ancestry.add(file_path)
        for child_index, child_path in enumerate(child_paths):
            child_display_index = f"{display_index}.{self._alpha_index(child_index)}"
            content_layout.addWidget(
                self._create_relationship_entry_widget(
                    child_path,
                    getter,
                    recurse,
                    next_ancestry,
                    child_display_index,
                    top_level_indexes,
                    rendered_indexes,
                    allow_cross_reference=True,
                )
            )
        return container

    def _relationship_leaf_row(self, label_text: str, file_path: str, show_open: bool) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        row_layout.addWidget(self._relationship_file_button(label_text, file_path), 1)
        if show_open:
            open_button = QPushButton("open")
            open_button.setFixedWidth(56)
            open_button.clicked.connect(
                lambda _checked=False, path=file_path: self.open_file_inspector(
                    {"file_path": path, "preferred_tab": "Relationships"}
                )
            )
            row_layout.addWidget(open_button)
        return row

    def _relationship_cross_reference_row(self, label_text: str, file_path: str, clickable: bool = True) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        if clickable:
            row_layout.addWidget(self._relationship_file_button(label_text, file_path), 1)
        else:
            row_layout.addWidget(QLabel(label_text), 1)
        return row

    def _relationship_file_button(self, label_text: str, file_path: str) -> QPushButton:
        button = QPushButton(label_text)
        button.setFlat(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet("text-align: left; padding: 2px 4px; border: 0;")
        button.setToolTip(self._relationship_hover_preview(file_path))
        button.clicked.connect(
            lambda _checked=False, path=file_path: self.open_file_inspector(
                {"file_path": path, "preferred_tab": "Relationships"}
            )
        )
        self.relationship_file_buttons.append(button)
        return button

    def _relationship_entry_label(self, display_index: str, file_path: str) -> str:
        return f"{display_index} {Path(file_path).name} — {file_path}"

    def _relationship_hover_preview(self, file_path: str) -> str:
        source_path = self.project_path / file_path
        try:
            lines = source_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        preview = "\n".join(lines[:4]).strip() or "(preview unavailable)"
        return f"{Path(file_path).name}\n{file_path}\n\n{preview}"

    def _relationship_total_count(
        self,
        file_path: str,
        getter: Callable[[str], list[str]],
        recurse: bool,
    ) -> int:
        if not file_path:
            return 0
        if not recurse:
            return len(getter(file_path))

        visited: set[str] = set()

        def visit(current_path: str) -> None:
            for related_path in getter(current_path):
                if related_path in visited or related_path == current_path:
                    continue
                visited.add(related_path)
                visit(related_path)

        visit(file_path)
        return len(visited)

    def _alpha_index(self, index: int) -> str:
        value = index + 1
        letters: list[str] = []
        while value > 0:
            value, remainder = divmod(value - 1, 26)
            letters.append(chr(ord("a") + remainder))
        return "".join(reversed(letters))

    def _set_relationship_expansion(self, expanded: bool) -> None:
        for section in self.relationships_container.findChildren(CollapsibleSection):
            section.setContentVisible(expanded)
        for toggle_button in self.relationships_container.findChildren(QToolButton):
            apply_expanded = getattr(toggle_button, "_apply_relationship_expanded", None)
            if callable(apply_expanded):
                apply_expanded(expanded)

    def _apply_relationship_toggle(self, toggle_button: QToolButton, content: QWidget, expanded: bool) -> None:
        toggle_button.setChecked(expanded)
        toggle_button.setText("v" if expanded else ">")
        content.setVisible(expanded)

    def _set_requested_tab(self, tab_name: str) -> None:
        normalized = tab_name.strip().lower()
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index).strip().lower() == normalized:
                self.tabs.setCurrentIndex(index)
                return
        self.tabs.setCurrentIndex(0)

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

    body_label = QLabel("")
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
    layout.addWidget(project_list, 1)
    layout.addWidget(module_label)
    layout.addWidget(module_list, 1)

    panel.setStyleSheet(
        "background-color: #0b0b0e; border: 1px solid #1a1a22; border-radius: 10px;"
    )
    return panel, body_label, project_list, module_list


class InstrumentedScriptRunnerPanel(QWidget):
    def __init__(self, project_root_provider: Callable[[], Path | None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_root_provider = project_root_provider
        self.storage = InstrumentationStorage(INSTRUMENTATION_DB_PATH)
        self.storage.initialize_schema()
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.readyReadStandardOutput.connect(self._drain_process_output)
        self.process.readyReadStandardError.connect(self._drain_process_output)
        self.process.finished.connect(self._handle_process_finished)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self._refresh_state)
        self.current_run_id: str | None = None
        self.current_run_name: str | None = None
        self.current_script_path: Path | None = None
        self.current_args: list[str] = []
        self.current_started_at: str | None = None
        self.stop_timer: QTimer | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Instrumented Script Runner")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")

        script_row = QWidget()
        script_row_layout = QHBoxLayout(script_row)
        script_row_layout.setContentsMargins(0, 0, 0, 0)
        script_row_layout.setSpacing(6)
        script_label = QLabel("Script Path:")
        self.script_path_input = QLineEdit()
        self.script_path_input.setPlaceholderText("tests/fixtures/instrumentation/recursive_workload.py")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_script)
        script_row_layout.addWidget(script_label)
        script_row_layout.addWidget(self.script_path_input, 1)
        script_row_layout.addWidget(browse_button)

        args_row = QWidget()
        args_row_layout = QHBoxLayout(args_row)
        args_row_layout.setContentsMargins(0, 0, 0, 0)
        args_row_layout.setSpacing(6)
        args_label = QLabel("Args:")
        self.args_input = QLineEdit()
        self.args_input.setPlaceholderText("--depth 12")
        args_row_layout.addWidget(args_label)
        args_row_layout.addWidget(self.args_input, 1)

        controls_row = QWidget()
        controls_layout = QHBoxLayout(controls_row)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.start_button = QPushButton("Start Run")
        self.stop_button = QPushButton("Stop Run")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self._start_run)
        self.stop_button.clicked.connect(self._stop_run)
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addStretch()

        self.metadata_block = QLabel()
        self.metadata_block.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.metadata_block.setStyleSheet("border: 1px solid #1a1a22; padding: 8px;")

        self.hot_files_list = QTreeWidget()
        self.hot_files_list.setHeaderLabels(["File", "Score", "Raw ms", "Calls"])
        self.hot_files_list.setRootIsDecorated(False)

        self.cpu_memory_block = QLabel("CPU: -\nRSS: -")
        self.cpu_memory_block.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.cpu_memory_block.setStyleSheet("border: 1px solid #1a1a22; padding: 8px;")

        self.summary_block = QPlainTextEdit()
        self.summary_block.setReadOnly(True)
        self.summary_block.setMaximumBlockCount(200)
        self.summary_block.setPlainText("No completed run.")

        self.debug_toggle = QToolButton()
        self.debug_toggle.setText("Debug Details")
        self.debug_toggle.setCheckable(True)
        self.debug_toggle.setChecked(False)
        self.debug_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.debug_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.debug_toggle.clicked.connect(self._toggle_debug_drawer)

        self.debug_details = QPlainTextEdit()
        self.debug_details.setReadOnly(True)
        self.debug_details.setVisible(False)
        self.debug_details.setMaximumBlockCount(400)

        layout.addWidget(title)
        layout.addWidget(script_row)
        layout.addWidget(args_row)
        layout.addWidget(controls_row)
        layout.addWidget(QLabel("Run Metadata"))
        layout.addWidget(self.metadata_block)
        layout.addWidget(QLabel("Live Hot Files"))
        layout.addWidget(self.hot_files_list, 1)
        layout.addWidget(QLabel("CPU / Memory"))
        layout.addWidget(self.cpu_memory_block)
        layout.addWidget(QLabel("Run Summary"))
        layout.addWidget(self.summary_block)
        layout.addWidget(self.debug_toggle)
        layout.addWidget(self.debug_details)
        self.setStyleSheet("border: 1px solid #1a1a22; border-radius: 10px;")
        self._reset_panels()

    def _browse_script(self) -> None:
        starting_dir = str(self.project_root_provider() or PROJECT_ROOT)
        script_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select Python Script",
            starting_dir,
            "Python Files (*.py)",
        )
        if script_path:
            self.script_path_input.setText(script_path)

    def _start_run(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        script_path = Path(self.script_path_input.text().strip()).expanduser()
        if not script_path.is_absolute():
            script_path = (self.project_root_provider() or PROJECT_ROOT) / script_path
        script_path = script_path.resolve()
        if not script_path.is_file():
            QMessageBox.warning(self, "Invalid Script", "Select a valid Python script to run.")
            return

        try:
            parsed_args = shlex.split(self.args_input.text().strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Args", str(exc))
            return

        project_root = self._resolve_project_root(script_path)
        run_name = f"{script_path.stem}_{datetime.now().strftime('%H%M%S')}"
        self.current_run_name = run_name
        self.current_run_id = f"{script_path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.current_script_path = script_path
        self.current_args = parsed_args
        self.current_started_at = datetime.now().isoformat()
        self._reset_panels()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.metadata_block.setText(self._metadata_text("starting", 0.0))

        process_args = [
            "-m",
            "backend.instrumentation.script_runner",
            "--database",
            str(INSTRUMENTATION_DB_PATH),
            "--project-root",
            str(project_root),
            "--script-path",
            str(script_path),
            "--run-name",
            run_name,
            "--scenario-kind",
            "instrumented_script",
            "--hardware-profile",
            f"{sys.platform}:{platform_string()}",
            "--",
            *parsed_args,
        ]
        self.process.start(sys.executable, process_args)
        if not self.process.waitForStarted(3000):
            QMessageBox.warning(self, "Runner Failed", "Failed to start instrumented run.")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return

        self.current_run_id = self._read_latest_run_id(run_name)
        self.refresh_timer.start()

    def _stop_run(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.stop_button.setEnabled(False)
        self.metadata_block.setText(self._metadata_text("stopping", self._current_elapsed_seconds()))
        self.process.terminate()
        if self.stop_timer is not None:
            self.stop_timer.stop()
        self.stop_timer = QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self._force_kill_process)
        self.stop_timer.start(3000)

    def _force_kill_process(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _handle_process_finished(self, _exit_code: int, _exit_status) -> None:
        self.refresh_timer.stop()
        if self.stop_timer is not None:
            self.stop_timer.stop()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._refresh_state()

    def _drain_process_output(self) -> None:
        _ = bytes(self.process.readAllStandardOutput())
        _ = bytes(self.process.readAllStandardError())

    def _refresh_state(self) -> None:
        if not self.current_run_id:
            return
        live_state = self.storage.fetch_live_run_state(self.current_run_id)
        if live_state is None:
            if self.current_run_name:
                resolved_run_id = self.storage.fetch_latest_run_id_by_name(self.current_run_name)
                if resolved_run_id and resolved_run_id != self.current_run_id:
                    self.current_run_id = resolved_run_id
                    live_state = self.storage.fetch_live_run_state(self.current_run_id)
            if live_state is None:
                self.metadata_block.setText(self._metadata_text("pending", self._current_elapsed_seconds()))
                return
        parsed_args = json.loads(str(live_state["parsed_args_json"]))
        elapsed_seconds = float(live_state["elapsed_seconds"])
        self.metadata_block.setText(
            "\n".join(
                [
                    f"Run Name: {self.current_run_id}",
                    f"Script: {live_state['script_path']}",
                    f"Args: {' '.join(parsed_args) if parsed_args else '(none)'}",
                    f"Started: {str(live_state['started_at'])}",
                    f"Elapsed: {self._format_elapsed(elapsed_seconds)}",
                    f"Status: {live_state['status']}",
                ]
            )
        )
        self.cpu_memory_block.setText(
            f"CPU: {float(live_state['cpu_percent']):.1f}%\nRSS: {float(live_state['rss_mb']):.1f} MB"
        )
        self._populate_hot_files()
        self._populate_summary()
        self._populate_debug(live_state)

    def _populate_hot_files(self) -> None:
        self.hot_files_list.clear()
        if not self.current_run_id:
            return
        rows = self.storage.fetch_live_file_rows(self.current_run_id)
        ordered_rows = sorted(
            rows,
            key=lambda row: (-float(row["rolling_score"]), -float(row["raw_ms"]), str(row["file_path"])),
        )[:10]
        for row in ordered_rows:
            item = QTreeWidgetItem(
                [
                    Path(str(row["file_path"])).name,
                    f"{float(row['rolling_score']):.1f}",
                    f"{float(row['raw_ms']):.1f}",
                    f"{int(row['call_count'])}",
                ]
            )
            self.hot_files_list.addTopLevelItem(item)

    def _populate_summary(self) -> None:
        if not self.current_run_id:
            return
        run_summary = self.storage.fetch_run_summary(self.current_run_id)
        file_summaries = self.storage.fetch_file_summaries(self.current_run_id, limit=10)
        if run_summary is None:
            self.summary_block.setPlainText("Summary pending aggregation.")
            return
        hottest_files = json.loads(str(run_summary["hottest_files_json"]))
        deltas = json.loads(str(run_summary["biggest_score_deltas_json"]))
        lines = ["Hottest Files"]
        for row in hottest_files:
            lines.append(
                f"- {Path(str(row['file_path'])).name}: {float(row['rolling_score']):.1f} rolling, {float(row['total_time_ms']):.1f} ms"
            )
        if file_summaries:
            lines.append("")
            lines.append("File Summaries")
            for row in file_summaries:
                lines.append(
                    f"- {row['file_path']}: score {float(row['normalized_compute_score']):.1f}, failures {int(row['exception_count'])}"
                )
        lines.append("")
        lines.append("Biggest Deltas")
        if deltas:
            for row in deltas:
                lines.append(f"- {row['file_path']}: {float(row['score_delta']):+.1f}")
        else:
            lines.append("- none")
        lines.append("")
        lines.append(f"Failures: {int(run_summary['failure_count'])}")
        self.summary_block.setPlainText("\n".join(lines))

    def _populate_debug(self, live_state) -> None:
        if not self.current_run_id:
            return
        lines = [
            f"Aggregation Status: {live_state['aggregation_status']}",
            f"Raw Function Row Count: {int(live_state['raw_function_row_count'])}",
            f"Sampler Sample Count: {int(live_state['sampler_sample_count'])}",
            f"Final Function Summary Count: {self.storage.fetch_function_summary_count(self.current_run_id)}",
            "",
            "External Buckets:",
        ]
        external_buckets = json.loads(str(live_state["external_buckets_json"]))
        if external_buckets:
            for row in external_buckets:
                lines.append(
                    f"- {row['bucket_name']}: {float(row['total_time_ms']):.1f} ms / {int(row['call_count'])} calls"
                )
        else:
            lines.append("- none")
        stdout_tail = str(live_state["stdout_tail"] or "")
        stderr_tail = str(live_state["stderr_tail"] or "")
        if stdout_tail:
            lines.extend(["", "Stdout:", stdout_tail])
        if stderr_tail:
            lines.extend(["", "Stderr:", stderr_tail])
        self.debug_details.setPlainText("\n".join(lines))

    def _toggle_debug_drawer(self) -> None:
        expanded = self.debug_toggle.isChecked()
        self.debug_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.debug_details.setVisible(expanded)

    def _metadata_text(self, status: str, elapsed_seconds: float) -> str:
        script_path = str(self.current_script_path) if self.current_script_path is not None else "-"
        parsed_args = " ".join(self.current_args) if self.current_args else "(none)"
        started = self.current_started_at or "-"
        return "\n".join(
            [
                f"Run Name: {self.current_run_id or '-'}",
                f"Script: {script_path}",
                f"Args: {parsed_args}",
                f"Started: {started}",
                f"Elapsed: {self._format_elapsed(elapsed_seconds)}",
                f"Status: {status}",
            ]
        )

    def _reset_panels(self) -> None:
        self.hot_files_list.clear()
        self.cpu_memory_block.setText("CPU: -\nRSS: -")
        self.summary_block.setPlainText("No completed run.")
        self.debug_details.setPlainText("")

    def _resolve_project_root(self, script_path: Path) -> Path:
        current_project = self.project_root_provider()
        if current_project is not None:
            try:
                script_path.relative_to(current_project)
                return current_project
            except ValueError:
                pass
        return script_path.parent

    def _read_latest_run_id(self, run_name: str) -> str:
        run_id = self.storage.fetch_latest_run_id_by_name(run_name)
        return run_id or (self.current_run_id or run_name)

    def _current_elapsed_seconds(self) -> float:
        if self.current_started_at is None:
            return 0.0
        try:
            started = datetime.fromisoformat(self.current_started_at)
        except ValueError:
            return 0.0
        return max((datetime.now(started.tzinfo) - started).total_seconds(), 0.0)

    def _format_elapsed(self, elapsed_seconds: float) -> str:
        total_seconds = max(int(elapsed_seconds), 0)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def shutdown(self) -> None:
        self.refresh_timer.stop()
        if self.stop_timer is not None:
            self.stop_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)


def platform_string() -> str:
    return sys.platform


class BlueBenchWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("(╯°□°)╯︵ ┻━┻ Blue Bench")
        self.resize(1200, 700)
        self.settings = QSettings("BlueBench", "BlueBenchApp")
        self.storage = InstrumentationStorage(INSTRUMENTATION_DB_PATH)
        self.storage.initialize_schema()
        self.graph_bridge = GraphBridge()
        self.project_discovery = ProjectDiscovery(DEV_ROOT)
        self.project_loader = ProjectLoader(
            self.graph_bridge.graph_manager,
            PythonRepoScanner,
        )
        self.current_project_path: Path | None = None
        self.active_run_id: str | None = None
        self.node_windows: dict[str, NodeInspectorWindow] = {}
        self._inspector_open_count = 0
        self.stress_engine_window: StressEngineWindow | None = None
        self.triage_window: TriageWindow | None = None

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
        run_label = QLabel("Run")
        self.run_selector = QComboBox()
        self.run_selector.setMinimumWidth(320)
        self.run_selector.currentIndexChanged.connect(self._handle_run_selection)
        self.run_view_selector = QComboBox()
        self.run_view_selector.addItem("Current", "current")
        self.run_view_selector.addItem("Previous Comparable", "previous")
        self.run_view_selector.currentIndexChanged.connect(self._handle_run_view_selection)
        self.refresh_runs_button = QPushButton("Refresh Runs")
        self.refresh_runs_button.clicked.connect(self._refresh_run_selector)
        self.export_button = QPushButton("Export Layout")
        self.export_button.clicked.connect(self._export_layout_document)
        self.context_mode_selector = QComboBox()
        self.context_mode_selector.addItem("AI Tiny", "tiny")
        self.context_mode_selector.addItem("AI Short", "short")
        self.context_mode_selector.addItem("AI Full", "full")
        self.context_export_button = QPushButton("Export AI Context")
        self.context_export_button.clicked.connect(self._export_ai_context)
        self.stress_engine_button = QPushButton("Stress Engine")
        self.stress_engine_button.clicked.connect(self._open_stress_engine)
        self.triage_button = QPushButton("New App Triage")
        self.triage_button.clicked.connect(self._open_triage_window)
        self.active_run_badge = QLabel("Active Run: none")
        self.active_run_badge.setStyleSheet(
            "padding: 8px 10px; border: 1px solid #1a1a22; background-color: #111116; color: #cdbfae;"
        )
        self.active_run_badge.setWordWrap(True)

        layout_controls_layout.addWidget(layout_label)
        layout_controls_layout.addStretch()
        layout_controls_layout.addWidget(run_label)
        layout_controls_layout.addWidget(self.run_selector)
        layout_controls_layout.addWidget(self.run_view_selector)
        layout_controls_layout.addWidget(self.refresh_runs_button)
        layout_controls_layout.addWidget(self.triage_button)
        layout_controls_layout.addWidget(self.stress_engine_button)
        layout_controls_layout.addWidget(self.context_mode_selector)
        layout_controls_layout.addWidget(self.context_export_button)
        layout_controls_layout.addWidget(self.export_button)

        graph_view = QWebEngineView()
        graph_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.graph_view = graph_view
        self.web_channel = QWebChannel(graph_view.page())
        self.web_channel.registerObject("graphBridge", self.graph_bridge)
        graph_view.page().setWebChannel(self.web_channel)
        graph_view.load(QUrl.fromLocalFile(str(GRAPH_HTML_PATH)))

        center_layout.addWidget(layout_controls)
        center_layout.addWidget(self.active_run_badge)
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
        self._restore_run_view_mode()
        self._refresh_run_selector()
        self._restore_active_run_selection()
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
        self._refresh_run_selector()
        self._persist_context_session_state()
        self.graph_bridge.set_project_tree(
            project_path,
            self.graph_bridge.graph_manager.build_codebase_tree(project_path, file_paths),
        )
        self._apply_active_run_context()
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

    def _export_ai_context(self) -> None:
        if not self.current_project_path:
            QMessageBox.information(self, "Export AI Context", "Load a project before exporting AI context.")
            return
        context_mode = str(self.context_mode_selector.currentData() or "short")
        context_pack = build_context_pack(
            self.current_project_path,
            self.active_run_id,
            self._run_view_mode(),
            mode=context_mode,
            storage=self.storage,
            session_state=self._context_session_state(),
            focus_targets=self._focus_targets(),
            open_files=self._open_file_paths(),
        )
        export_root = self.current_project_path / ".bluebench"
        json_path = export_context_json(context_pack, export_root / f"bb_context_{context_mode}.json")
        markdown_path = export_context_markdown(context_pack, export_root / f"bb_context_{context_mode}.md")
        self._persist_context_session_state(last_context_mode=context_mode)
        QMessageBox.information(
            self,
            "Export AI Context",
            f"Exported AI context.\n\nJSON: {json_path}\nMarkdown: {markdown_path}",
        )

    def _open_stress_engine(self) -> None:
        if self.stress_engine_window is None:
            self.stress_engine_window = StressEngineWindow(
                lambda: self.current_project_path,
                lambda payload: self.open_inspector_from_explorer(payload),
            )
            self.stress_engine_window.closed.connect(self._clear_stress_engine_window)
        self.stress_engine_window.show()
        self.stress_engine_window.raise_()
        self.stress_engine_window.activateWindow()

    def _open_triage_window(self) -> None:
        if self.triage_window is None:
            self.triage_window = TriageWindow(
                lambda: self.current_project_path,
                self.storage,
                self.open_inspector_from_explorer,
            )
            self.triage_window.closed.connect(self._clear_triage_window)
        self.triage_window.show()
        self.triage_window.raise_()
        self.triage_window.activateWindow()

    def _clear_stress_engine_window(self) -> None:
        self._refresh_run_selector()
        self.stress_engine_window = None

    def _clear_triage_window(self) -> None:
        self.triage_window = None

    def _update_inspector(self, payload: dict) -> None:
        node = payload.get("node") or payload
        if not node:
            return
        if not self.current_project_path:
            return

        node_id = str(node.get("id") or "")
        if not node_id:
            return

        inspector_payload = self._build_inspector_payload(node, payload.get("preferred_tab"))
        existing_window = self.node_windows.get(node_id)
        if existing_window is not None:
            existing_window.refresh(inspector_payload)
            existing_window.raise_()
            existing_window.activateWindow()
            return

        inspector_window = NodeInspectorWindow(
            self.graph_bridge.graph_manager,
            self.current_project_path,
            inspector_payload,
            self._remove_node_window,
            self.open_inspector_from_explorer,
        )
        self._position_inspector_window(inspector_window)
        self.node_windows[node_id] = inspector_window
        inspector_window.show()
        self._persist_context_session_state()

    def open_inspector_from_explorer(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return

        file_path = payload.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            return

        node = self.graph_bridge.graph_manager.get_node_by_file_path(file_path)
        if node is None:
            return

        inspector_payload = self._build_inspector_payload(node, payload.get("preferred_tab"))
        self._update_inspector(inspector_payload)

    def _build_inspector_payload(self, node: dict[str, object], preferred_tab: object = None) -> dict[str, object]:
        file_path = str(node.get("file_path") or "")
        display_run_id = self._display_run_id()
        active_run_name = ""
        active_run_scenario = ""
        active_run_hardware = ""
        active_run_status = ""
        active_run_finished_at = ""
        active_run_failure_count: int | None = None
        previous_run_name = ""
        previous_run_id = ""
        previous_run_finished_at = ""
        if display_run_id:
            run_row = self.storage.fetch_run(display_run_id)
            if run_row is not None:
                active_run_name = str(run_row["run_name"] or "")
                active_run_scenario = str(run_row["scenario_kind"] or "")
                active_run_hardware = str(run_row["hardware_profile"] or "")
                active_run_status = str(run_row["status"] or "")
                active_run_finished_at = str(run_row["finished_at"] or "")
                run_summary = self.storage.fetch_run_summary(display_run_id)
                if run_summary is not None:
                    active_run_failure_count = int(run_summary["failure_count"])
                previous_run = self.get_previous_comparable_run(display_run_id)
                if previous_run is not None:
                    previous_run_name = str(previous_run.get("run_name") or "")
                    previous_run_id = str(previous_run.get("run_id") or "")
                    previous_run_finished_at = str(previous_run.get("finished_at") or "")
        payload = {
            "id": node.get("id"),
            "name": node.get("name"),
            "type": node.get("type"),
            "file_path": file_path,
            "line_number": node.get("line_number"),
            "line_start": node.get("line_start"),
            "line_end": node.get("line_end"),
            "compute_score": node.get("compute_score"),
            "parent": node.get("parent"),
            "call_path_total_compute": node.get("call_path_total_compute"),
            "active_run_id": display_run_id,
            "selected_run_id": self.active_run_id,
            "run_view_mode": self._run_view_mode(),
            "active_run_name": active_run_name,
            "active_run_scenario": active_run_scenario,
            "active_run_hardware": active_run_hardware,
            "active_run_status": active_run_status,
            "active_run_finished_at": active_run_finished_at,
            "active_run_failure_count": active_run_failure_count,
            "previous_run_name": previous_run_name,
            "previous_run_id": previous_run_id,
            "previous_run_finished_at": previous_run_finished_at,
            "file_compute": self.get_file_compute_for_run(display_run_id, file_path),
            "function_compute": self.get_function_compute_for_run(display_run_id, file_path),
        }
        if isinstance(preferred_tab, str) and preferred_tab:
            payload["preferred_tab"] = preferred_tab
        return payload

    def _remove_node_window(self, node_id: str) -> None:
        self.node_windows.pop(node_id, None)
        self._persist_context_session_state()

    def _close_all_node_windows(self) -> None:
        for node_id, window in list(self.node_windows.items()):
            window.close()
            self.node_windows.pop(node_id, None)
        self._persist_context_session_state()

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
        if self.stress_engine_window is not None:
            self.stress_engine_window.close()
        if self.triage_window is not None:
            self.triage_window.close()
        self._persist_context_session_state()
        self.settings.setValue("splitterState", self.main_splitter.saveState())
        super().closeEvent(event)

    def list_available_runs(self) -> list[dict[str, object]]:
        return [
            dict(row)
            for row in self.storage.list_completed_runs(project_root=self.current_project_path)
        ]

    def get_active_run_id(self) -> str | None:
        return self._display_run_id()

    def set_active_run_id(self, run_id: str | None) -> None:
        normalized = run_id if run_id and self.storage.run_exists(run_id) else None
        self.active_run_id = normalized
        if normalized is None:
            self.settings.remove("activeRunId")
        else:
            self.settings.setValue("activeRunId", normalized)
        self._update_active_run_badge()
        self._apply_active_run_context()
        self._refresh_open_inspectors()
        self._persist_context_session_state()

    def _run_view_mode(self) -> str:
        return str(self.run_view_selector.currentData() or "current")

    def _restore_run_view_mode(self) -> None:
        stored_mode = str(self.settings.value("runViewMode") or "current")
        index = self.run_view_selector.findData(stored_mode)
        self.run_view_selector.setCurrentIndex(index if index >= 0 else 0)

    def _handle_run_view_selection(self) -> None:
        self.settings.setValue("runViewMode", self._run_view_mode())
        self._update_active_run_badge()
        self._apply_active_run_context()
        self._refresh_open_inspectors()
        self._persist_context_session_state()

    def _display_run(self) -> dict[str, object] | None:
        if not self.active_run_id:
            return None
        if self._run_view_mode() != "previous":
            run_row = self.storage.fetch_run(self.active_run_id)
            return dict(run_row) if run_row is not None else None
        return self.get_previous_comparable_run(self.active_run_id)

    def _display_run_id(self) -> str | None:
        display_run = self._display_run()
        if display_run is None:
            return None
        return str(display_run.get("run_id") or "")

    def get_previous_comparable_run(self, run_id: str | None) -> dict[str, object] | None:
        if not run_id:
            return None
        run_row = self.storage.fetch_run(run_id)
        if run_row is None:
            return None
        previous_run_id = self.storage.fetch_previous_comparable_run_id(
            run_id,
            str(run_row["scenario_kind"]),
            str(run_row["hardware_profile"]),
            run_row["project_root"],
        )
        if not previous_run_id:
            return None
        previous_row = self.storage.fetch_run(previous_run_id)
        return dict(previous_row) if previous_row is not None else None

    def get_file_compute_for_run(self, run_id: str | None, file_path: str) -> dict[str, object]:
        if not run_id or not file_path:
            return {}
        row = self.storage.fetch_file_summary(run_id, file_path)
        if row is None:
            return {}
        current_score = float(row["normalized_compute_score"])
        delta: float | None = None
        run_row = self.storage.fetch_run(run_id)
        if run_row is not None:
            previous_run_id = self.storage.fetch_previous_comparable_run_id(
                run_id,
                str(run_row["scenario_kind"]),
                str(run_row["hardware_profile"]),
                run_row["project_root"],
            )
            if previous_run_id:
                previous_row = self.storage.fetch_file_summary(previous_run_id, file_path)
                previous_score = float(previous_row["normalized_compute_score"]) if previous_row is not None else 0.0
                delta = current_score - previous_score
        external_summary = json.loads(str(row["external_pressure_summary"])) if row["external_pressure_summary"] else {}
        return {
            "file_path": str(row["file_path"]),
            "normalized_compute_score": current_score,
            "compute_tier": 9 if current_score >= 67 else 6 if current_score >= 34 else 3,
            "compute_tally": current_score,
            "total_self_time_ms": float(row["total_self_time_ms"]),
            "total_time_ms": float(row["total_time_ms"]),
            "call_count": int(row["call_count"]),
            "exception_count": int(row["exception_count"]),
            "rolling_score": float(row["rolling_score"]),
            "delta": delta,
            "external_pressure_summary": external_summary if isinstance(external_summary, dict) else {},
        }

    def get_function_compute_for_run(self, run_id: str | None, file_path: str) -> list[dict[str, object]]:
        if not run_id or not file_path:
            return []
        function_compute: list[dict[str, object]] = []
        for row in self.storage.fetch_function_summaries_for_file(run_id, file_path):
            symbol_key = str(row["symbol_key"])
            symbol_name = symbol_key.split("::", 1)[1] if "::" in symbol_key else str(row["display_name"])
            function_compute.append(
                {
                    "symbol_key": symbol_key,
                    "symbol_name": symbol_name,
                    "display_name": str(row["display_name"]),
                    "self_time_ms": float(row["self_time_ms"]),
                    "total_time_ms": float(row["total_time_ms"]),
                    "call_count": int(row["call_count"]),
                    "exception_count": int(row["exception_count"]),
                    "last_exception_type": row["last_exception_type"],
                    "normalized_compute_score": float(row["normalized_compute_score"]),
                }
            )
        return function_compute

    def _refresh_run_selector(self) -> None:
        selected_run_id = self.active_run_id
        available_run_ids = {str(row["run_id"]) for row in self.list_available_runs()}
        if selected_run_id and selected_run_id not in available_run_ids:
            self.active_run_id = None
            self.settings.remove("activeRunId")
            selected_run_id = None
        self.run_selector.blockSignals(True)
        self.run_selector.clear()
        self.run_selector.addItem("No Active Run", "")
        for row in self.list_available_runs():
            run_id = str(row["run_id"])
            finished_at = str(row.get("finished_at") or row.get("started_at") or "")
            label = f"{row['run_name']} · {row['scenario_kind']} · {finished_at}"
            self.run_selector.addItem(label, run_id)
        index = self.run_selector.findData(selected_run_id or "")
        self.run_selector.setCurrentIndex(index if index >= 0 else 0)
        self.run_selector.blockSignals(False)
        self._update_active_run_badge()
        self._persist_context_session_state()

    def _restore_active_run_selection(self) -> None:
        stored_run_id = self.settings.value("activeRunId")
        if isinstance(stored_run_id, str) and stored_run_id and self.storage.run_exists(stored_run_id):
            self.active_run_id = stored_run_id
        else:
            self.active_run_id = None
        self._refresh_run_selector()
        self._update_active_run_badge()
        self._persist_context_session_state()

    def _handle_run_selection(self) -> None:
        selected_run_id = str(self.run_selector.currentData() or "").strip() or None
        self.set_active_run_id(selected_run_id)

    def _apply_active_run_context(self) -> None:
        display_run_id = self._display_run_id()
        if not display_run_id:
            self.graph_bridge.set_active_run_context(None, {})
            self._refresh_renderer()
            return
        file_compute_context: dict[str, dict[str, object]] = {}
        for row in self.storage.fetch_file_summaries(display_run_id, limit=None):
            file_path = str(row["file_path"])
            compute_entry = self.get_file_compute_for_run(display_run_id, file_path)
            if not compute_entry:
                continue
            shallow_external = self._shallow_external_summary(compute_entry.get("external_pressure_summary"))
            if shallow_external is not None:
                compute_entry["external_summary"] = shallow_external
            file_compute_context[file_path] = compute_entry
        self.graph_bridge.set_active_run_context(display_run_id, file_compute_context)
        self._refresh_renderer()

    def _refresh_open_inspectors(self) -> None:
        for node_id, window in list(self.node_windows.items()):
            node = self.graph_bridge.graph_manager.get_node(node_id)
            if node is None:
                continue
            preferred_tab = window.tabs.tabText(window.tabs.currentIndex())
            window.refresh(self._build_inspector_payload(node, preferred_tab))

    def _shallow_external_summary(self, summary: object) -> str | None:
        if not isinstance(summary, dict):
            return None
        buckets = summary.get("external_buckets")
        if not isinstance(buckets, dict):
            return None
        top_bucket_name = ""
        top_bucket_ms = 0.0
        for bucket_name, values in buckets.items():
            if not isinstance(values, dict):
                continue
            total_time_ms = float(values.get("total_time_ms") or 0.0)
            if total_time_ms > top_bucket_ms:
                top_bucket_name = str(bucket_name).replace("external:", "")
                top_bucket_ms = total_time_ms
        if not top_bucket_name or top_bucket_ms <= 0.0:
            return None
        return f"{top_bucket_name} {top_bucket_ms:.0f} ms"

    def _update_active_run_badge(self) -> None:
        if not self.active_run_id:
            self.active_run_badge.setText("Active Run: none")
            return
        selected_run = self.storage.fetch_run(self.active_run_id)
        if selected_run is None:
            self.active_run_badge.setText("Active Run: none")
            return
        display_run = self._display_run()
        if display_run is None:
            self.active_run_badge.setText(f"Selected Run: {selected_run['run_name']}\nPrevious comparable run unavailable")
            return
        display_run_id = str(display_run.get("run_id") or "")
        lines = [
            f"Selected Run: {selected_run['run_name']}",
            f"Viewing: {'Previous Comparable' if self._run_view_mode() == 'previous' else 'Current Run'}",
            f"Compute Source: {display_run['run_name']}",
            f"{display_run['scenario_kind']} · {display_run['hardware_profile']}",
        ]
        run_summary = self.storage.fetch_run_summary(display_run_id)
        if run_summary is not None:
            lines.append(f"Failures {int(run_summary['failure_count'])}")
        previous_run = self.get_previous_comparable_run(display_run_id)
        if previous_run is not None and previous_run.get("run_name"):
            lines.append(f"Previous {previous_run['run_name']}")
        quality_lines = self._run_quality_lines(display_run_id)
        lines.extend(quality_lines)
        self.active_run_badge.setText("\n".join(lines))

    def _run_quality_lines(self, run_id: str | None) -> list[str]:
        if not run_id:
            return []
        lines: list[str] = []
        run_summary = self.storage.fetch_run_summary(run_id)
        if run_summary is not None and int(run_summary["failure_count"]) > 0:
            lines.append(f"Quality warning: {int(run_summary['failure_count'])} failures recorded")
        if self.get_previous_comparable_run(run_id) is None:
            lines.append("Quality note: no previous comparable run")
        file_count = len(self.storage.fetch_file_summaries(run_id, limit=None))
        if file_count <= 3:
            lines.append(f"Quality warning: low coverage ({file_count} files measured)")
        return lines

    def _open_file_paths(self) -> list[str]:
        open_files: list[str] = []
        for window in self.node_windows.values():
            file_path = str(window.node.get("file_path") or "").strip()
            if file_path and file_path not in open_files:
                open_files.append(file_path)
        return open_files

    def _focus_targets(self) -> list[dict[str, object]]:
        display_run_id = self._display_run_id()
        if not display_run_id:
            return []
        targets: list[dict[str, object]] = []
        for row in self.storage.fetch_file_summaries(display_run_id, limit=3):
            targets.append(
                {
                    "file_path": str(row["file_path"]),
                    "reason": "hot_file",
                    "confidence": "high",
                    "score": float(row["normalized_compute_score"]),
                }
            )
        return targets

    def _context_session_state(self, *, last_context_mode: str | None = None) -> dict[str, object]:
        project_root = str(self.current_project_path.resolve()) if self.current_project_path else ""
        triage_mode_selector = getattr(self.triage_window, "mode_selector", None)
        triage_mode = "quick"
        if triage_mode_selector is not None and triage_mode_selector.currentData() == "full":
            triage_mode = "full"
        return {
            "project_root": project_root,
            "selected_run_id": self.active_run_id,
            "display_run_id": self._display_run_id(),
            "run_view_mode": self._run_view_mode(),
            "open_files": self._open_file_paths(),
            "focus_targets": self._focus_targets(),
            "last_triage_mode": triage_mode,
            "last_context_mode": last_context_mode or str(self.context_mode_selector.currentData() or "short"),
        }

    def _persist_context_session_state(self, *, last_context_mode: str | None = None) -> None:
        if not self.current_project_path:
            return
        save_session_state(self.current_project_path, self._context_session_state(last_context_mode=last_context_mode))

def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = BlueBenchWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
