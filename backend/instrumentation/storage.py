from __future__ import annotations

import json
from pathlib import Path
import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    run_name TEXT NOT NULL,
    scenario_kind TEXT NOT NULL,
    hardware_profile TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS function_run_raw (
    run_id TEXT NOT NULL,
    symbol_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    function_name TEXT NOT NULL,
    self_time_ms REAL NOT NULL,
    total_time_ms REAL NOT NULL,
    call_count INTEGER NOT NULL,
    recursive_call_count INTEGER NOT NULL,
    max_recursion_depth INTEGER NOT NULL,
    exception_count INTEGER NOT NULL,
    last_exception_type TEXT,
    PRIMARY KEY (run_id, symbol_key)
);

CREATE TABLE IF NOT EXISTS resource_samples (
    run_id TEXT NOT NULL,
    sample_ts REAL NOT NULL,
    cpu_percent REAL NOT NULL,
    rss_mb REAL NOT NULL,
    read_bytes INTEGER,
    write_bytes INTEGER
);

CREATE TABLE IF NOT EXISTS external_bucket_raw (
    run_id TEXT NOT NULL,
    bucket_name TEXT NOT NULL,
    total_time_ms REAL NOT NULL,
    call_count INTEGER NOT NULL,
    PRIMARY KEY (run_id, bucket_name)
);

CREATE TABLE IF NOT EXISTS live_file_raw (
    run_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    rolling_score REAL NOT NULL,
    raw_ms REAL NOT NULL,
    call_count INTEGER NOT NULL,
    PRIMARY KEY (run_id, file_path)
);

