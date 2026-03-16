# Module Tree

Relevant canonical layers and consumers:

```text
backend/
  evidence/
    __init__.py
    schemas/
      __init__.py
      run_schema.py
    store/
      __init__.py
      sqlite_store.py
    loaders/
      __init__.py
      evidence_loader.py
      run_loader.py

  derive/
    __init__.py
    compute_details.py
    evidence_labels.py
    hotspot_ranker.py
    run_comparator.py
    summary_builder.py

  experiments/
    __init__.py
    base.py
    compare_runs.py
    isolate_hotspot.py

  adapters/
    __init__.py
    cli/
      __init__.py
      commands.py
    codex/
      __init__.py
      context_pack.py
```

Current downstream consumers on the canonical path:

```text
backend/context/service.py
backend/context/exporters.py
backend/stress_engine.py
backend/main.py
backend/triage/runtime_summary.py
backend/triage/exporter.py
backend/triage/service.py
backend/reports/
```
