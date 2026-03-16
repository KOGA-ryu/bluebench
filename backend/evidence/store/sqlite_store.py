from __future__ import annotations

import json
from pathlib import Path

from backend.evidence.schemas.run_schema import build_run_evidence
from backend.instrumentation.storage import InstrumentationStorage


class SQLiteEvidenceStore:
    def __init__(self, storage: InstrumentationStorage) -> None:
        self.storage = storage

    def list_completed_runs(self, project_root: str | Path | None = None) -> list[dict[str, object]]:
        return [dict(row) for row in self.storage.list_completed_runs(project_root=project_root)]

    def load_previous_comparable_run(
        self,
        run_id: str,
        project_root: str | Path | None = None,
    ) -> dict[str, object] | None:
        run_row = self.storage.fetch_run(run_id)
        if run_row is None:
            return None
        previous_run_id = self.storage.fetch_previous_comparable_run_id(
            run_id,
            str(run_row["scenario_kind"]),
            str(run_row["hardware_profile"]),
            project_root or run_row["project_root"],
        )
        if not previous_run_id:
            return None
        return self.load_run_evidence(previous_run_id)

    def load_run_evidence(self, run_id: str) -> dict[str, object] | None:
        run_row = self.storage.fetch_run(run_id)
        if run_row is None:
            return None
        project_root = Path(str(run_row["project_root"] or "")).resolve() if run_row["project_root"] else None
        report = self._load_run_performance_report(project_root, str(run_row["run_id"])) if project_root else None
        if report is None and project_root:
            report = self._load_performance_report(project_root)
        if report and not self._report_matches_run(report, run_row):
            report = None
        if report and isinstance(report.get("top_files_by_raw_ms"), list):
            files = [
                {
                    "file_path": str(item.get("file_path") or ""),
                    "raw_ms": float(item.get("raw_ms") or 0.0),
                    "call_count": self._to_int(item.get("call_count")),
                    "rolling_score": self._to_float(item.get("rolling_score")),
                    "normalized_compute_score": None,
                }
                for item in report.get("top_files_by_raw_ms", [])
                if str(item.get("file_path") or "")
            ]
        else:
            files = [
                {
                    "file_path": str(row["file_path"]),
                    "raw_ms": float(row["total_time_ms"]),
                    "call_count": int(row["call_count"]),
                    "rolling_score": float(row["rolling_score"]),
                    "normalized_compute_score": float(row["normalized_compute_score"]),
                }
                for row in self.storage.fetch_file_summaries(run_id, limit=None)
            ]
        return build_run_evidence(
            run_id=str(run_row["run_id"]),
            run_name=str(run_row["run_name"]),
            timestamp=str(run_row["finished_at"] or run_row["started_at"] or ""),
            status=str(run_row["status"]),
            quality=str(report.get("run_quality") or "") if report else None,
            project_root=str(project_root or ""),
            scenario_kind=str(run_row["scenario_kind"]),
            hardware_profile=str(run_row["hardware_profile"]),
            runtime_ms=self._to_float(report.get("instrumented_runtime_ms")) if report else None,
            trace_overhead_ms=self._to_float(report.get("trace_overhead_estimate_ms")) if report else None,
            stages={
                str(key): float(value)
                for key, value in dict(report.get("stage_timings_ms") or {}).items()
                if self._to_float(value) is not None
            }
            if report
            else {},
            files=files,
        )

    @staticmethod
    def _to_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _load_run_performance_report(project_root: Path, run_id: str) -> dict[str, object] | None:
        report_path = project_root / ".bluebench" / "run_reports" / f"{run_id}.json"
        if not report_path.is_file():
            return None
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _load_performance_report(project_root: Path) -> dict[str, object] | None:
        report_path = project_root / "bb_performance_report.json"
        if not report_path.is_file():
            return None
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _report_matches_run(report: dict[str, object], run_row: dict[str, object]) -> bool:
        report_run_id = str(report.get("run_id") or "")
        if report_run_id and report_run_id == str(run_row["run_id"]):
            return True
        report_run_name = str(report.get("run_name") or "")
        return bool(report_run_name) and report_run_name == str(run_row["run_name"])
