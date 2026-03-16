# Architecture

## Purpose
BlueBench is an evidence-first investigation tool. It collects runtime evidence, derives canonical summaries from that evidence, and exposes those results through UI, CLI, reports, and Codex-facing packets.

## Core Flow
BlueBench loop:
1. Run evidence collection.
2. Load canonical evidence.
3. Derive summaries, comparisons, and packets.
4. Show or export the result.

Scanner loop:
1. Run a scan target.
2. Analyze the run with BlueBench.
3. Inspect hotspots and recommendations.
4. Apply one targeted change.
5. Compare the next run against the baseline.

## Layer Rules
- `backend/evidence/`: raw run facts and persistence only.
- `backend/derive/`: canonical hotspot, comparison, quality, and summary logic.
- `backend/experiments/`: named recipes over canonical layers.
- `backend/adapters/`: CLI, Codex, and UI consumers only.
- `backend/reports/`: formatting only.

## Product Entry Points
- `bin/bluebench`: product CLI for evidence collection, comparison, recommendation, and stress checks.
- `bin/scanner`: scanner wrapper for a normal run, instrumented run, and live benchmark.
- `scripts/run_bluebench.py`: BlueBench wrapper implementation.
- `scripts/run_scanner.py`: scanner wrapper implementation.

## User Loops
BlueBench:
`run evidence collection -> derive results -> emit packets -> show summary`

Scanner:
`scan target -> BlueBench analysis -> hotspot report -> recommendation`