CREATE TABLE IF NOT EXISTS run_summary (
    run_id TEXT PRIMARY KEY,
    hottest_files_json TEXT NOT NULL,
    biggest_score_deltas_json TEXT NOT NULL,
    failure_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS function_summary (
    run_id TEXT NOT NULL,
    symbol_key TEXT NOT NULL,
    file_path TEXT NOT NULL,
    display_name TEXT NOT NULL,
    self_time_ms REAL NOT NULL,
    total_time_ms REAL NOT NULL,
    call_count INTEGER NOT NULL,
    exception_count INTEGER NOT NULL,
    last_exception_type TEXT,
    normalized_compute_score REAL NOT NULL,
    PRIMARY KEY (run_id, symbol_key)
);

CREATE TABLE IF NOT EXISTS file_summary (
    run_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    total_self_time_ms REAL NOT NULL,
    total_time_ms REAL NOT NULL,
    call_count INTEGER NOT NULL,
    exception_count INTEGER NOT NULL,
    external_pressure_summary TEXT NOT NULL,
    normalized_compute_score REAL NOT NULL,
    rolling_score REAL NOT NULL,
    PRIMARY KEY (run_id, file_path)
);

CREATE TABLE IF NOT EXISTS run_summary_stage (
    run_id TEXT PRIMARY KEY,
    hottest_files_json TEXT NOT NULL,
    biggest_score_deltas_json TEXT NOT NULL,
    failure_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS function_summary_stage (
    run_id TEXT NOT NULL,
    symbol_key TEXT NOT NULL,
    file_path TEXT NOT NULL,
    display_name TEXT NOT NULL,
    self_time_ms REAL NOT NULL,
    total_time_ms REAL NOT NULL,
    call_count INTEGER NOT NULL,
    exception_count INTEGER NOT NULL,
    last_exception_type TEXT,
    normalized_compute_score REAL NOT NULL,
    PRIMARY KEY (run_id, symbol_key)
);

CREATE TABLE IF NOT EXISTS file_summary_stage (
    run_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    total_self_time_ms REAL NOT NULL,
    total_time_ms REAL NOT NULL,
    call_count INTEGER NOT NULL,
    exception_count INTEGER NOT NULL,
    external_pressure_summary TEXT NOT NULL,
    normalized_compute_score REAL NOT NULL,
    rolling_score REAL NOT NULL,
    PRIMARY KEY (run_id, file_path)
);
"""


class InstrumentationStorage:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def insert_run(self, run_row: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runs
                (run_id, run_name, scenario_kind, hardware_profile, started_at, finished_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_row["run_id"],
                    run_row["run_name"],
                    run_row["scenario_kind"],
                    run_row["hardware_profile"],
                    run_row["started_at"],
                    run_row.get("finished_at"),
                    run_row["status"],
                ),
            )

    def insert_function_rows(self, run_id: str, rows: list[dict[str, object]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO function_run_raw
                (run_id, symbol_key, display_name, file_path, function_name, self_time_ms, total_time_ms,
                 call_count, recursive_call_count, max_recursion_depth, exception_count, last_exception_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row["symbol_key"],
                        row["display_name"],
                        row["file_path"],
                        row["function_name"],
                        row["self_time_ms"],
                        row["total_time_ms"],
                        row["call_count"],
                        row["recursive_call_count"],
                        row["max_recursion_depth"],
                        row["exception_count"],
                        row["last_exception_type"],
                    )
                    for row in rows
                ],
            )

    def insert_resource_samples(self, run_id: str, rows: list[dict[str, object]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO resource_samples
                (run_id, sample_ts, cpu_percent, rss_mb, read_bytes, write_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row["sample_ts"],
                        row["cpu_percent"],
                        row["rss_mb"],
                        row["read_bytes"],
                        row["write_bytes"],
                    )
                    for row in rows
                ],
            )

    def insert_external_bucket_rows(self, run_id: str, rows: list[dict[str, object]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO external_bucket_raw
                (run_id, bucket_name, total_time_ms, call_count)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row["bucket_name"],
                        row["total_time_ms"],
                        row["call_count"],
                    )
                    for row in rows
                ],
            )

    def insert_live_file_rows(self, run_id: str, rows: list[dict[str, object]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO live_file_raw
                (run_id, file_path, rolling_score, raw_ms, call_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row["file_path"],
                        row["rolling_score"],
                        row["raw_ms"],
                        row["call_count"],
                    )
                    for row in rows
                ],
            )

    def fetch_run(self, run_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()

    def fetch_function_rows(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM function_run_raw WHERE run_id = ?", (run_id,)).fetchall()

    def fetch_resource_samples(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM resource_samples WHERE run_id = ?", (run_id,)).fetchall()

    def fetch_external_bucket_rows(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM external_bucket_raw WHERE run_id = ?", (run_id,)).fetchall()

    def fetch_live_file_rows(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM live_file_raw WHERE run_id = ?", (run_id,)).fetchall()

    def fetch_previous_comparable_run_id(self, run_id: str, scenario_kind: str, hardware_profile: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id FROM runs
                WHERE scenario_kind = ? AND hardware_profile = ? AND status = 'completed' AND run_id != ?
                ORDER BY finished_at DESC
                LIMIT 1
                """,
                (scenario_kind, hardware_profile, run_id),
            ).fetchone()
        return str(row["run_id"]) if row is not None else None

    def fetch_file_summary_map(self, run_id: str) -> dict[str, float]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT file_path, normalized_compute_score FROM file_summary WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        return {str(row["file_path"]): float(row["normalized_compute_score"]) for row in rows}

    def replace_staged_summaries(
        self,
        run_id: str,
        run_summary: dict[str, object],
        function_rows: list[dict[str, object]],
        file_rows: list[dict[str, object]],
    ) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM run_summary_stage WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM function_summary_stage WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM file_summary_stage WHERE run_id = ?", (run_id,))
            connection.execute(
                """
                INSERT INTO run_summary_stage (run_id, hottest_files_json, biggest_score_deltas_json, failure_count)
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    json.dumps(run_summary["hottest_files"]),
                    json.dumps(run_summary["biggest_score_deltas"]),
                    run_summary["failure_count"],
                ),
            )
            connection.executemany(
                """
                INSERT INTO function_summary_stage
                (run_id, symbol_key, file_path, display_name, self_time_ms, total_time_ms, call_count,
                 exception_count, last_exception_type, normalized_compute_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row["symbol_key"],
                        row["file_path"],
                        row["display_name"],
                        row["self_time_ms"],
                        row["total_time_ms"],
                        row["call_count"],
                        row["exception_count"],
                        row["last_exception_type"],
                        row["normalized_compute_score"],
                    )
                    for row in function_rows
                ],
            )
            connection.executemany(
                """
                INSERT INTO file_summary_stage
                (run_id, file_path, total_self_time_ms, total_time_ms, call_count, exception_count,
                 external_pressure_summary, normalized_compute_score, rolling_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        row["file_path"],
                        row["total_self_time_ms"],
                        row["total_time_ms"],
                        row["call_count"],
                        row["exception_count"],
                        json.dumps(row["external_pressure_summary"]),
                        row["normalized_compute_score"],
                        row["rolling_score"],
                    )
                    for row in file_rows
                ],
            )
            connection.execute("DELETE FROM run_summary WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM function_summary WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM file_summary WHERE run_id = ?", (run_id,))
            connection.execute(
                """
                INSERT INTO run_summary
                SELECT run_id, hottest_files_json, biggest_score_deltas_json, failure_count
                FROM run_summary_stage WHERE run_id = ?
                """,
                (run_id,),
            )
            connection.execute(
                """
                INSERT INTO function_summary
                SELECT run_id, symbol_key, file_path, display_name, self_time_ms, total_time_ms, call_count,
                       exception_count, last_exception_type, normalized_compute_score
                FROM function_summary_stage WHERE run_id = ?
                """,
                (run_id,),
            )
            connection.execute(
                """
                INSERT INTO file_summary
                SELECT run_id, file_path, total_self_time_ms, total_time_ms, call_count, exception_count,
                       external_pressure_summary, normalized_compute_score, rolling_score
                FROM file_summary_stage WHERE run_id = ?
                """,
                (run_id,),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

