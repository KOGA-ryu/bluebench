from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import runpy
import signal
import sys
import threading
import time

from .aggregator import BackgroundAggregator
from .collector import RunMetricsCollector
from .storage import InstrumentationStorage


def _parse_cli(argv: list[str]) -> dict[str, object]:
    if "--" not in argv:
        raise SystemExit("expected -- separator before script args")
    separator = argv.index("--")
    options = argv[:separator]
    script_args = argv[separator + 1 :]
    parsed: dict[str, object] = {"script_args": script_args}
    iterator = iter(options)
    for token in iterator:
        if not token.startswith("--"):
            continue
        key = token[2:].replace("-", "_")
        parsed[key] = next(iterator)
    required = {"database", "project_root", "script_path", "run_name"}
    missing = [key for key in required if key not in parsed]
    if missing:
        raise SystemExit(f"missing required options: {', '.join(missing)}")
    parsed.setdefault("scenario_kind", "instrumented_script")
    parsed.setdefault("hardware_profile", platform.platform())
    return parsed


class _LiveStateWriter:
    def __init__(
        self,
        storage: InstrumentationStorage,
        collector: RunMetricsCollector,
        *,
        run_id: str,
        script_path: str,
        parsed_args: list[str],
        started_at: str,
        stdout_buffer: deque[str],
        stderr_buffer: deque[str],
    ) -> None:
        self.storage = storage
        self.collector = collector
        self.run_id = run_id
        self.script_path = script_path
        self.parsed_args = parsed_args
        self.started_at = started_at
        self.stdout_buffer = stdout_buffer
        self.stderr_buffer = stderr_buffer
        self.status = "running"
        self.aggregation_status = "idle"
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="bluebench-live-state", daemon=True)
        self._started_at_perf = time.perf_counter()
        self.flush_count = 0
        self.flush_total_time_ms = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        self.flush_once()

    def flush_once(self) -> None:
        flush_started = time.perf_counter()
        sample = self.collector.latest_resource_sample()
        debug = self.collector.debug_snapshot()
        self.storage.upsert_live_run_state(
            {
                "run_id": self.run_id,
                "script_path": self.script_path,
                "parsed_args": self.parsed_args,
                "started_at": self.started_at,
                "elapsed_seconds": max(time.perf_counter() - self._started_at_perf, 0.0),
                "status": self.status,
                "cpu_percent": sample["cpu_percent"],
                "rss_mb": sample["rss_mb"],
                "aggregation_status": self.aggregation_status,
                "raw_function_row_count": debug["raw_function_row_count"],
                "sampler_sample_count": debug["sampler_sample_count"],
                "external_buckets": debug["external_buckets"],
                "stdout_tail": "\n".join(self.stdout_buffer),
                "stderr_tail": "\n".join(self.stderr_buffer),
            }
        )
        self.storage.replace_live_file_rows(self.run_id, self.collector.live_ranking_rows())
        self.flush_count += 1
        self.flush_total_time_ms += (time.perf_counter() - flush_started) * 1000.0

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.flush_once()
            self._stop_event.wait(0.5)


def main() -> int:
    options = _parse_cli(sys.argv[1:])
    project_root = Path(str(options["project_root"])).resolve()
    script_path = Path(str(options["script_path"])).resolve()
    storage = InstrumentationStorage(str(options["database"]))
    aggregator = BackgroundAggregator(storage)
    collector = RunMetricsCollector(
        project_root,
        storage,
        aggregator,
        run_name=str(options["run_name"]),
        scenario_kind=str(options["scenario_kind"]),
        hardware_profile=str(options["hardware_profile"]),
    )
    stdout_buffer: deque[str] = deque(maxlen=200)
    stderr_buffer: deque[str] = deque(maxlen=200)
    run_id = collector.start()
    started_at = collector.started_at or datetime.now().isoformat()
    live_writer = _LiveStateWriter(
        storage,
        collector,
        run_id=run_id,
        script_path=script_path.as_posix(),
        parsed_args=[str(item) for item in options["script_args"]],
        started_at=started_at,
        stdout_buffer=stdout_buffer,
        stderr_buffer=stderr_buffer,
    )

    stop_requested = {"value": False}

    def request_stop(_signum, _frame) -> None:
        stop_requested["value"] = True
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    class _StreamCapture:
        def __init__(self, target, buffer: deque[str]) -> None:
            self.target = target
            self.buffer = buffer

        def write(self, text: str) -> int:
            if text:
                for line in text.rstrip().splitlines():
                    self.buffer.append(line)
            return self.target.write(text)

        def flush(self) -> None:
            self.target.flush()

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = _StreamCapture(original_stdout, stdout_buffer)
    sys.stderr = _StreamCapture(original_stderr, stderr_buffer)
    live_writer.start()
    exit_code = 0
    final_status = "completed"
    instrumented_runtime_started = time.perf_counter()
    instrumented_runtime_ms = 0.0
    aggregation_time_ms = 0.0
    report_path: str | None = None

    try:
        sys.argv = [script_path.as_posix(), *[str(item) for item in options["script_args"]]]
        os.chdir(project_root)
        sys.path.insert(0, str(project_root))
        sys.path.insert(0, str(script_path.parent))
        runpy.run_path(str(script_path), run_name="__main__")
    except KeyboardInterrupt:
        final_status = "stopped" if stop_requested["value"] else "failed"
        exit_code = 130 if stop_requested["value"] else 1
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        exit_code = code
        final_status = "completed" if code == 0 else "failed"
    except Exception:
        import traceback

        traceback.print_exc()
        final_status = "failed"
        exit_code = 1
    finally:
        instrumented_runtime_ms = max((time.perf_counter() - instrumented_runtime_started) * 1000.0, 0.0)
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        live_writer.status = final_status
        live_writer.flush_once()
        live_writer.stop()
        collector.stop(status=final_status, aggregate_async=False)
        live_writer.status = "aggregating"
        live_writer.aggregation_status = "running"
        live_writer.flush_once()
        try:
            aggregation_started = time.perf_counter()
            aggregator.aggregate_run(run_id)
            aggregation_time_ms = (time.perf_counter() - aggregation_started) * 1000.0
            live_writer.aggregation_status = "complete"
        except Exception:
            live_writer.aggregation_status = "failed"
            raise
        finally:
            live_writer.status = final_status
            live_writer.flush_once()
            performance_report = collector.performance_snapshot()
            performance_report.update(
                {
                    "instrumented_runtime_ms": instrumented_runtime_ms,
                    "aggregation_time_ms": aggregation_time_ms,
                    "live_state_flush_time_ms": live_writer.flush_total_time_ms,
                    "live_state_flush_count": live_writer.flush_count,
                    "report_generated_at": datetime.now().isoformat(),
                    "script_path": script_path.as_posix(),
                    "parsed_args": [str(item) for item in options["script_args"]],
                    "status": final_status,
                }
            )
            report_path = storage.write_performance_report(project_root, performance_report).as_posix()
            aggregator.shutdown()
            if report_path:
                print(json.dumps({"bb_performance_report": report_path}))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
