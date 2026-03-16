from __future__ import annotations

import argparse
import json
import random
import statistics
import time


def build_payload(items: int) -> list[dict[str, object]]:
    payload = []
    for index in range(items):
        payload.append(
            {
                "index": index,
                "value": random.random(),
                "tags": [f"tag-{index % 5}", f"group-{index % 3}"],
            }
        )
    return payload


def external_bucket_pass(items: int) -> float:
    payload = build_payload(items)
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    return statistics.fmean(float(item["value"]) for item in decoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=int, default=700)
    parser.add_argument("--passes", type=int, default=5)
    args = parser.parse_args()

    values = []
    for _ in range(args.passes):
        values.append(external_bucket_pass(args.items))
        time.sleep(0.02)

    print({"mean": round(statistics.fmean(values), 6)})


if __name__ == "__main__":
    main()
