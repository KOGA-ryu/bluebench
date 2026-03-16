from __future__ import annotations

import argparse
import time


def recursive_work(depth: int) -> int:
    if depth <= 0:
        time.sleep(0.01)
        return 1
    return depth + recursive_work(depth - 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--repeats", type=int, default=4)
    args = parser.parse_args()

    results = []
    for _ in range(args.repeats):
        results.append(recursive_work(args.depth))

    print({"results": results})


if __name__ == "__main__":
    main()
