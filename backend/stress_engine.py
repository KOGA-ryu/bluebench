from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shlex
import sys

import os

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.instrumentation.storage import InstrumentationStorage
from backend.stress_spec import (
    BUILTIN_HARDWARE_PROFILES,
    SCENARIO_DEFAULTS,
    default_section_texts,
    dump_yaml_subset,
    parse_yaml_subset,
    verification_profile_label,
    verification_profile_note,
    verification_profile_spec,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTRUMENTATION_DB_PATH = PROJECT_ROOT / ".bluebench" / "instrumentation.sqlite3"
SECTION_GUIDANCE = {
    "Run": "Run identity and execution context. Set the name, target project root, and interpreter.",
    "Hardware": "Baseline hardware profile plus lightweight overrides for CPU and memory.",
    "Scenario": "Choose the workload target. Use custom_script for a real project entry point.",
    "Dashboard": "Controls live output priority order. Keep this short and operational.",
    "Save / Export": "Artifact settings for .bbtest output and future reuse.",
}


def platform_string() -> str:
    return sys.platform




class RunOutputStack(QWidget):
    fileRequested = Signal(object)

    def __init__(self, storage: InstrumentationStorage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.readyReadStandardOutput.connect(self._drain_process_output)
        self.process.readyReadStandardError.connect(self._drain_process_output)
        self.process.finished.connect(self._handle_process_finished)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.refresh_state)
        self.current_run_id: str | None = None
        self.current_run_name: str | None = None
        self.current_script_path: str = ""
        self.current_args: list[str] = []
        self.current_started_at: str | None = None
        self.current_project_root: Path = PROJECT_ROOT
        self.current_interpreter_path: str = sys.executable
        self.stop_timer: QTimer | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.start_button = QPushButton("Start Run")
        self.stop_button = QPushButton("Stop Run")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self._start_from_pending)
        self.stop_button.clicked.connect(self.stop_run)
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addStretch()

        self.metadata_block = QLabel()
        self.metadata_block.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.metadata_block.setStyleSheet("border: 1px solid #1a1a22; padding: 8px;")

        self.hot_files_list = QTreeWidget()
        self.hot_files_list.setHeaderLabels(["#", "File", "Score", "Raw ms", "Calls"])
        self.hot_files_list.setRootIsDecorated(False)
        self.hot_files_list.setAlternatingRowColors(True)
        self.hot_files_list.itemActivated.connect(self._open_selected_hot_file)
        self.hot_files_list.itemDoubleClicked.connect(self._open_selected_hot_file)

        self.cpu_memory_block = QLabel("CPU: -\nRSS: -")
        self.cpu_memory_block.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.cpu_memory_block.setStyleSheet("border: 1px solid #1a1a22; padding: 8px;")

        self.event_log = QPlainTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.setMaximumBlockCount(200)

        self.timeline_block = QPlainTextEdit()
        self.timeline_block.setReadOnly(True)
        self.timeline_block.setMaximumBlockCount(200)

        self.summary_block = QPlainTextEdit()
        self.summary_block.setReadOnly(True)
        self.summary_block.setMaximumBlockCount(300)
        self.summary_block.setPlainText("No completed run.")

        self.regressions_list = QTreeWidget()
        self.regressions_list.setHeaderLabels(["File", "Delta"])
        self.regressions_list.setRootIsDecorated(False)
        self.regressions_list.setAlternatingRowColors(True)
        self.regressions_list.itemActivated.connect(self._open_selected_regression)
        self.regressions_list.itemDoubleClicked.connect(self._open_selected_regression)

        self.run_quality_block = QLabel("Run quality warnings will appear after summary data is available.")
        self.run_quality_block.setWordWrap(True)
        self.run_quality_block.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.run_quality_block.setStyleSheet("border: 1px solid #1a1a22; padding: 8px;")

        self.debug_toggle = QToolButton()
        self.debug_toggle.setText("Debug Details")
        self.debug_toggle.setCheckable(True)
        self.debug_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.debug_toggle.clicked.connect(self._toggle_debug_drawer)

        self.debug_details = QPlainTextEdit()
        self.debug_details.setReadOnly(True)
        self.debug_details.setVisible(False)
        self.debug_details.setMaximumBlockCount(500)

        self.hot_files_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.event_log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.timeline_block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.summary_block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.debug_details.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.hot_files_list.setColumnWidth(0, 34)
        self.hot_files_list.setColumnWidth(1, 220)
        self.regressions_list.setColumnWidth(0, 280)

        self.metadata_label = QLabel("Run Metadata")
        self.hot_files_label = QLabel("Hot Files")
        self.cpu_memory_label = QLabel("CPU / Memory")
        self.event_log_label = QLabel("Event Log")
        self.timeline_label = QLabel("Timeline")
        self.summary_label = QLabel("Summary")
        self.regressions_label = QLabel("Top Regressions")
        self.run_quality_label = QLabel("Run Quality")

        for label in [
            self.metadata_label,
            self.hot_files_label,
            self.cpu_memory_label,
            self.event_log_label,
            self.timeline_label,
            self.summary_label,
            self.regressions_label,
            self.run_quality_label,
        ]:
            label.setStyleSheet("font-size: 12px; font-weight: 700; color: #d8d8df; letter-spacing: 0.04em; text-transform: uppercase;")

        layout.addWidget(controls)
        layout.addWidget(self.metadata_label)
        layout.addWidget(self.metadata_block)
        layout.addWidget(self.hot_files_label)
        layout.addWidget(self.hot_files_list)
        layout.addWidget(self.cpu_memory_label)
        layout.addWidget(self.cpu_memory_block)
        layout.addWidget(self.event_log_label)
        layout.addWidget(self.event_log)
        layout.addWidget(self.timeline_label)
        layout.addWidget(self.timeline_block)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_block)
        layout.addWidget(self.regressions_label)
        layout.addWidget(self.regressions_list)
        layout.addWidget(self.run_quality_label)
        layout.addWidget(self.run_quality_block)
        layout.addWidget(self.debug_toggle)
        layout.addWidget(self.debug_details)
        self._pending_spec: dict[str, object] | None = None
        self._apply_visual_state("idle", "idle")

    def set_pending_spec(self, spec: dict[str, object], *, editable: bool = True) -> None:
        self._pending_spec = dict(spec)
        running = self.process.state() != QProcess.ProcessState.NotRunning
        self.start_button.setEnabled(editable and not running)
        self.stop_button.setEnabled(running)
        if not running:
            self.metadata_block.setText(self._pending_metadata_text(spec))
            self._apply_visual_state("idle", "idle")

    def _start_from_pending(self) -> None:
        if self._pending_spec is None:
            return
        self.start_run_from_spec(self._pending_spec)

    def start_run_from_spec(self, spec: dict[str, object]) -> bool:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return False
        scenario = spec.get("scenario", {})
        run_section = spec.get("run", {})
        hardware = spec.get("hardware", {})
        if not isinstance(scenario, dict) or not isinstance(run_section, dict) or not isinstance(hardware, dict):
            return False
        script_path_text = str(scenario.get("script_path") or "").strip()
        module_name = str(scenario.get("module_name") or "").strip()
        script_path = Path(script_path_text).expanduser() if script_path_text else Path()
        if script_path_text and not script_path.is_absolute():
            script_path = (PROJECT_ROOT / script_path).resolve()
        parsed_args = [str(item) for item in scenario.get("args", [])] if isinstance(scenario.get("args"), list) else []
        if script_path_text and not script_path.is_file():
            return False
        if not script_path_text and not module_name:
            return False
        default_target_name = script_path.stem if script_path_text else module_name.rsplit(".", 1)[-1]
        run_name = str(run_section.get("name") or f"{default_target_name}_{datetime.now().strftime('%H%M%S')}")
        self.current_run_name = run_name
        self.current_run_id = f"{default_target_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.current_script_path = script_path.as_posix() if script_path_text else f"<module:{module_name}>"
        self.current_args = parsed_args
        self.current_started_at = datetime.now().isoformat()
        self.current_project_root = self._resolve_project_root(spec, script_path)
        interpreter_path = str(run_section.get("interpreter_path") or "").strip()
        executable = sys.executable
        if interpreter_path:
            resolved_interpreter = Path(interpreter_path).expanduser()
            if not resolved_interpreter.is_absolute():
                resolved_interpreter = (self.current_project_root / resolved_interpreter).resolve()
            if not resolved_interpreter.is_file():
                return False
            executable = str(resolved_interpreter)
        self.current_interpreter_path = executable
        self.process.setWorkingDirectory(str(self.current_project_root))
        process_environment = QProcessEnvironment.systemEnvironment()
        pythonpath_entries = [str(PROJECT_ROOT), str(self.current_project_root)]
        existing_pythonpath = process_environment.value("PYTHONPATH", "")
        if existing_pythonpath:
            pythonpath_entries.append(existing_pythonpath)
        process_environment.insert("PYTHONPATH", os.pathsep.join(pythonpath_entries))
        self.process.setProcessEnvironment(process_environment)
        self.event_log.clear()
        self.timeline_block.clear()
        self.summary_block.setPlainText("Summary pending aggregation.")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._apply_visual_state("running", "running")
        process_args = [
            "-m",
            "backend.instrumentation.script_runner",
            "--database",
            str(INSTRUMENTATION_DB_PATH),
            "--project-root",
            str(self.current_project_root),
            "--run-name",
            run_name,
            "--scenario-kind",
            str(scenario.get("kind") or "custom_script"),
            "--hardware-profile",
            str(hardware.get("profile") or f"{sys.platform}:{platform_string()}"),
            "--",
            *parsed_args,
        ]
        if module_name:
            process_args[8:8] = ["--module-name", module_name]
        else:
            process_args[8:8] = ["--script-path", str(script_path)]
        self.process.start(executable, process_args)
        if not self.process.waitForStarted(3000):
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return False
        self.current_run_id = self.storage.fetch_latest_run_id_by_name(run_name) or self.current_run_id
        self.refresh_timer.start()
        return True

    def stop_run(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.stop_button.setEnabled(False)
        self.process.terminate()
        if self.stop_timer is not None:
            self.stop_timer.stop()
        self.stop_timer = QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self._force_kill_process)
        self.stop_timer.start(3000)

    def load_summary_artifact(self, artifact: dict[str, object]) -> None:
        summary = artifact.get("summary", {})
        spec = artifact.get("spec", {})
        self._pending_spec = spec if isinstance(spec, dict) else None
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        if isinstance(spec, dict):
            self.metadata_block.setText(self._pending_metadata_text(spec))
        else:
            self.metadata_block.setText("No editable run spec loaded.")
        self._apply_summary_data(summary if isinstance(summary, dict) else {})
        debug = artifact.get("debug", {})
        self.debug_details.setPlainText(json.dumps(debug, indent=2) if debug else "No debug data.")

    def refresh_state(self) -> None:
        if not self.current_run_id:
            return
        live_state = self.storage.fetch_live_run_state(self.current_run_id)
        if live_state is None and self.current_run_name:
            resolved = self.storage.fetch_latest_run_id_by_name(self.current_run_name)
            if resolved:
                self.current_run_id = resolved
                live_state = self.storage.fetch_live_run_state(self.current_run_id)
        if live_state is None:
            return
        parsed_args = json.loads(str(live_state["parsed_args_json"]))
        elapsed_seconds = float(live_state["elapsed_seconds"])
        self.metadata_block.setText(
            "\n".join(
                [
                    f"Run Name: {self.current_run_name or self.current_run_id}",
                    f"Script: {live_state['script_path']}",
                    f"Interpreter: {self.current_interpreter_path}",
                    f"Args: {' '.join(parsed_args) if parsed_args else '(none)'}",
                    f"Started: {live_state['started_at']}",
                    f"Elapsed: {self._format_elapsed(elapsed_seconds)}",
                    f"Status: {live_state['status']}",
                ]
            )
        )
        self.cpu_memory_block.setText(
            f"CPU: {float(live_state['cpu_percent']):.1f}%\nRSS: {float(live_state['rss_mb']):.1f} MB"
        )
        rows = self.storage.fetch_live_file_rows(self.current_run_id)
        self.hot_files_list.clear()
        for index, row in enumerate(sorted(rows, key=lambda item: (-float(item["rolling_score"]), -float(item["raw_ms"])))[:10], start=1):
            item = QTreeWidgetItem(
                [
                    str(index),
                    Path(str(row["file_path"])).name,
                    f"{float(row['rolling_score']):.1f}",
                    f"{float(row['raw_ms']):.1f}",
                    f"{int(row['call_count'])}",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, str(row["file_path"]))
            self.hot_files_list.addTopLevelItem(item)
        self.event_log.setPlainText("\n".join(filter(None, [str(live_state["stdout_tail"]), str(live_state["stderr_tail"])])))
        self.timeline_block.setPlainText(
            "\n".join(
                [
                    f"elapsed={self._format_elapsed(elapsed_seconds)}",
                    f"status={live_state['status']}",
                    f"aggregation={live_state['aggregation_status']}",
                    f"performance_report={self._performance_report_path()}",
                ]
            )
        )
        self._populate_summary_from_storage()
        self.debug_details.setPlainText(
            "\n".join(
                [
                    f"Aggregation Status: {live_state['aggregation_status']}",
                    f"Raw Function Row Count: {int(live_state['raw_function_row_count'])}",
                    f"Sampler Sample Count: {int(live_state['sampler_sample_count'])}",
                    *self._performance_report_debug_lines(),
                    "External Buckets:",
                    *[
                        f"- {row['bucket_name']}: {float(row['total_time_ms']):.1f} ms / {int(row['call_count'])} calls"
                        for row in json.loads(str(live_state["external_buckets_json"]))
                    ],
                ]
            )
        )
        self._apply_visual_state(str(live_state["status"]), str(live_state["aggregation_status"]))

    def _populate_summary_from_storage(self) -> None:
        if not self.current_run_id:
            return
        run_summary = self.storage.fetch_run_summary(self.current_run_id)
        file_summaries = self.storage.fetch_file_summaries(self.current_run_id, limit=10)
        if run_summary is None:
            self.summary_block.setPlainText("Summary pending aggregation.")
            return
        summary_data = {
            "hottest_files": json.loads(str(run_summary["hottest_files_json"])),
            "biggest_score_deltas": json.loads(str(run_summary["biggest_score_deltas_json"])),
            "failure_count": int(run_summary["failure_count"]),
            "file_summaries": [dict(row) for row in file_summaries],
        }
        self._apply_summary_data(summary_data)

    def _apply_summary_data(self, summary_data: dict[str, object]) -> None:
        hottest = summary_data.get("hottest_files", [])
        deltas = summary_data.get("biggest_score_deltas", [])
        file_summaries = summary_data.get("file_summaries", [])
        failure_count = int(summary_data.get("failure_count", 0))
        self.regressions_list.clear()
        lines = ["Hottest Files"]
        for row in hottest if isinstance(hottest, list) else []:
            lines.append(f"- {row.get('file_path', '-')}: {float(row.get('rolling_score', 0.0)):.1f}")
        lines.append("")
        lines.append("Biggest Deltas")
        for row in deltas if isinstance(deltas, list) else []:
            lines.append(f"- {row.get('file_path', '-')}: {float(row.get('score_delta', 0.0)):+.1f}")
            item = QTreeWidgetItem(
                [
                    str(row.get("file_path", "-")),
                    f"{float(row.get('score_delta', 0.0)):+.1f}",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, str(row.get("file_path", "")))
            self.regressions_list.addTopLevelItem(item)
        if isinstance(file_summaries, list) and file_summaries:
            lines.append("")
            lines.append("File Summaries")
            for row in file_summaries:
                lines.append(
                    f"- {row.get('file_path', '-')}: score {float(row.get('normalized_compute_score', 0.0)):.1f}"
                )
        performance_report = self._load_performance_report()
        if performance_report is not None:
            lines.append("")
            lines.append("Performance Report")
            quality = str(performance_report.get("run_quality", "unrated"))
            lines.append(f"- run quality: {quality}")
            lines.append(f"- trace events: {int(performance_report.get('trace_events', 0))}")
            lines.append(f"- functions seen: {int(performance_report.get('functions_seen', 0))}")
            lines.append(f"- files seen: {int(performance_report.get('files_seen', 0))}")
            lines.append(f"- instrumented runtime: {float(performance_report.get('instrumented_runtime_ms', 0.0)):.1f} ms")
            lines.append(f"- trace overhead est: {float(performance_report.get('trace_overhead_estimate_ms', 0.0)):.1f} ms")
            lines.append(f"- sqlite writes: {float(performance_report.get('sqlite_write_time_ms', 0.0)):.1f} ms")
            lines.append(f"- aggregation: {float(performance_report.get('aggregation_time_ms', 0.0)):.1f} ms")
            stage_timings = performance_report.get("stage_timings_ms")
            if isinstance(stage_timings, dict) and stage_timings:
                lines.append("- stage timings:")
                for stage_name, stage_ms in sorted(stage_timings.items()):
                    lines.append(f"  - {stage_name}: {float(stage_ms):.1f} ms")
        lines.append("")
        lines.append(f"Failures: {failure_count}")
        self.summary_block.setPlainText("\n".join(lines))
        self.run_quality_block.setText("\n".join(self._run_quality_lines(summary_data, performance_report)))

    def _pending_metadata_text(self, spec: dict[str, object]) -> str:
        run_section = spec.get("run", {})
        scenario = spec.get("scenario", {})
        if not isinstance(run_section, dict) or not isinstance(scenario, dict):
            return "No spec loaded."
        return "\n".join(
                [
                    f"Run Name: {run_section.get('name', '-')}",
                    f"Target: {scenario.get('module_name') or scenario.get('script_path', '-')}",
                    f"Interpreter: {run_section.get('interpreter_path') or sys.executable}",
                    f"Args: {' '.join(str(item) for item in scenario.get('args', [])) if isinstance(scenario.get('args'), list) else '(none)'}",
                    "Started: -",
                "Elapsed: 00:00:00",
                "Status: idle",
            ]
        )

    def _toggle_debug_drawer(self) -> None:
        expanded = self.debug_toggle.isChecked()
        self.debug_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.debug_details.setVisible(expanded)

    def _drain_process_output(self) -> None:
        _ = bytes(self.process.readAllStandardOutput())
        _ = bytes(self.process.readAllStandardError())

    def _handle_process_finished(self, _exit_code: int, _exit_status) -> None:
        self.refresh_timer.stop()
        if self.stop_timer is not None:
            self.stop_timer.stop()
        self.start_button.setEnabled(self._pending_spec is not None)
        self.stop_button.setEnabled(False)
        self.refresh_state()
        self._apply_visual_state("completed", "complete")

    def _force_kill_process(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def shutdown(self) -> None:
        self.refresh_timer.stop()
        if self.stop_timer is not None:
            self.stop_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)

    def _format_elapsed(self, elapsed_seconds: float) -> str:
        total_seconds = max(int(elapsed_seconds), 0)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _resolve_project_root(self, spec: dict[str, object], script_path: Path) -> Path:
        run_section = spec.get("run", {})
        project_root = PROJECT_ROOT
        if isinstance(run_section, dict) and isinstance(run_section.get("project_root"), str) and str(run_section["project_root"]).strip():
            candidate = Path(str(run_section["project_root"])).expanduser()
            if candidate.exists():
                project_root = candidate.resolve()
        elif script_path:
            project_root = script_path.parent
        return project_root

    def _performance_report_path(self) -> str:
        return str((self.current_project_root / "bb_performance_report.json").resolve())

    def _load_performance_report(self) -> dict[str, object] | None:
        report_path = Path(self._performance_report_path())
        if not report_path.is_file():
            return None
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _performance_report_debug_lines(self) -> list[str]:
        report = self._load_performance_report()
        if report is None:
            return [f"Performance Report: missing at {self._performance_report_path()}"]
        return [
            f"Performance Report: {self._performance_report_path()}",
            f"Run Quality: {report.get('run_quality', 'unrated')}",
            f"Trace Events: {int(report.get('trace_events', 0))}",
            f"Functions Seen: {int(report.get('functions_seen', 0))}",
            f"Files Seen: {int(report.get('files_seen', 0))}",
            f"Instrumented Runtime: {float(report.get('instrumented_runtime_ms', 0.0)):.1f} ms",
            f"Trace Overhead Estimate: {float(report.get('trace_overhead_estimate_ms', 0.0)):.1f} ms",
            f"SQLite Write Time: {float(report.get('sqlite_write_time_ms', 0.0)):.1f} ms",
            f"Aggregation Time: {float(report.get('aggregation_time_ms', 0.0)):.1f} ms",
            f"Live Flush Time: {float(report.get('live_state_flush_time_ms', 0.0)):.1f} ms",
            *self._stage_timing_debug_lines(report),
        ]

    def _open_selected_hot_file(self, item: QTreeWidgetItem) -> None:
        file_path = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
        if file_path:
            self.fileRequested.emit({"file_path": file_path, "preferred_tab": "Compute"})

    def _open_selected_regression(self, item: QTreeWidgetItem) -> None:
        file_path = str(item.data(0, Qt.ItemDataRole.UserRole) or "").strip()
        if file_path:
            self.fileRequested.emit({"file_path": file_path, "preferred_tab": "Compute"})

    def _run_quality_lines(
        self,
        summary_data: dict[str, object],
        performance_report: dict[str, object] | None,
    ) -> list[str]:
        lines: list[str] = []
        failure_count = int(summary_data.get("failure_count", 0))
        if failure_count > 0:
            lines.append(f"Failure warning: {failure_count} failures recorded in this run.")
        deltas = summary_data.get("biggest_score_deltas", [])
        if not isinstance(deltas, list) or not deltas:
            lines.append("Comparison note: no previous comparable run or no meaningful deltas.")
        if performance_report is None:
            lines.append("Instrumentation warning: performance report missing.")
            return lines or ["No quality warnings."]
        files_seen = int(performance_report.get("files_seen", 0))
        if files_seen <= 3:
            lines.append(f"Coverage warning: only {files_seen} files were measured.")
        functions_seen = int(performance_report.get("functions_seen", 0))
        if functions_seen <= 5:
            lines.append(f"Coverage warning: only {functions_seen} functions were measured.")
        instrumented_runtime_ms = float(performance_report.get("instrumented_runtime_ms", 0.0))
        trace_overhead_ms = float(performance_report.get("trace_overhead_estimate_ms", 0.0))
        if instrumented_runtime_ms > 0.0 and trace_overhead_ms / instrumented_runtime_ms >= 0.5:
            lines.append("Instrumentation warning: tracer overhead is at least 50% of measured runtime.")
        external_share = self._dominant_external_share(summary_data)
        if external_share >= 0.7:
            lines.append(f"Trust warning: external pressure dominates runtime share ({external_share:.0%}).")
        quality = str(performance_report.get("run_quality", "unrated"))
        if quality in {"weak", "diagnostic_only"}:
            lines.append(f"Overall quality: {quality.replace('_', ' ')}.")
        if not lines:
            lines.append("No obvious quality warnings for this run.")
        return lines

    def _stage_timing_debug_lines(self, report: dict[str, object]) -> list[str]:
        stage_timings = report.get("stage_timings_ms")
        if not isinstance(stage_timings, dict) or not stage_timings:
            return ["Stage Timings: none"]
        return [f"Stage {name}: {float(value):.1f} ms" for name, value in sorted(stage_timings.items())]

    def _dominant_external_share(self, summary_data: dict[str, object]) -> float:
        file_summaries = summary_data.get("file_summaries")
        if not isinstance(file_summaries, list) or not file_summaries:
            return 0.0
        top_summary = file_summaries[0]
        if not isinstance(top_summary, dict):
            return 0.0
        try:
            external_summary = json.loads(str(top_summary.get("external_pressure_summary") or "{}"))
        except json.JSONDecodeError:
            return 0.0
        return float(external_summary.get("runtime_share") or 0.0)

    def _apply_visual_state(self, status: str, aggregation_status: str) -> None:
        idle = status == "idle"
        running = status == "running"
        completed = status in {"completed", "stopped"} and aggregation_status == "complete"

        self.metadata_block.setStyleSheet(
            "border: 1px solid #1a1a22; padding: 8px; background-color: #111116; color: #d8d8df;"
            if idle
            else "border: 1px solid #6a8fb3; padding: 8px; background-color: #0f1520; color: #e6edf7;"
            if running
            else "border: 1px solid #758b54; padding: 8px; background-color: #10160f; color: #e5edd8;"
            if completed
            else "border: 1px solid #5b3a3a; padding: 8px; background-color: #1a1010; color: #f0d8d8;"
        )
        self.summary_block.setStyleSheet(
            "border: 1px solid #1a1a22; background-color: #0e0d12; color: #cdbfae;"
            if not completed
            else "border: 1px solid #758b54; background-color: #10160f; color: #e7eddc;"
        )
        self.event_log.setStyleSheet(
            "border: 1px solid #1a1a22; background-color: #0d0c11; color: #c4b7a5;"
            if not completed
            else "border: 1px solid #15151b; background-color: #09090c; color: #8f887e;"
        )
        self.timeline_block.setStyleSheet(
            "border: 1px solid #1a1a22; background-color: #0d0c11; color: #c4b7a5;"
        )
        self.hot_files_list.setStyleSheet(
            "QTreeWidget { border: 1px solid #1a1a22; background-color: #0d0c11; color: #d8d8df; alternate-background-color: #121118; }"
            "QHeaderView::section { background-color: #17141f; color: #d8d8df; border: 0; padding: 4px 6px; font-weight: 700; }"
        )
        self.regressions_list.setStyleSheet(
            "QTreeWidget { border: 1px solid #1a1a22; background-color: #0d0c11; color: #d8d8df; alternate-background-color: #121118; }"
            "QHeaderView::section { background-color: #17141f; color: #d8d8df; border: 0; padding: 4px 6px; font-weight: 700; }"
        )
        self.summary_label.setText("Summary" if not completed else "Summary · Complete")
        self.run_quality_block.setStyleSheet(
            "border: 1px solid #1a1a22; padding: 8px; background-color: #111116; color: #cdbfae;"
            if not completed
            else "border: 1px solid #6a8fb3; padding: 8px; background-color: #0f1520; color: #e6edf7;"
        )


class StressEngineWindow(QWidget):
    closed = Signal()

    def __init__(self, project_root_provider, open_file_inspector=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_root_provider = project_root_provider
        self.open_file_inspector = open_file_inspector
        self.storage = InstrumentationStorage(INSTRUMENTATION_DB_PATH)
        self.storage.initialize_schema()
        self.setWindowTitle("Stress Engine")
        self.read_only_summary_mode = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(6)
        self.open_button = QPushButton("Open .bbtest")
        self.save_button = QPushButton("Save .bbtest")
        self.editor_toggle = QToolButton()
        self.editor_toggle.setText("Hide Editors")
        self.editor_toggle.setCheckable(True)
        self.editor_toggle.setChecked(True)
        self.editor_toggle.clicked.connect(self._toggle_editors)
        self.open_button.clicked.connect(self._open_artifact)
        self.save_button.clicked.connect(self._save_artifact)
        self.profile_preset = QComboBox()
        self.profile_preset.addItem(verification_profile_label("smoke"), "smoke")
        self.profile_preset.addItem(verification_profile_label("real"), "real")
        self.profile_preset.addItem(verification_profile_label("diagnostic"), "diagnostic")
        self.profile_preset.currentIndexChanged.connect(self._update_profile_note)
        self.apply_profile_button = QPushButton("Apply Profile")
        self.apply_profile_button.clicked.connect(self._apply_profile_preset)
        top_bar_layout.addWidget(self.open_button)
        top_bar_layout.addWidget(self.save_button)
        top_bar_layout.addWidget(self.profile_preset)
        top_bar_layout.addWidget(self.apply_profile_button)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.editor_toggle)

        self.run_context_strip = QLabel("Run Context: no spec loaded")
        self.run_context_strip.setWordWrap(True)
        self.run_context_strip.setStyleSheet(
            "padding: 8px 10px; border: 1px solid #1a1a22; background-color: #111116; color: #cdbfae;"
        )
        self.profile_note = QLabel()
        self.profile_note.setWordWrap(True)
        self.profile_note.setStyleSheet(
            "padding: 8px 10px; border: 1px solid #1a1a22; background-color: #111116; color: #b6ab9c;"
        )

        self.section_list = QListWidget()
        self.section_list.setFixedWidth(180)
        self.section_list.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.editor_stack = QStackedWidget()
        self.editor_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.section_guidance = QLabel()
        self.section_guidance.setWordWrap(True)
        self.section_guidance.setStyleSheet(
            "padding: 8px 10px; border: 1px solid #1a1a22; background-color: #111116; color: #b6ab9c;"
        )
        self.section_editors: dict[str, QPlainTextEdit] = {}
        for section_name in ["Run", "Hardware", "Scenario", "Dashboard", "Save / Export"]:
            self.section_list.addItem(QListWidgetItem(section_name))
            editor = QPlainTextEdit()
            editor.textChanged.connect(self._validate_spec)
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.section_editors[section_name] = editor
            self.editor_stack.addWidget(editor)
        self.section_list.currentRowChanged.connect(self.editor_stack.setCurrentIndex)
        self.section_list.currentRowChanged.connect(self._update_section_guidance)
        self.section_list.setCurrentRow(0)

        editor_area = QWidget()
        editor_area_layout = QVBoxLayout(editor_area)
        editor_area_layout.setContentsMargins(0, 0, 0, 0)
        editor_area_layout.setSpacing(8)
        editor_body = QWidget()
        editor_body_layout = QHBoxLayout(editor_body)
        editor_body_layout.setContentsMargins(0, 0, 0, 0)
        editor_body_layout.setSpacing(8)
        editor_body_layout.addWidget(self.section_list)
        editor_body_layout.addWidget(self.editor_stack, 1)
        editor_area_layout.addWidget(self.section_guidance)
        editor_area_layout.addWidget(editor_body, 1)

        self.validation_panel = QPlainTextEdit()
        self.validation_panel.setReadOnly(True)
        self.validation_panel.setMaximumHeight(120)
        self.validation_panel.setPlainText("No validation errors.")
        self.validation_label = QLabel("Validation")
        self.validation_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #d8d8df; letter-spacing: 0.04em; text-transform: uppercase;")

        self.output_stack = RunOutputStack(self.storage)
        self.output_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if self.open_file_inspector is not None:
            self.output_stack.fileRequested.connect(self.open_file_inspector)

        self.editor_container = QWidget()
        editor_container_layout = QVBoxLayout(self.editor_container)
        editor_container_layout.setContentsMargins(0, 0, 0, 0)
        editor_container_layout.setSpacing(8)
        editor_container_layout.addWidget(editor_area, 1)
        editor_container_layout.addWidget(self.validation_label)
        editor_container_layout.addWidget(self.validation_panel)

        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setWidget(self.editor_container)

        output_scroll = QScrollArea()
        output_scroll.setWidgetResizable(True)
        output_scroll.setFrameShape(QFrame.Shape.NoFrame)
        output_scroll.setWidget(self.output_stack)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(editor_scroll)
        splitter.addWidget(output_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([300, 420])

        layout.addWidget(top_bar)
        layout.addWidget(self.profile_note)
        layout.addWidget(self.run_context_strip)
        layout.addWidget(splitter, 1)

        self._load_default_sections("smoke")
        self._update_profile_note()
        self._update_section_guidance(self.section_list.currentRow())
        self._validate_spec()
        self._apply_initial_geometry()

    def _load_default_sections(self, profile: str = "smoke") -> None:
        for section_name, text in default_section_texts(profile).items():
            self.section_editors[section_name].setPlainText(text)

    def _apply_profile_preset(self) -> None:
        profile = str(self.profile_preset.currentData() or "smoke")
        project_root = self._current_project_root()
        spec = verification_profile_spec(profile)
        run_section = dict(spec.get("run") or {})
        scenario = dict(spec.get("scenario") or {})
        if project_root:
            run_section["project_root"] = str(project_root)
            if not str(run_section.get("interpreter_path") or "").strip():
                candidate = project_root / ".venv" / "bin" / "python"
                run_section["interpreter_path"] = str(candidate) if candidate.is_file() else ""
            args = scenario.get("args")
            if isinstance(args, list):
                scenario["args"] = [str(project_root) if item == "" else item for item in args]
        merged = {
            "run": run_section,
            "hardware": spec.get("hardware") or {},
            "scenario": scenario,
            "dashboard": spec.get("dashboard") or {},
            "save_export": spec.get("save_export") or {},
        }
        self._load_spec_into_editors(merged)
        self._validate_spec()

    def _update_profile_note(self) -> None:
        profile = str(self.profile_preset.currentData() or "smoke")
        self.profile_note.setText(f"Verification Profile: {verification_profile_note(profile)}")

    def _current_project_root(self) -> Path | None:
        candidate = self.project_root_provider()
        return candidate.resolve() if isinstance(candidate, Path) else None

    def _toggle_editors(self) -> None:
        visible = self.editor_toggle.isChecked()
        self.editor_toggle.setText("Hide Editors" if visible else "Show Editors")
        self.editor_container.setVisible(visible)

    def _update_section_guidance(self, row: int) -> None:
        if row < 0 or row >= self.section_list.count():
            self.section_guidance.setText("Select a section to edit its part of the run spec.")
            return
        section_name = self.section_list.item(row).text().replace(" *", "")
        self.section_guidance.setText(SECTION_GUIDANCE.get(section_name, "Edit this section of the run spec."))

    def _collect_section_data(self) -> tuple[dict[str, object], list[str]]:
        errors: list[str] = []
        merged: dict[str, object] = {}
        section_keys = {
            "Run": "run",
            "Hardware": "hardware",
            "Scenario": "scenario",
            "Dashboard": "dashboard",
            "Save / Export": "save_export",
        }
        for section_name, key in section_keys.items():
            editor = self.section_editors[section_name]
            try:
                merged[key] = parse_yaml_subset(editor.toPlainText(), section_name=section_name)
                self._set_section_error_state(section_name, False)
            except Exception as exc:
                errors.append(f"{section_name}: {exc}")
                self._set_section_error_state(section_name, True)
        return merged, errors

    def _validate_spec(self) -> None:
        spec, errors = self._collect_section_data()
        self._update_run_context_strip(self._merged_canonical_spec(spec) if not errors else spec)
        errors.extend(self._canonical_validation_errors(spec))
        if errors:
            self._apply_validation_state(errors)
            self.output_stack.set_pending_spec(spec, editable=False)
            self.output_stack.start_button.setEnabled(False)
            return
        self._apply_validation_state([])
        self.output_stack.set_pending_spec(self._merged_canonical_spec(spec), editable=not self.read_only_summary_mode)

    def _canonical_validation_errors(self, section_data: dict[str, object]) -> list[str]:
        errors: list[str] = []
        run_section = section_data.get("run", {})
        hardware = section_data.get("hardware", {})
        scenario = section_data.get("scenario", {})
        dashboard = section_data.get("dashboard", {})
        if not isinstance(run_section, dict) or not str(run_section.get("name") or "").strip():
            errors.append("Run: name is required.")
        if isinstance(run_section, dict):
            interpreter_path = str(run_section.get("interpreter_path") or "").strip()
            if interpreter_path:
                candidate = Path(interpreter_path).expanduser()
                if not candidate.is_absolute():
                    project_root = str(run_section.get("project_root") or "").strip()
                    base = Path(project_root).expanduser() if project_root else PROJECT_ROOT
                    candidate = (base / candidate).resolve()
                if not candidate.is_file():
                    errors.append("Run: interpreter_path must point to an existing Python executable.")
        if not isinstance(hardware, dict):
            errors.append("Hardware: section must be a mapping.")
        else:
            profile = str(hardware.get("profile") or "")
            if profile not in BUILTIN_HARDWARE_PROFILES:
                errors.append("Hardware: profile must be one of the built-in profiles.")
        if not isinstance(scenario, dict):
            errors.append("Scenario: section must be a mapping.")
        else:
            kind = str(scenario.get("kind") or "")
            if kind not in SCENARIO_DEFAULTS:
                errors.append("Scenario: kind must be api_stress, file_processing, compute_heavy, or custom_script.")
            if kind == "custom_script":
                script_path = str(scenario.get("script_path") or "")
                module_name = str(scenario.get("module_name") or "").strip()
                if not script_path and not module_name:
                    errors.append("Scenario: custom_script requires script_path or module_name.")
        if not isinstance(dashboard, dict) or not isinstance(dashboard.get("priority"), list) or not dashboard.get("priority"):
            errors.append("Dashboard: priority must be a non-empty list.")
        return errors

    def _merged_canonical_spec(self, section_data: dict[str, object]) -> dict[str, object]:
        run_section = dict(section_data.get("run", {})) if isinstance(section_data.get("run"), dict) else {}
        hardware = dict(section_data.get("hardware", {})) if isinstance(section_data.get("hardware"), dict) else {}
        scenario = dict(section_data.get("scenario", {})) if isinstance(section_data.get("scenario"), dict) else {}
        dashboard = dict(section_data.get("dashboard", {})) if isinstance(section_data.get("dashboard"), dict) else {}
        save_export = dict(section_data.get("save_export", {})) if isinstance(section_data.get("save_export"), dict) else {}
        profile_name = str(hardware.get("profile") or "mini_pc_n100_16gb")
        merged_hardware = {
            "profile": profile_name,
            "profile_data": BUILTIN_HARDWARE_PROFILES.get(profile_name, {}),
            "overrides": hardware.get("overrides", {}) if isinstance(hardware.get("overrides"), dict) else {},
        }
        scenario_kind = str(scenario.get("kind") or "compute_heavy")
        defaults = SCENARIO_DEFAULTS.get(scenario_kind, {})
        script_path = str(scenario.get("script_path") or defaults.get("script_path") or "")
        module_name = str(scenario.get("module_name") or defaults.get("module_name") or "")
        args_value = scenario.get("args")
        if isinstance(args_value, str):
            scenario_args = shlex.split(args_value)
        elif isinstance(args_value, list):
            scenario_args = [str(item) for item in args_value]
        else:
            scenario_args = [str(item) for item in defaults.get("args", [])]
        return {
            "run": {
                "name": str(run_section.get("name") or "").strip(),
                "project_root": str(run_section.get("project_root") or "").strip(),
                "interpreter_path": str(run_section.get("interpreter_path") or "").strip(),
            },
            "hardware": merged_hardware,
            "scenario": {
                "kind": scenario_kind,
                "script_path": script_path,
                "module_name": module_name,
                "args": scenario_args,
            },
            "dashboard": {
                "priority": [str(item) for item in dashboard.get("priority", [])] if isinstance(dashboard.get("priority"), list) else [],
            },
            "save_export": save_export,
        }

    def _set_section_error_state(self, section_name: str, has_error: bool) -> None:
        matches = self.section_list.findItems(section_name, Qt.MatchFlag.MatchExactly)
        if not matches:
            return
        item = matches[0]
        item.setText(f"{section_name} *" if has_error else section_name)

    def _save_artifact(self) -> None:
        spec, errors = self._collect_section_data()
        errors.extend(self._canonical_validation_errors(spec))
        if errors:
            QMessageBox.warning(self, "Invalid Spec", "\n".join(errors))
            return
        canonical = self._merged_canonical_spec(spec)
        suggested_name = "run.bbtest"
        save_export = canonical.get("save_export", {})
        if isinstance(save_export, dict):
            configured_path = str(save_export.get("artifact_path") or "").strip()
            if configured_path:
                suggested_name = configured_path
        suggested = str((PROJECT_ROOT / suggested_name).resolve())
        target_path, _selected_filter = QFileDialog.getSaveFileName(self, "Save .bbtest", suggested, "BlueBench Test (*.bbtest)")
        if not target_path:
            return
        artifact_path = Path(target_path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "format": "bbtest-1",
            "saved_at": datetime.now().isoformat(),
            "spec": canonical,
            "summary": self._current_summary_snapshot(),
            "debug": {"validation": self.validation_panel.toPlainText()},
        }
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    def _open_artifact(self) -> None:
        target_path, _selected_filter = QFileDialog.getOpenFileName(self, "Open .bbtest", str(PROJECT_ROOT), "BlueBench Test (*.bbtest)")
        if not target_path:
            return
        artifact = json.loads(Path(target_path).read_text(encoding="utf-8"))
        if not isinstance(artifact, dict):
            QMessageBox.warning(self, "Invalid Artifact", "The selected .bbtest file is invalid.")
            return
        chooser = QMessageBox(self)
        chooser.setWindowTitle("Open .bbtest")
        chooser.setText("Open as:")
        editable_button = chooser.addButton("Editable run spec", QMessageBox.ButtonRole.AcceptRole)
        summary_button = chooser.addButton("Read-only summary", QMessageBox.ButtonRole.ActionRole)
        chooser.addButton(QMessageBox.StandardButton.Cancel)
        chooser.exec()
        clicked = chooser.clickedButton()
        if clicked == editable_button:
            self._set_read_only_summary_mode(False)
            self._load_spec_into_editors(artifact.get("spec", {}))
            self._validate_spec()
            return
        if clicked == summary_button:
            self._set_read_only_summary_mode(True)
            self._load_spec_into_editors(artifact.get("spec", {}))
            self._validate_spec()
            self.output_stack.load_summary_artifact(artifact)
            return

    def _load_spec_into_editors(self, spec: object) -> None:
        if not isinstance(spec, dict):
            return
        section_map = {
            "Run": spec.get("run", {}),
            "Hardware": {
                "profile": spec.get("hardware", {}).get("profile") if isinstance(spec.get("hardware"), dict) else "",
                "overrides": spec.get("hardware", {}).get("overrides", {}) if isinstance(spec.get("hardware"), dict) else {},
            },
            "Scenario": spec.get("scenario", {}),
            "Dashboard": spec.get("dashboard", {}),
            "Save / Export": spec.get("save_export", {}),
        }
        for section_name, value in section_map.items():
            self.section_editors[section_name].setPlainText(dump_yaml_subset(value if isinstance(value, (dict, list)) else {}))

    def _current_summary_snapshot(self) -> dict[str, object]:
        run_id = self.output_stack.current_run_id
        if not run_id:
            return {
                "hottest_files": [],
                "biggest_score_deltas": [],
                "failure_count": 0,
            }
        run_summary = self.storage.fetch_run_summary(run_id)
        file_summaries = self.storage.fetch_file_summaries(run_id, limit=10)
        if run_summary is None:
            return {
                "hottest_files": [],
                "biggest_score_deltas": [],
                "failure_count": 0,
            }
        return {
            "hottest_files": json.loads(str(run_summary["hottest_files_json"])),
            "biggest_score_deltas": json.loads(str(run_summary["biggest_score_deltas_json"])),
            "failure_count": int(run_summary["failure_count"]),
            "file_summaries": [dict(row) for row in file_summaries],
        }

    def _set_read_only_summary_mode(self, enabled: bool) -> None:
        self.read_only_summary_mode = enabled
        for editor in self.section_editors.values():
            editor.setReadOnly(enabled)
        self.save_button.setEnabled(not enabled)

    def _update_run_context_strip(self, spec: dict[str, object]) -> None:
        run_section = spec.get("run", {})
        scenario = spec.get("scenario", {})
        if not isinstance(run_section, dict) or not isinstance(scenario, dict):
            self.run_context_strip.setText("Run Context: no spec loaded")
            return
        run_name = str(run_section.get("name") or "-")
        project_root = str(run_section.get("project_root") or "-")
        interpreter_path = str(run_section.get("interpreter_path") or sys.executable)
        script_path = str(scenario.get("script_path") or "-")
        self.run_context_strip.setText(
            "\n".join(
                [
                    f"{run_name} · {project_root}",
                    f"{interpreter_path}",
                    f"{script_path}",
                ]
            )
        )

    def _apply_validation_state(self, errors: list[str]) -> None:
        if errors:
            self.validation_label.setText(f"Validation ({len(errors)} errors)")
            self.validation_label.setStyleSheet(
                "font-size: 12px; font-weight: 700; color: #f0c3b8; letter-spacing: 0.04em; text-transform: uppercase;"
            )
            self.validation_panel.setStyleSheet(
                "border: 1px solid #9a4e3f; background-color: #1a1010; color: #f0d8d2;"
            )
            self.validation_panel.setPlainText("\n".join(errors))
            return

        self.validation_label.setText("Validation (ready)")
        self.validation_label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #d9f0ba; letter-spacing: 0.04em; text-transform: uppercase;"
        )
        self.validation_panel.setStyleSheet(
            "border: 1px solid #758b54; background-color: #10160f; color: #dbe8c7;"
        )
        self.validation_panel.setPlainText("No validation errors.")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.output_stack.shutdown()
        self.closed.emit()
        super().closeEvent(event)

    def _apply_initial_geometry(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 720)
            return
        available = screen.availableGeometry()
        width = min(1100, int(available.width() * 0.85))
        height = min(800, int(available.height() * 0.80))
        width = max(width, 820)
        height = max(height, 620)
        x = available.x() + max((available.width() - width) // 2, 0)
        y = available.y() + max((available.height() - height) // 2, 0)
        self.setGeometry(x, y, width, height)
