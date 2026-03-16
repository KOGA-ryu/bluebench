# BlueBench

BlueBench is an evidence-first engineering workbench. It collects runtime evidence, derives canonical hotspot and comparison outputs, and exposes those results through UI, reports, CLI commands, and Codex-facing packets.

The sibling scanner project is the primary live workload used with BlueBench in this repo. Its loop is:

`scan target -> BlueBench analysis -> hotspot report -> recommendation`

BlueBench’s own loop is:

`run evidence collection -> derive results -> emit packets -> show summary`

## Install
```bash
make install
```

## Run
Launch the desktop shell:
```bash
make run-bluebench
```

Instrument a script target:
```bash
bin/bluebench run tools/verification/bluebench_real_verify.py -- --project-root /Users/kogaryu/dev/bluebench
```

Compare runs:
```bash
bin/bluebench compare RUN_A RUN_B --project-root /Users/kogaryu/dev/bluebench
```

Get the next recommended step:
```bash
bin/bluebench recommend-next \
  --target backend/scanner/python_parser/python_scanner.py \
  --run RUN_B \
  --baseline RUN_A \
  --project-root /Users/kogaryu/dev/bluebench
```

Stress the canonical flow:
```bash
bin/bluebench stress-canonical --project-root /Users/kogaryu/dev/bluebench --iterations 100
```

## Scanner Wrapper
Run the scanner once:
```bash
make run-scanner
```

Run the scanner under BlueBench instrumentation:
```bash
bin/scanner run --instrument --mode smoke
```

Benchmark the live scanner path:
```bash
bin/scanner benchmark --profile top_gainers_mvp --symbols NVDA,AAPL --repeats 3
```

## Example Output
```text
{
  "target": "backend/scanner/python_parser/python_scanner.py",
  "recommended_experiment": "isolate_hotspot",
  "confidence": "high"
}
```

## Docs
- [Quickstart](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [Terminology](docs/terminology.md)

## Version
```bash
bin/bluebench --version
bin/scanner --version
```
