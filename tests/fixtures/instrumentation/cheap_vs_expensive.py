from __future__ import annotations

import argparse
import math
import time


def cheap_step(value: int) -> float:
    return math.sqrt(value + 1)


def expensive_step(size: int) -> int:
    total = 0
    for outer in range(size):
        for inner in range(size):
            total += (outer * inner) % 17
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cheap-loops", type=int, default=20000)
    parser.add_argument("--expensive-size", type=int, default=180)
    parser.add_argument("--expensive-runs", type=int, default=3)
    args = parser.parse_args()

    cheap_total = 0.0
    for index in range(args.cheap_loops):
        cheap_total += cheap_step(index)

    expensive_total = 0
    for _ in range(args.expensive_runs):
        expensive_total += expensive_step(args.expensive_size)
        time.sleep(0.02)

    print({"cheap_total": round(cheap_total, 2), "expensive_total": expensive_total})


if __name__ == "__main__":
    main()
