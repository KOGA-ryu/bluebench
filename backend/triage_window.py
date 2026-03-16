from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from backend.instrumentation.storage import InstrumentationStorage
from backend.triage import export_triage_json, export_triage_markdown, generate_triage


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- none"]


class TriageWindow(QWidget):
    closed = Signal()

    def __init__(
        self,
        project_root_provider,
        storage: InstrumentationStorage,
        open_file_inspector=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_root_provider = project_root_provider
        self.storage = storage
        self.open_file_inspector = open_file_inspector
        self.current_triage: dict[str, object] | None = None
        self.current_project_root: Path | None = None

        self.setWindowTitle("New App Triage")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        self.project_label = QLabel("Project: none")
        self.project_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #d8d8df;")
        self.run_selector = QComboBox()
        self.run_selector.setMinimumWidth(320)
        self.mode_selector = QComboBox()
        self.mode_selector.addItem("Quick", "quick")
        self.mode_selector.addItem("Full", "full")
        self.generate_button = QPushButton("Generate Triage")
        self.export_md_button = QPushButton("Export Markdown")
        self.export_json_button = QPushButton("Export JSON")
        self.refresh_runs_button = QPushButton("Refresh Runs")
        self.open_hot_file_button = QPushButton("Open Top Hot File")
        self.open_regression_button = QPushButton("Open Top Regression")
        self.open_entry_button = QPushButton("Open Top Entry")

        self.generate_button.clicked.connect(self._generate_triage)
        self.export_md_button.clicked.connect(self._export_markdown)
        self.export_json_button.clicked.connect(self._export_json)
        self.refresh_runs_button.clicked.connect(self._refresh_run_selector)
        self.open_hot_file_button.clicked.connect(self._open_top_hot_file)
        self.open_regression_button.clicked.connect(self._open_top_regression)
        self.open_entry_button.clicked.connect(self._open_top_entry)

        controls_layout.addWidget(self.project_label, 1)
        controls_layout.addWidget(QLabel("Run"))
        controls_layout.addWidget(self.run_selector)
        controls_layout.addWidget(QLabel("Mode"))
        controls_layout.addWidget(self.mode_selector)
        controls_layout.addWidget(self.refresh_runs_button)
        controls_layout.addWidget(self.generate_button)
        controls_layout.addWidget(self.open_hot_file_button)
        controls_layout.addWidget(self.open_regression_button)
        controls_layout.addWidget(self.open_entry_button)
        controls_layout.addWidget(self.export_md_button)
        controls_layout.addWidget(self.export_json_button)

        self.context_block = QLabel("No project loaded.")
        self.context_block.setWordWrap(True)
        self.context_block.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.context_block.setStyleSheet(
            "padding: 8px 10px; border: 1px solid #1a1a22; background-color: #111116; color: #cdbfae;"
        )

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        self.project_summary_block = self._create_section_block("Project Summary")
        self.architecture_block = self._create_section_block("Architecture Snapshot")
        self.runtime_block = self._create_section_block("Runtime Evidence")
        self.risks_block = self._create_section_block("Risks")
        self.recommendations_block = self._create_section_block("Recommended Actions")

        for widget in [
            self.project_summary_block,
            self.architecture_block,
            self.runtime_block,
            self.risks_block,
            self.recommendations_block,
        ]:
            content_layout.addWidget(widget)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        layout.addWidget(controls)
        layout.addWidget(self.context_block)
        layout.addWidget(scroll, 1)

        self._refresh_project_context()
        self._apply_initial_geometry()
        self._reset_sections()
        self._update_action_buttons()

    def _create_section_block(self, title: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(title)
        label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #d8d8df; letter-spacing: 0.04em; text-transform: uppercase;"
        )
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setMaximumBlockCount(400)
        text.setFrameShape(QFrame.Shape.Box)
        text.setStyleSheet("border: 1px solid #1a1a22; background-color: #0d0c11; color: #d8d8df;")
        layout.addWidget(label)
        layout.addWidget(text)
        widget._text_widget = text  # type: ignore[attr-defined]
        return widget

    def _section_editor(self, section_widget: QWidget) -> QPlainTextEdit:
        return section_widget._text_widget  # type: ignore[attr-defined]

    def _refresh_project_context(self) -> None:
        project_root = self.project_root_provider()
        self.current_project_root = project_root.resolve() if isinstance(project_root, Path) else None
        if self.current_project_root is None:
            self.project_label.setText("Project: none")
            self.context_block.setText("No project loaded.")
            self.run_selector.clear()
            self.run_selector.addItem("No completed run", "")
        self.generate_button.setEnabled(False)
        self._update_action_buttons()
        return

        self.project_label.setText(f"Project: {self.current_project_root.name}")
        self.context_block.setText(
            "\n".join(
                [
                    f"Project Root: {self.current_project_root}",
                    "Generate a static or run-aware triage report for the current project.",
                ]
            )
        )
        self.generate_button.setEnabled(True)
        self._refresh_run_selector()
        self._update_action_buttons()

    def _refresh_run_selector(self) -> None:
        self.run_selector.clear()
        self.run_selector.addItem("No completed run", "")
        if self.current_project_root is None:
            return
        for row in self.storage.list_completed_runs(project_root=self.current_project_root):
            run_id = str(row["run_id"])
            label = f"{row['run_name']} · {row['scenario_kind']} · {row['finished_at'] or row['started_at']}"
            self.run_selector.addItem(label, run_id)

    def _generate_triage(self) -> None:
        self._refresh_project_context()
        if self.current_project_root is None:
            QMessageBox.warning(self, "No Project", "Load a project before generating triage.")
            return
        run_id = str(self.run_selector.currentData() or "").strip() or None
        mode = str(self.mode_selector.currentData() or "quick")
        try:
            self.current_triage = generate_triage(
                self.current_project_root,
                run_id=run_id,
                mode=mode,
                storage=self.storage,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Triage Failed", str(exc))
            return
        self._render_triage(self.current_triage)
        self._update_action_buttons()

    def _render_triage(self, triage: dict[str, object]) -> None:
        project = dict(triage.get("project") or {})
        runtime_context = dict(triage.get("runtime_context") or {})
        architecture = dict(triage.get("architecture") or {})
        compute = dict(triage.get("compute") or {})
        risks = dict(triage.get("operational_risks") or {})
        recommendations = list(triage.get("recommended_actions") or [])
        hypotheses = list(triage.get("hypotheses") or [])

        selected_run = runtime_context.get("selected_run")
        run_line = "Run: none"
        if isinstance(selected_run, dict):
            run_line = (
                f"Run: {selected_run.get('run_name', '-')} · "
                f"{selected_run.get('scenario_kind', '-')} · "
                f"{selected_run.get('hardware_profile', '-')}"
            )
        self.context_block.setText(
            "\n".join(
                [
                    f"Project Root: {project.get('root', '-')}",
                    run_line,
                    f"Mode: {triage.get('mode', '-')}",
                ]
            )
        )

        self._section_editor(self.project_summary_block).setPlainText(
            "\n".join(
                [
                    f"Name: {project.get('name', '-')}",
                    f"App Type Guess: {project.get('app_type_guess', '-')}",
                    f"File Count: {int(project.get('file_count', 0))}",
                    "Top-level Areas:",
                    *_bullet_lines(
                        [
                            f"{item.get('name', '-')} ({int(item.get('file_count', 0))} files)"
                            for item in project.get("top_level_areas", []) or []
                        ]
                    ),
                    "Entry Points:",
                    *_bullet_lines(
                        [
                            f"{item.get('path', '-')} (score {int(item.get('score', 0))})"
                            for item in project.get("entry_points", []) or []
                        ]
                    ),
                ]
            )
        )

        self._section_editor(self.architecture_block).setPlainText(
            "\n".join(
                [
                    "Subsystem Candidates:",
                    *_bullet_lines(
                        [
                            f"{item.get('name', '-')} · {item.get('role', '-')}"
                            for item in architecture.get("suspected_subsystems", []) or []
                        ]
                    ),
                    "Relationship Hotspots:",
                    *_bullet_lines(
                        [
                            f"{item.get('file_path', '-')} · score {int(item.get('relationship_score', 0))}"
                            for item in architecture.get("relationship_hotspots", []) or []
                        ]
                    ),
                    "Coupling Notes:",
                    *_bullet_lines([str(item) for item in architecture.get("coupling_notes", []) or []]),
                    "Hypotheses:",
                    *_bullet_lines(
                        [
                            f"{item.get('title', '-')} [{item.get('confidence', '-')}]"
                            for item in hypotheses
                        ]
                    ),
                ]
            )
        )

        self._section_editor(self.runtime_block).setPlainText(
            "\n".join(
                [
                    "Hot Files:",
                    *_bullet_lines(
                        [
                            f"{item.get('file_path', '-')} · score {float(item.get('normalized_compute_score', 0.0)):.1f} · {float(item.get('total_time_ms', 0.0)):.1f} ms"
                            for item in compute.get("hot_files", []) or []
                        ]
                    ),
                    "Hot Functions:",
                    *_bullet_lines(
                        [
                            f"{item.get('display_name', '-')} · {item.get('file_path', '-')} · {float(item.get('total_time_ms', 0.0)):.1f} ms"
                            for item in compute.get("hot_functions", []) or []
                        ]
                    ),
                    "Regressions:",
                    *_bullet_lines(
                        [
                            f"{item.get('file_path', '-')} · {float(item.get('score_delta', 0.0)):+.1f}"
                            for item in compute.get("regressions", []) or []
                        ]
                    ),
                    "Quality Warnings:",
                    *_bullet_lines([str(item) for item in runtime_context.get("quality_warnings", []) or []]),
                ]
            )
        )

        self._section_editor(self.risks_block).setPlainText(
            "\n".join(
                [
                    "Native Dependencies:",
                    *_bullet_lines([str(item) for item in risks.get("native_dependencies", []) or []]),
                    "Optional Dependencies:",
                    *_bullet_lines([str(item) for item in risks.get("optional_dependencies", []) or []]),
                    "Native Risk Files:",
                    *_bullet_lines([str(item) for item in risks.get("native_risk_files", []) or []]),
                    "Launch Assumptions:",
                    *_bullet_lines([str(item) for item in risks.get("launch_assumptions", []) or []]),
                    "External Modules:",
                    *_bullet_lines([str(item) for item in risks.get("external_modules", []) or []]),
                ]
            )
        )

        self._section_editor(self.recommendations_block).setPlainText(
            "\n".join(
                [
                    "Recommended Actions:",
                    *_bullet_lines(
                        [
                            f"{int(item.get('priority', 0))}. {item.get('title', '-')} [{item.get('confidence', '-')}]"
                            for item in recommendations
                        ]
                    ),
                ]
            )
        )

    def _reset_sections(self) -> None:
        for section in [
            self.project_summary_block,
            self.architecture_block,
            self.runtime_block,
            self.risks_block,
            self.recommendations_block,
        ]:
            self._section_editor(section).setPlainText("No triage generated.")

    def _open_top_hot_file(self) -> None:
        if self.current_triage is None:
            return
        compute = dict(self.current_triage.get("compute") or {})
        hot_files = list(compute.get("hot_files") or [])
        if not hot_files:
            return
        self._open_file(str(hot_files[0].get("file_path") or ""), "Compute")

    def _open_top_regression(self) -> None:
        if self.current_triage is None:
            return
        compute = dict(self.current_triage.get("compute") or {})
        regressions = list(compute.get("regressions") or [])
        if not regressions:
            return
        self._open_file(str(regressions[0].get("file_path") or ""), "Compute")

    def _open_top_entry(self) -> None:
        if self.current_triage is None:
            return
        project = dict(self.current_triage.get("project") or {})
        entry_points = list(project.get("entry_points") or [])
        if not entry_points:
            return
        self._open_file(str(entry_points[0].get("path") or ""), "Code")

    def _open_file(self, file_path: str, preferred_tab: str) -> None:
        if not file_path or self.open_file_inspector is None:
            return
        self.open_file_inspector({"file_path": file_path, "preferred_tab": preferred_tab})

    def _update_action_buttons(self) -> None:
        has_triage = self.current_triage is not None
        compute = dict(self.current_triage.get("compute") or {}) if has_triage else {}
        project = dict(self.current_triage.get("project") or {}) if has_triage else {}
        hot_files = list(compute.get("hot_files") or [])
        regressions = list(compute.get("regressions") or [])
        entry_points = list(project.get("entry_points") or [])
        enabled = self.open_file_inspector is not None
        self.open_hot_file_button.setEnabled(enabled and bool(hot_files))
        self.open_regression_button.setEnabled(enabled and bool(regressions))
        self.open_entry_button.setEnabled(enabled and bool(entry_points))

    def _export_markdown(self) -> None:
        if self.current_triage is None or self.current_project_root is None:
            return
        default_path = self.current_project_root / "bb_triage_report.md"
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Triage Markdown",
            str(default_path),
            "Markdown (*.md)",
        )
        if not target_path:
            return
        export_triage_markdown(self.current_triage, Path(target_path))

    def _export_json(self) -> None:
        if self.current_triage is None or self.current_project_root is None:
            return
        default_path = self.current_project_root / "bb_triage_report.json"
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Triage JSON",
            str(default_path),
            "JSON (*.json)",
        )
        if not target_path:
            return
        export_triage_json(self.current_triage, Path(target_path))

    def _apply_initial_geometry(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 760)
            return
        available = screen.availableGeometry()
        width = min(1120, int(available.width() * 0.82))
        height = min(860, int(available.height() * 0.84))
        width = max(width, 860)
        height = max(height, 640)
        x = available.x() + max((available.width() - width) // 2, 0)
        y = available.y() + max((available.height() - height) // 2, 0)
        self.setGeometry(x, y, width, height)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._refresh_project_context()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.closed.emit()
        super().closeEvent(event)
