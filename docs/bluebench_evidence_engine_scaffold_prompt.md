# Codex Prompt — BlueBench Evidence Engine Scaffolding

Goal:
Refactor BlueBench toward a strict `measure once, derive once, display many` architecture.

Do not rewrite the whole app.
Do not break existing BlueBench UI behavior.
Do not redesign the layout engine, Inspector, or Stress Engine UX in this pass.

This pass is for scaffolding the canonical architecture and extracting the first shared modules so later work stops duplicating truth across surfaces.

## Core Rule

BlueBench must separate:

1. evidence collection
2. evidence storage
3. derivation
4. presentation

The rule is:

- core measures once
- derive computes once
- adapters display many

Presentation layers must never invent core truth.

## Target Architecture

Create these top-level packages:

```text
backend/
  core/
    run_engine.py
    evidence_writer.py

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
      run_loader.py
      evidence_loader.py

  derive/
    __init__.py
    hotspot_ranker.py
    run_comparator.py
    summary_builder.py
    evidence_labels.py

  experiments/
    __init__.py
    base.py
    compare_runs.py
    isolate_hotspot.py

  adapters/
    __init__.py
    codex/
      __init__.py
      context_pack.py
    cli/
      __init__.py
      commands.py
```

You do not need to move every existing file immediately.
This is an extraction pass, not a rewrite pass.

## Dependency Law

Allowed dependencies:

- `core -> evidence`
- `derive -> evidence`
- `experiments -> core, evidence, derive`
- `adapters -> evidence, derive, experiments`

Forbidden dependencies:

- `core -> derive`
- `core -> adapters`
- `derive -> adapters`
- `reports/UI adapters -> custom ranking logic`

If an existing module already violates this, do not rewrite it wholesale here.
Instead, extract the new canonical logic and make current callers use it where practical.

## Scope For This Pass

Implement only the MVP architecture extraction:

### 1. Canonical run evidence schema

Create a canonical run evidence shape in:

```python
backend/evidence/schemas/run_schema.py
```

It must support at least:

- run metadata
- measured timings
- measured stage timings
- file-level timing records
- run quality
- evidence labels

Represent fields with plain Python dict helpers or dataclasses.
Do not overengineer validation yet.

Minimum fields:

```python
{
  "run_id": str,
  "run_name": str,
  "timestamp": str,
  "status": str,
  "quality": str | None,
  "measured": {
    "runtime_ms": float | None,
    "trace_overhead_ms": float | None,
  },
  "stages": {
    str: float
  },
  "files": [
    {
      "file_path": str,
      "raw_ms": float,
      "call_count": int | None
    }
  ]
}
```

### 2. Evidence label helpers

Create:

```python
backend/derive/evidence_labels.py
```

Provide a tiny canonical helper for labeled values:

```python
{
  "type": "measured" | "derived" | "inferred" | "missing",
  "key": str,
  "value": Any
}
```

This must be shared by derivation and adapters.

### 3. SQLite evidence adapter

Create:

```python
backend/evidence/store/sqlite_store.py
```

This layer must read existing BlueBench run data from the current SQLite storage and adapt it into canonical evidence objects.

Do not replace the current instrumentation database.
Wrap it.

Implement at least:

- `load_run_evidence(run_id)`
- `list_completed_runs(project_root=None)`
- `load_previous_comparable_run(run_id, project_root=None)`

This layer may call existing storage helpers internally.

### 4. Shared run loaders

Create:

- `backend/evidence/loaders/run_loader.py`
- `backend/evidence/loaders/evidence_loader.py`

These should provide thin shared loading helpers so UI, CLI, and Codex-facing adapters do not pull raw SQL or raw storage logic directly.

### 5. Canonical derivation modules

Create:

- `backend/derive/hotspot_ranker.py`
- `backend/derive/run_comparator.py`
- `backend/derive/summary_builder.py`

Requirements:

#### `hotspot_ranker.py`
- accept canonical run evidence
- return top file hotspots
- do not query storage directly

#### `run_comparator.py`
- accept two canonical run evidence objects
- compute:
  - runtime delta
  - trace overhead delta
  - stage deltas
  - file timing deltas
- return canonical derived output only

#### `summary_builder.py`
- build a compact summary object from canonical evidence + canonical derivations
- this is the shared source for:
  - context packs
  - CLI output
  - future UI view models

Do not put presentation formatting here.

### 6. Core evidence writer

Create:

```python
backend/core/evidence_writer.py
```

This should provide a tiny helper that converts current performance-report style output into canonical run evidence records for later storage/export use.

Do not rewrite instrumentation collection yet.
Just create the canonical write path wrapper.

### 7. Core run engine wrapper

Create:

```python
backend/core/run_engine.py
```

This is a small orchestration wrapper around the existing instrumentation/script-runner flow.

It must not reimplement tracing or aggregation.
It should only provide a stable boundary so experiments and adapters do not depend directly on scattered runtime entrypoints.

### 8. Experiment scaffolding

Create:

- `backend/experiments/base.py`
- `backend/experiments/compare_runs.py`
- `backend/experiments/isolate_hotspot.py`

This pass only needs scaffolding plus shared interfaces.

Implement:

- a base experiment shape
- `compare_runs` that uses canonical evidence + comparator
- `isolate_hotspot` as a placeholder interface with TODO-level internals allowed

Do not build a giant experiment system yet.

### 9. Codex adapter context pack bridge

Create:

```python
backend/adapters/codex/context_pack.py
```

This adapter must consume only:

- canonical evidence
- canonical derivations

It must not invent its own hotspot math or quality logic.

It should adapt current context-pack building toward the new evidence/derive layer with minimal behavior regression.

### 10. CLI adapter scaffolding

Create:

```python
backend/adapters/cli/commands.py
```

Provide a small CLI-oriented wrapper that can:

- load run evidence
- print hotspot summary
- compare two runs

This is scaffolding only.
Do not build a full CLI product.

## Existing Code Integration

Reuse existing BlueBench logic where practical:

- instrumentation SQLite storage
- performance report generation
- context pack generation
- current run selection helpers

This pass should extract shared logic, not duplicate it.

If a current surface computes hotspot ranking, delta, or summary logic inline, move that logic behind the new `derive/` modules and switch the caller to use them.

The main goal is to reduce duplicate truth, not to move files for aesthetics.

## Behavior Rules

- Do not change visual layout behavior.
- Do not change run-selection semantics.
- Do not change Inspector UX.
- Do not change Stress Engine UX.
- Do not rewrite the tracer or scanner here.

You may adapt internal callers to use the new evidence/derive modules where it is low risk and directly reduces duplication.

## Tests

Add tests for:

1. `load_run_evidence(run_id)` returns canonical schema shape
2. hotspot ranking is stable from canonical evidence
3. run comparison computes correct deltas
4. summary builder produces compact canonical output
5. Codex context-pack adapter uses canonical derivation output

Use existing test fixtures and current SQLite-backed run data patterns where possible.

Do not require live UI interaction.

## Deliverable

After this pass, BlueBench should have:

- one canonical run evidence shape
- one canonical derivation layer for hotspots, deltas, and summaries
- one adapter path for Codex-facing context
- experiment scaffolding
- reduced risk of semantic drift between surfaces

The system does not need to be fully migrated yet.

The purpose of this pass is to establish the architecture so future work can follow:

measure once → derive once → display many

## Important Constraint

If a result can appear in more than one surface, there must be one canonical computation for it.

If you find hotspot ranking, delta math, or quality logic duplicated in multiple places, the new `derive/` layer must become the canonical home.
