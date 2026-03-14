from __future__ import annotations

from dataclasses import dataclass
from math import exp
from pathlib import Path
import time


@dataclass
class LiveRankingEntry:
    file_path: str
    file_name: str
    rolling_score: float
    raw_ms: float
    call_count: int


class LiveRankingCalculator:
    def __init__(self, decay_seconds: float = 5.0) -> None:
        self.decay_seconds = max(decay_seconds, 0.1)
        self._entries: dict[str, dict[str, float | str | int]] = {}

    def record(self, file_path: str, elapsed_ms: float, call_count: int = 1, now: float | None = None) -> None:
        timestamp = now if now is not None else time.perf_counter()
        entry = self._entries.setdefault(
            file_path,
            {
                "file_path": file_path,
                "file_name": Path(file_path).name,
                "rolling_score": 0.0,
                "raw_ms": 0.0,
                "call_count": 0,
                "updated_at": timestamp,
            },
        )
        previous_timestamp = float(entry["updated_at"])
        decay = exp(-(max(timestamp - previous_timestamp, 0.0) / self.decay_seconds))
        entry["rolling_score"] = (float(entry["rolling_score"]) * decay) + max(elapsed_ms, 0.0)
        entry["raw_ms"] = float(entry["raw_ms"]) + max(elapsed_ms, 0.0)
        entry["call_count"] = int(entry["call_count"]) + max(call_count, 0)
        entry["updated_at"] = timestamp

    def snapshot(self, limit: int = 10, now: float | None = None) -> list[LiveRankingEntry]:
        timestamp = now if now is not None else time.perf_counter()
        ranked: list[LiveRankingEntry] = []
        for file_path, entry in self._entries.items():
            decay = exp(-(max(timestamp - float(entry["updated_at"]), 0.0) / self.decay_seconds))
            rolling_score = float(entry["rolling_score"]) * decay
            ranked.append(
                LiveRankingEntry(
                    file_path=file_path,
                    file_name=str(entry["file_name"]),
                    rolling_score=rolling_score,
                    raw_ms=float(entry["raw_ms"]),
                    call_count=int(entry["call_count"]),
                )
            )
        ranked.sort(key=lambda item: (-item.rolling_score, -item.raw_ms, item.file_path))
        return ranked[:limit]

