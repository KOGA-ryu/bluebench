# Quickstart

## Install
```bash
make install
```

## Run BlueBench
Launch the desktop shell:
```bash
make run-bluebench
```

Run one instrumented script target:
```bash
bin/bluebench run tools/verification/bluebench_real_verify.py -- --project-root /path/to/project
```

Compare two runs:
```bash
bin/bluebench compare RUN_A RUN_B --project-root /path/to/project
```

Get the next recommendation:
```bash
bin/bluebench recommend-next --target backend/scanner/python_parser/python_scanner.py --run RUN_B --baseline RUN_A --project-root /path/to/project
```

## Run Scanner
Normal verification run:
```bash
make run-scanner
```

Instrument the scanner with BlueBench:
```bash
bin/scanner run --instrument --mode smoke
```

Run the live benchmark probe:
```bash
bin/scanner benchmark --profile top_gainers_mvp --symbols NVDA,AAPL --repeats 3
```

## Test
```bash
make test
```

## Main Loop
1. Run scanner or target workload.
2. Use BlueBench to inspect hotspots.
3. Use `compare` and `recommend-next`.
4. Make one targeted change.
5. Rerun and compare.
