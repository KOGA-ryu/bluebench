import math


def expensive_work(value: int) -> int:
    total = 0
    for index in range(50):
        total += int(math.sqrt(index + value))
    return total
