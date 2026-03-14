from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import math

from .storage import InstrumentationStorage


class BackgroundAggregator:
    def __init__(self, storage: InstrumentationStorage, top_n: int = 10) -> None:
        self.storage = storage
        self.top_n = top_n
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bluebench-aggregate")

    def aggregate_run_async(self, run_id: str) -> Future:
        return self._executor.submit(self.aggregate_run, run_id)

    def aggregate_run(self, run_id: str) -> None:
        run_row = self.storage.fetch_run(run_id)
        if run_row is None:
            return

        function_rows = self.storage.fetch_function_rows(run_id)
        resource_samples = self.storage.fetch_resource_samples(run_id)
        external_rows = self.storage.fetch_external_bucket_rows(run_id)
        live_rows = self.storage.fetch_live_file_rows(run_id)

        function_summaries = self._function_summaries(function_rows)
        file_summaries = self._file_summaries(function_rows, resource_samples, external_rows, live_rows)
        previous_run_id = self.storage.fetch_previous_comparable_run_id(
            run_id,
            str(run_row["scenario_kind"]),
            str(run_row["hardware_profile"]),
        )
        previous_scores = self.storage.fetch_file_summary_map(previous_run_id) if previous_run_id else {}
        run_summary = self._run_summary(file_summaries, function_rows, previous_scores)
        self.storage.replace_staged_summaries(run_id, run_summary, function_summaries, file_summaries)

    def _function_summaries(self, function_rows) -> list[dict[str, object]]:
        if not function_rows:
            return []
        scored_rows: list[dict[str, object]] = []
        max_score = 0.0
        for row in function_rows:
            score = (
                float(row["total_time_ms"]) * 0.6
                + float(row["self_time_ms"]) * 0.4
                + math.log1p(int(row["call_count"])) * 4.0
            )
            max_score = max(max_score, score)
            scored_rows.append(
                {
                    "symbol_key": str(row["symbol_key"]),
                    "file_path": str(row["file_path"]),
                    "display_name": str(row["display_name"]),
                    "self_time_ms": float(row["self_time_ms"]),
                    "total_time_ms": float(row["total_time_ms"]),
                    "call_count": int(row["call_count"]),
                    "exception_count": int(row["exception_count"]),
                    "last_exception_type": row["last_exception_type"],
                    "_score": score,
                }
            )
        for row in scored_rows:
            row["normalized_compute_score"] = (row.pop("_score") / max_score * 100.0) if max_score > 0 else 0.0
        return scored_rows

    def _file_summaries(self, function_rows, resource_samples, external_rows, live_rows) -> list[dict[str, object]]:
        file_groups: dict[str, dict[str, object]] = {}
        total_runtime_ms = sum(float(row["total_time_ms"]) for row in function_rows) or 1.0
        average_cpu = sum(float(row["cpu_percent"]) for row in resource_samples) / max(len(resource_samples), 1)
        average_rss = sum(float(row["rss_mb"]) for row in resource_samples) / max(len(resource_samples), 1)
        external_summary = {
            str(row["bucket_name"]): {
                "total_time_ms": float(row["total_time_ms"]),
                "call_count": int(row["call_count"]),
            }
            for row in external_rows
        }
        live_map = {
            str(row["file_path"]): {
                "rolling_score": float(row["rolling_score"]),
                "raw_ms": float(row["raw_ms"]),
                "call_count": int(row["call_count"]),
            }
            for row in live_rows
        }

        for row in function_rows:
            file_path = str(row["file_path"])
            group = file_groups.setdefault(
                file_path,
                {
                    "file_path": file_path,
                    "total_self_time_ms": 0.0,
                    "total_time_ms": 0.0,
                    "call_count": 0,
                    "exception_count": 0,
                    "max_function_total_ms": 0.0,
                },
            )
            total_time_ms = float(row["total_time_ms"])
            group["total_self_time_ms"] = float(group["total_self_time_ms"]) + float(row["self_time_ms"])
            group["total_time_ms"] = float(group["total_time_ms"]) + total_time_ms
            group["call_count"] = int(group["call_count"]) + int(row["call_count"])
            group["exception_count"] = int(group["exception_count"]) + int(row["exception_count"])
            group["max_function_total_ms"] = max(float(group["max_function_total_ms"]), total_time_ms)

        scored_rows: list[dict[str, object]] = []
        max_score = 0.0
        for group in file_groups.values():
            hotspot_concentration = float(group["max_function_total_ms"]) / max(float(group["total_time_ms"]), 1.0)
            runtime_share = float(group["total_time_ms"]) / total_runtime_ms
            resource_pressure = runtime_share * ((average_cpu * 0.6) + (average_rss * 0.4))
            score = (
                float(group["total_time_ms"]) * 0.45
                + float(group["total_self_time_ms"]) * 0.35
                + math.log1p(int(group["call_count"])) * 6.0
                + hotspot_concentration * 20.0
                + resource_pressure
            )
            max_score = max(max_score, score)
            file_path = str(group["file_path"])
            live_entry = live_map.get(file_path, {"rolling_score": 0.0, "raw_ms": 0.0, "call_count": 0})
            scored_rows.append(
                {
                    "file_path": file_path,
                    "total_self_time_ms": float(group["total_self_time_ms"]),
                    "total_time_ms": float(group["total_time_ms"]),
                    "call_count": int(group["call_count"]),
                    "exception_count": int(group["exception_count"]),
                    "external_pressure_summary": {
                        "runtime_share": runtime_share,
                        "avg_cpu_percent": average_cpu,
                        "avg_rss_mb": average_rss,
                        "external_buckets": external_summary,
                    },
                    "rolling_score": float(live_entry["rolling_score"]),
                    "_score": score,
                }
            )
        for row in scored_rows:
            row["normalized_compute_score"] = (row.pop("_score") / max_score * 100.0) if max_score > 0 else 0.0
        return scored_rows

    def _run_summary(self, file_summaries, function_rows, previous_scores: dict[str, float]) -> dict[str, object]:
        hottest_files = sorted(
            file_summaries,
            key=lambda row: (-float(row["rolling_score"]), -float(row["total_time_ms"]), str(row["file_path"])),
        )[: self.top_n]
        deltas = []
        for row in file_summaries:
            file_path = str(row["file_path"])
            current_score = float(row["normalized_compute_score"])
            previous_score = float(previous_scores.get(file_path, 0.0))
            deltas.append(
                {
                    "file_path": file_path,
                    "score_delta": current_score - previous_score,
                }
            )
        deltas.sort(key=lambda row: (-abs(float(row["score_delta"])), str(row["file_path"])))
        failure_count = sum(int(row["exception_count"]) for row in function_rows)
        return {
            "hottest_files": hottest_files,
            "biggest_score_deltas": deltas[: self.top_n],
            "failure_count": failure_count,
        }

