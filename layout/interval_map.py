from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    start: int
    end: int


class ColumnIntervalMap:
    def __init__(self) -> None:
        self._intervals: dict[int, list[Interval]] = defaultdict(list)

    def clear(self) -> None:
        self._intervals.clear()

    def get_intervals(self, column: int) -> list[Interval]:
        return list(self._intervals.get(column, []))

    def find_free_start(self, column: int, start_y: int, height: int) -> int:
        intervals = self._intervals.get(column, [])
        if not intervals:
            return start_y

        candidate = start_y
        starts = [interval.start for interval in intervals]
        index = max(0, bisect_left(starts, start_y) - 1)

        while index < len(intervals):
            interval = intervals[index]
            if candidate + height <= interval.start:
                return candidate
            if candidate < interval.end:
                candidate = interval.end
            index += 1

        return candidate

    def reserve(self, column: int, start_y: int, end_y: int) -> Interval:
        if end_y <= start_y:
            raise ValueError("end_y must be greater than start_y")

        new_interval = Interval(start=start_y, end=end_y)
        intervals = self._intervals[column]
        if not intervals:
            intervals.append(new_interval)
            return new_interval

        merged: list[Interval] = []
        inserted = False

        for interval in intervals:
            if interval.end < new_interval.start:
                merged.append(interval)
                continue

            if new_interval.end < interval.start:
                if not inserted:
                    merged.append(new_interval)
                    inserted = True
                merged.append(interval)
                continue

            new_interval = Interval(
                start=min(new_interval.start, interval.start),
                end=max(new_interval.end, interval.end),
            )

        if not inserted:
            merged.append(new_interval)

        self._intervals[column] = merged
        return new_interval
