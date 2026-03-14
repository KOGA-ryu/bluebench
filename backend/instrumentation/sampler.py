from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import resource
import threading
import time


@dataclass
class ResourceSample:
    sample_ts: float
    cpu_percent: float
    rss_mb: float
    read_bytes: int | None
    write_bytes: int | None


class ResourceSampler:
    def __init__(
        self,
        callback: Callable[[ResourceSample], None],
        interval_seconds: float = 0.25,
    ) -> None:
        self.callback = callback
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_process_time: float | None = None
        self._last_wall_time: float | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="bluebench-resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.interval_seconds * 2, 0.5))
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.callback(self._sample())
            self._stop_event.wait(self.interval_seconds)

    def _sample(self) -> ResourceSample:
        now = time.time()
        process_time = time.process_time()
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = float(usage.ru_maxrss) / 1024.0
        cpu_percent = 0.0
        if self._last_process_time is not None and self._last_wall_time is not None:
            wall_delta = max(now - self._last_wall_time, 0.001)
            cpu_delta = max(process_time - self._last_process_time, 0.0)
            cpu_percent = (cpu_delta / wall_delta) * 100.0 / max(os.cpu_count() or 1, 1)
        self._last_process_time = process_time
        self._last_wall_time = now
        read_bytes, write_bytes = self._io_counters()
        return ResourceSample(
            sample_ts=now,
            cpu_percent=cpu_percent,
            rss_mb=rss_mb,
            read_bytes=read_bytes,
            write_bytes=write_bytes,
        )

    def _io_counters(self) -> tuple[int | None, int | None]:
        proc_io_path = Path("/proc/self/io")
        if not proc_io_path.exists():
            return None, None
        try:
            contents = proc_io_path.read_text(encoding="utf-8")
        except OSError:
            return None, None
        values: dict[str, int] = {}
        for line in contents.splitlines():
            if ":" not in line:
                continue
            key, raw_value = line.split(":", 1)
            try:
                values[key.strip()] = int(raw_value.strip())
            except ValueError:
                continue
        return values.get("read_bytes"), values.get("write_bytes")

