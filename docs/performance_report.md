# BlueBench Performance Report

BlueBench now writes a per-run performance artifact named:

`bb_performance_report.json`

## Location

The report is written to the active run `project_root`.

Example:

```text
/path/to/project/bb_performance_report.json
```

For runs launched from the Stress Engine, the report path is also surfaced in:
- `Timeline`
- `Debug Details`

## Purpose

The report exists to show where time and resources moved during a run so optimization work is based on measured stage costs instead of guesswork.

## Current Fields

The report currently includes:

- `run_id`
- `run_name`
- `scenario_kind`
- `hardware_profile`
- `trace_events`
- `functions_seen`
- `files_seen`
- `resource_samples`
- `instrumented_runtime_ms`
- `sqlite_write_time_ms`
- `aggregation_time_ms`
- `live_state_flush_time_ms`
- `live_state_flush_count`
- `trace_overhead_estimate_ms`
- `top_files_by_raw_ms`
- `script_path`
- `parsed_args`
- `status`
- `report_generated_at`

## Meaning

- `instrumented_runtime_ms`
  Runtime spent executing the instrumented target script.

- `trace_overhead_estimate_ms`
  Estimated time spent inside tracked tracer callback handling for traced events.

- `sqlite_write_time_ms`
  Time spent flushing summarized raw rows to SQLite at run finalization.

- `aggregation_time_ms`
  Time spent building staged/final summaries after the run.

- `live_state_flush_time_ms`
  Total time spent updating live run state and live file rankings during the run.

- `top_files_by_raw_ms`
  Top files ranked from the live ranking path, useful for quick hotspot checks.

## Notes

- The report is a measurement aid, not the source of truth for final summaries.
- Final run summaries still come from SQLite summary tables:
  - `run_summary`
  - `file_summary`
  - `function_summary`
- The report is intended to make optimization targets obvious:
  - tracing
  - SQLite writes
  - aggregation
  - live state flushing

## Related Code

- [collector.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/collector.py)
- [script_runner.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/script_runner.py)
- [storage.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/storage.py)
- [stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py)
