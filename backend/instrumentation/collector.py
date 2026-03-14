from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import threading
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

    def start(self) -> str:
        self.storage.initialize_schema()
        self.started_at = datetime.now(UTC).isoformat()
        self.status = "running"
        self.storage.insert_run(
            {
                "run_id": self.run_id,
                "run_name": self.run_name,
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

    def stop(self, status: str = "completed") -> str:
        self._tracer.stop()
        self._sampler.stop()
        self.finished_at = datetime.now(UTC).isoformat()
        self.status = status
        self.storage.insert_run(
            {
                "run_id": self.run_id,
                "run_name": self.run_name,
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
        self.aggregator.aggregate_run_async(self.run_id)
        return self.run_id

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

