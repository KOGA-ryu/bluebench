# BlueBench AI Use Case Tasks

This document turns the AI use case design into concrete implementation work.

Primary reference:

- [ai_use_case_design.md](/Users/kogaryu/dev/bluebench/docs/ai_use_case_design.md)

Goal:

- optimize BlueBench for Codex working in CLI

Non-goals:

- generic AI chat features
- vague “assistant mode”
- ornamental dashboards

---

## Build Order

Build in this order:

1. AI Context Pack
2. Layered summaries
3. Typed evidence model
4. Session persistence
5. Focus set / working set
6. Run quality scoring
7. AI session brief
8. Inspector-aware context export

Do not start with broad UI changes.
The highest leverage is export quality and state continuity.

---

## Pass 1: AI Context Pack

### Task 1.1: Create context package modules

Create:

```text
backend/context/
    __init__.py
    service.py
    exporters.py
```

Acceptance:

- imports cleanly
- no Qt dependencies

### Task 1.2: Build canonical context object

Implement:

```python
def build_context_pack(
    project_root: Path,
    active_run_id: str | None,
    run_view_mode: str,
    mode: str = "short",
) -> dict[str, object]:
    ...
```

Must include:

- project summary
- active/display run context
- top hotspots
- top risks
- top actions
- current focus targets if any

Acceptance:

- `tiny`, `short`, `full` all work
- output is deterministic

### Task 1.3: Export context pack

Add:

- `bb_context_tiny.json`
- `bb_context_short.json`
- `bb_context_full.json`
- optional matching `.md`

Acceptance:

- export files are created successfully
- compact modes remain small

---

## Pass 2: Layered Summary System

### Task 2.1: Define summary budgets

Set hard limits for:

- top entry points
- top files
- top functions
- top risks
- top actions

Acceptance:

- `tiny` and `short` cannot grow without bound

### Task 2.2: Apply layering to triage

Use the same size model in:

- triage exports
- context pack

Acceptance:

- compact triage output is materially smaller than full

---

## Pass 3: Typed Evidence Model

### Task 3.1: Add evidence typing schema

Common fields:

- `evidence_type`
- `confidence`
- `source`

Allowed evidence types:

- `measured`
- `inferred`
- `heuristic`
- `stale`
- `missing`

Acceptance:

- every major finding includes an evidence type

### Task 3.2: Apply evidence typing to exports

Start with:

- triage findings
- context pack findings
- run quality warnings

Acceptance:

- compact exports preserve evidence typing

---

## Pass 4: Session Persistence

### Task 4.1: Add session artifact

Suggested file:

- `.bluebench/session.json`

Persist:

- active project
- active run id
- run view mode
- open inspector files
- focus targets
- last triage mode

Acceptance:

- restart restores useful state

### Task 4.2: Read session artifact into context pack

Acceptance:

- context export reflects current working session

---

## Pass 5: Focus Set / Working Set

### Task 5.1: Define focus target model

Suggested fields:

- `file_path`
- `reason`
- `confidence`

### Task 5.2: Add pinning flow

Allow pinning from:

- triage
- inspector
- hot files

Acceptance:

- focus set is exportable
- session persistence restores it

---

## Pass 6: Run Quality Scoring

### Task 6.1: Build quality scoring helper

Inputs:

- failure count
- files seen
- tracer overhead ratio
- missing report
- missing previous comparable run

Outputs:

- score
- grade
- warnings

Acceptance:

- quality summary can replace verbose warnings in compact mode

---

## Pass 7: AI Session Brief

### Task 7.1: Add very small text briefing export

Possible files:

- `bb_session_brief.md`
- `bb_session_brief.txt`

Should include:

- project
- run
- top hotspot
- top regression
- top entry point
- current focus
- next actions

Acceptance:

- usable as startup context in CLI

---

## Pass 8: Inspector-Aware Context Export

### Task 8.1: Add inspector context hook

Include:

- active inspector file
- compute summary
- top functions in that file
- relationship highlights

Acceptance:

- context export reflects the actual file under investigation

---

## Suggested Module Layout

```text
backend/context/
    __init__.py
    service.py
    exporters.py
    session_state.py
    quality.py
```

---

## Tests

Add:

- `tests/test_context_pack.py`
- `tests/test_session_state.py`
- `tests/test_run_quality.py`

Cover:

- compact/full export correctness
- typed evidence presence
- session restore
- context budgeting

---

## Acceptance Checklist

The AI-focused pass is successful when:

- BlueBench can export compact machine-first context
- compact exports stay small
- evidence types are explicit
- session state restores working context
- current focus can be exported
- run quality is summarized compactly

---

## Recommended Immediate Next Step

Build Pass 1 first:

- AI Context Pack

That gives the largest direct benefit to Codex for the least UI churn.
