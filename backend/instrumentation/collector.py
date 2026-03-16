from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from concurrent.futures import Future
from pathlib import Path
import threading
import time
from uuid import uuid4

from .aggregator import BackgroundAggregator
from .ranking import LiveRankingCalculator
from .sampler import ResourceSample, ResourceSampler
from .storage import InstrumentationStorage
from .tracer import ExternalBucketEvent, PythonTracer, SymbolEvent


@dataclass
class _FunctionAccumulator:
    symbol_key: str
    display_name: str
    file_path: str
    function_name: str
    self_time_ms: float = 0.0
    total_time_ms: float = 0.0
    call_count: int = 0
    recursive_call_count: int = 0
    max_recursion_depth: int = 0
    exception_count: int = 0
    last_exception_type: str | None = None


@dataclass
class _ExternalBucketAccumulator:
    bucket_name: str
    total_time_ms: float = 0.0
    call_count: int = 0


class RunMetricsCollector:
    def __init__(
        self,
        project_root: str | Path,
        storage: InstrumentationStorage,
        aggregator: BackgroundAggregator | None = None,
        *,
        run_name: str,
        scenario_kind: str,
        hardware_profile: str,
        sample_interval_seconds: float = 0.25,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.storage = storage
        self.aggregator = aggregator or BackgroundAggregator(storage)
        self.run_name = run_name
        self.scenario_kind = scenario_kind
        self.hardware_profile = hardware_profile
        self.sample_interval_seconds = sample_interval_seconds
        self.run_id = uuid4().hex
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.status = "created"
        self._lock = threading.Lock()
        self._functions: dict[str, _FunctionAccumulator] = {}
        self._external_buckets: dict[str, _ExternalBucketAccumulator] = {}
        self._resource_samples: list[ResourceSample] = []
        self._ranking = LiveRankingCalculator()
        self._sampler = ResourceSampler(self.record_resource_sample, interval_seconds=self.sample_interval_seconds)
        self._tracer = PythonTracer(self.project_root, self)
        self._trace_event_count = 0
        self._tracer_callback_time_ms = 0.0
        self._sqlite_write_time_ms = 0.0
        self._run_started_perf: float | None = None
        self._run_finished_perf: float | None = None

    def start(self) -> str:
        self.storage.initialize_schema()
        self.started_at = datetime.now(UTC).isoformat()
        self._run_started_perf = time.perf_counter()
        self.status = "running"
        self.storage.insert_run(
            {
                "run_id": self.run_id,
                "run_name": self.run_name,
                "project_root": str(self.project_root),
                "scenario_kind": self.scenario_kind,
                "hardware_profile": self.hardware_profile,
                "started_at": self.started_at,
                "finished_at": None,
                "status": self.status,
            }
        )
        self._sampler.start()
        self._tracer.start()
        return self.run_id

    def stop(self, status: str = "completed", aggregate_async: bool = True) -> Future | None:
        self._tracer.stop()
        self._sampler.stop()
        self._run_finished_perf = time.perf_counter()
        self.finished_at = datetime.now(UTC).isoformat()
        self.status = status
        write_started = time.perf_counter()
        self.storage.insert_run(
            {
                "run_id": self.run_id,
                "run_name": self.run_name,
                "project_root": str(self.project_root),
                "scenario_kind": self.scenario_kind,
                "hardware_profile": self.hardware_profile,
                "started_at": self.started_at or self.finished_at,
                "finished_at": self.finished_at,
                "status": status,
            }
        )
        self.storage.insert_function_rows(self.run_id, self.function_rows())
        self.storage.insert_resource_samples(self.run_id, self.resource_sample_rows())
        self.storage.insert_external_bucket_rows(self.run_id, self.external_bucket_rows())
        self.storage.insert_live_file_rows(self.run_id, self.live_ranking_rows())
        self._sqlite_write_time_ms += (time.perf_counter() - write_started) * 1000.0
        if aggregate_async:
            return self.aggregator.aggregate_run_async(self.run_id)
        return None

    def record_symbol_event(self, event: SymbolEvent) -> None:
        with self._lock:
            accumulator = self._functions.setdefault(
                event.symbol_key,
                _FunctionAccumulator(
                    symbol_key=event.symbol_key,
                    display_name=event.display_name,
                    file_path=event.file_path,
                    function_name=event.function_name,
                ),
            )
            accumulator.self_time_ms += event.self_time_ms
            accumulator.total_time_ms += event.elapsed_ms
            accumulator.call_count += 1
            if event.recursion_depth > 1:
                accumulator.recursive_call_count += 1
            accumulator.max_recursion_depth = max(accumulator.max_recursion_depth, event.recursion_depth)
            if event.had_exception:
                accumulator.exception_count += 1
                accumulator.last_exception_type = event.exception_type
            self._ranking.record(event.file_path, event.elapsed_ms, 1)

    def record_external_bucket(self, event: ExternalBucketEvent) -> None:
        with self._lock:
            accumulator = self._external_buckets.setdefault(
                event.bucket_name,
                _ExternalBucketAccumulator(bucket_name=event.bucket_name),
            )
            accumulator.total_time_ms += event.elapsed_ms
            accumulator.call_count += 1

    def record_resource_sample(self, sample: ResourceSample) -> None:
        with self._lock:
            self._resource_samples.append(sample)

    def record_tracer_callback_time(self, elapsed_ms: float) -> None:
        with self._lock:
            self._trace_event_count += 1
            self._tracer_callback_time_ms += elapsed_ms

    def function_rows(self) -> list[dict[str, object]]:
        with self._lock:
            rows = [
                {
                    "symbol_key": item.symbol_key,
                    "display_name": item.display_name,
                    "file_path": item.file_path,
                    "function_name": item.function_name,
                    "self_time_ms": item.self_time_ms,
                    "total_time_ms": item.total_time_ms,
                    "call_count": item.call_count,
                    "recursive_call_count": item.recursive_call_count,
                    "max_recursion_depth": item.max_recursion_depth,
                    "exception_count": item.exception_count,
                    "last_exception_type": item.last_exception_type,
                }
                for item in self._functions.values()
            ]
        rows.sort(key=lambda row: (-float(row["total_time_ms"]), str(row["symbol_key"])))
        return rows

    def resource_sample_rows(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "sample_ts": sample.sample_ts,
                    "cpu_percent": sample.cpu_percent,
                    "rss_mb": sample.rss_mb,
                    "read_bytes": sample.read_bytes,
                    "write_bytes": sample.write_bytes,
                }
                for sample in self._resource_samples
            ]

    def external_bucket_rows(self) -> list[dict[str, object]]:
        with self._lock:
            rows = [
                {
                    "bucket_name": item.bucket_name,
                    "total_time_ms": item.total_time_ms,
                    "call_count": item.call_count,
                }
                for item in self._external_buckets.values()
            ]
        rows.sort(key=lambda row: (-float(row["total_time_ms"]), str(row["bucket_name"])))
        return rows

    def live_hot_files(self, limit: int = 10) -> list[dict[str, object]]:
        return [
            {
                "file_path": item.file_path,
                "file_name": item.file_name,
                "rolling_score": item.rolling_score,
                "raw_ms": item.raw_ms,
                "call_count": item.call_count,
            }
            for item in self._ranking.snapshot(limit=limit)
        ]

    def live_ranking_rows(self) -> list[dict[str, object]]:
        return self.live_hot_files(limit=1000)

    def latest_resource_sample(self) -> dict[str, object]:
        with self._lock:
            if not self._resource_samples:
                return {
                    "sample_ts": 0.0,
                    "cpu_percent": 0.0,
                    "rss_mb": 0.0,
                    "read_bytes": None,
                    "write_bytes": None,
                }
            sample = self._resource_samples[-1]
        return {
            "sample_ts": sample.sample_ts,
            "cpu_percent": sample.cpu_percent,
            "rss_mb": sample.rss_mb,
            "read_bytes": sample.read_bytes,
            "write_bytes": sample.write_bytes,
        }

    def debug_snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "raw_function_row_count": len(self._functions),
                "sampler_sample_count": len(self._resource_samples),
                "trace_event_count": self._trace_event_count,
                "files_seen": len({item.file_path for item in self._functions.values()}),
                "external_buckets": [
                    {
                        "bucket_name": item.bucket_name,
                        "total_time_ms": item.total_time_ms,
                        "call_count": item.call_count,
                    }
                    for item in sorted(
                        self._external_buckets.values(),
                        key=lambda entry: (-entry.total_time_ms, entry.bucket_name),
                    )
                ],
            }

    def performance_snapshot(self) -> dict[str, object]:
        with self._lock:
            function_count = len(self._functions)
            files_seen = len({item.file_path for item in self._functions.values()})
            trace_event_count = self._trace_event_count
            tracer_callback_time_ms = self._tracer_callback_time_ms
            sample_count = len(self._resource_samples)
        runtime_ms = 0.0
        if self._run_started_perf is not None:
            finished_perf = self._run_finished_perf if self._run_finished_perf is not None else time.perf_counter()
            runtime_ms = max((finished_perf - self._run_started_perf) * 1000.0, 0.0)
        quality, reasons = _run_quality(
            function_count=function_count,
            files_seen=files_seen,
            sample_count=sample_count,
            runtime_ms=runtime_ms,
            trace_overhead_ms=tracer_callback_time_ms,
        )
        return {
            "run_id": self.run_id,
            "run_name": self.run_name,
            "scenario_kind": self.scenario_kind,
            "hardware_profile": self.hardware_profile,
            "trace_events": trace_event_count,
            "functions_seen": function_count,
            "files_seen": files_seen,
            "resource_samples": sample_count,
            "instrumented_runtime_ms": runtime_ms,
            "sqlite_write_time_ms": self._sqlite_write_time_ms,
            "trace_overhead_estimate_ms": tracer_callback_time_ms,
            "top_files_by_raw_ms": self.live_hot_files(limit=10),
            "run_quality": quality,
            "run_quality_reasons": reasons,
        }


def _run_quality(
    *,
    function_count: int,
    files_seen: int,
    sample_count: int,
    runtime_ms: float,
    trace_overhead_ms: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if files_seen <= 1:
        reasons.append("very low file coverage")
    elif files_seen <= 3:
        reasons.append("low file coverage")
    if function_count <= 2:
        reasons.append("very low function coverage")
    elif function_count <= 5:
        reasons.append("low function coverage")
    if sample_count <= 1:
        reasons.append("insufficient resource samples")
    elif sample_count <= 3:
        reasons.append("few resource samples")
    if runtime_ms < 1000.0:
        reasons.append("short runtime")
    if runtime_ms > 0.0 and trace_overhead_ms / runtime_ms >= 0.75:
        reasons.append("trace overhead dominates runtime")
    elif runtime_ms > 0.0 and trace_overhead_ms / runtime_ms >= 0.5:
        reasons.append("trace overhead is high")

    if "trace overhead dominates runtime" in reasons or "very low file coverage" in reasons:
        return "diagnostic_only", reasons
    if reasons:
        return "weak", reasons
    return "strong", []
