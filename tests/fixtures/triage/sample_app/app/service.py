import sqlite3

from core.worker import expensive_work


def load_items() -> list[int]:
    sqlite3.connect(":memory:").close()
    return [expensive_work(index) for index in range(3)]
