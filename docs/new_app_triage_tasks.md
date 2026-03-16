# BlueBench New App Triage Tasks

This document turns the triage design into buildable work.

Primary reference:

- [new_app_triage_design.md](/Users/kogaryu/dev/bluebench/docs/new_app_triage_design.md)

Goal:

- implement a standalone triage feature that helps Codex orient in a new repo quickly and defensibly

Out of scope:

- AI advice generation
- Docker orchestration
- full architecture graph visualization
- autonomous code modification
- deep comparison dashboards

---

## Build Strategy

Build triage in four passes:

1. backend foundation
2. report generation
3. UI surface
4. CLI surface

Do not start with UI.
The value depends on the backend producing structured, trustworthy triage data first.

---

## Pass 1: Backend Foundation

### Task 1.1: Create triage module skeleton

Create:

```text
backend/triage/
    __init__.py
    service.py
    static_summary.py
    runtime_summary.py
    architecture_heuristics.py
    recommendations.py
    exporter.py
```

Requirements:

- modules import cleanly
- no UI dependencies
- service layer owns orchestration

Acceptance:

- `python3 -m compileall backend/triage`

---

### Task 1.2: Implement triage service entry point

Add:

```python
def generate_triage(project_root: Path, run_id: str | None = None, mode: str = "quick") -> dict[str, object]:
    ...
```

Requirements:

- validates inputs
- orchestrates static summary, runtime summary, heuristics, recommendations
- returns structured dict

Acceptance:

- unit test covers empty/no-run and run-aware calls

---

### Task 1.3: Static project summary

Implement in `static_summary.py`:

- project name
- root path
- language summary
- file count
- top-level directories
- candidate entry points
- probable app type

Sources:

- existing project loader
- file paths
- scanner output where available

Acceptance:

- known repo like `vox` yields at least one plausible entry point
- project summary returns deterministic results

---

### Task 1.4: Entry point detection heuristics

Add detection for:

- `app/main.py`
- `__main__.py`
- CLI entry scripts
- common Qt startup files
- common server startup files

Requirements:

- evidence-based
- score candidates
- return ordered list

Acceptance:

- result includes candidate path and reason

---

### Task 1.5: Runtime summary adapter

Implement in `runtime_summary.py`:

- selected run context
- previous comparable run context
- hottest files
- hottest functions
- external pressure
- failures
- regressions
- run quality warnings

Sources:

- `InstrumentationStorage`
- `bb_performance_report.json`

Acceptance:

- returns empty-but-valid structure when no run is selected
- returns populated structure for a completed run

---

### Task 1.6: Architecture heuristics

Implement in `architecture_heuristics.py`:

- top-level area summary
- subsystem candidates
- relationship hotspots
- coupling notes

Minimum heuristics:

- high fan-in file candidates
- high fan-out file candidates
- folder hotspot concentration
- mixed-concern file detection

Acceptance:

- outputs structured findings with evidence lines
- does not require a completed run

---

### Task 1.7: Recommendation generation

Implement in `recommendations.py`:

- top 3-5 actions
- evidence-backed
- confidence-labelled

Rules:

- recommendations must cite signals
- avoid generic “optimize code” language
- prioritize low-regret next steps

Acceptance:

- recommendations differ when run-aware evidence exists
- every recommendation includes confidence and reason

---

## Pass 2: Report Generation

### Task 2.1: JSON exporter

Implement:

```python
def export_triage_json(triage: dict[str, object], target_path: Path) -> Path:
    ...
```

Requirements:

- pretty printed
- deterministic ordering where practical
- preserves all structured fields

Acceptance:

- exported file re-loads as valid JSON

---

### Task 2.2: Markdown exporter

Implement:

```python
def export_triage_markdown(triage: dict[str, object], target_path: Path) -> Path:
    ...
```

Requirements:

- text-first
- readable by humans and LLMs
- includes evidence and confidence labels

Sections:

- Project Summary
- Runtime Context
- Architecture Snapshot
- Measured Compute Summary
- Dependency and Environment Risks
- Bottleneck Hypotheses
- Suggested First Actions

Acceptance:

- generated markdown is readable without JSON
- includes all major sections even when data is sparse

---

### Task 2.3: Artifact naming

Choose and implement default names:

- `bb_triage_report.json`
- `bb_triage_report.md`

Default location:

- project root

Acceptance:

- exports land in predictable paths

---

## Pass 3: Qt UI Surface

### Task 3.1: Create detached triage window

Create:

- `backend/triage_window.py`

Requirements:

- detached Qt window
- lightweight vertical layout
- no pane-manager complexity

Core sections:

- controls
- summary
- architecture
- runtime evidence
- risks
- recommendations
- export actions

Acceptance:

- window opens from main app
- does not block main workflow

---

### Task 3.2: Add launch point in main app

Add:

- `New App Triage` button in the main app

Requirements:

- uses current project
- optional current active run
- opens detached triage window

Acceptance:

- from a loaded project, triage can be generated without manual path entry

---

### Task 3.3: Add controls

Controls should include:

- project root display
- selected run selector
- mode selector: `quick` / `full`
- `Generate Triage`
- `Export Markdown`
- `Export JSON`

Acceptance:

- user can generate triage with and without a selected run

---

### Task 3.4: Display evidence sections

Show:

- project summary
- architecture snapshot
- compute summary
- risks
- recommendations

Requirements:

- text-first
- confidence visible
- evidence visible

Acceptance:

- a user can scan the whole triage without opening more dialogs

---

## Pass 4: CLI Surface

### Task 4.1: Add CLI entry point

Create:

- `backend/triage/cli.py`

Usage:

```bash
python -m backend.triage.cli --project-root /path/to/repo --run-id abc123 --mode full
```

Requirements:

- prints concise summary
- writes JSON and Markdown artifacts

Acceptance:

- CLI works without Qt
- useful to Codex inside terminal

---

### Task 4.2: Add compact terminal summary

Print:

- project
- app type guess
- entry points
- hot files
- top risks
- top actions

Acceptance:

- terminal output is useful even before opening artifacts

---

## Cross-Cutting Tasks

### Task C.1: Confidence model

Every hypothesis and recommendation must include:

- `low`
- `medium`
- `high`

Rules:

- measured + static evidence -> high
- single signal -> medium
- structure-only guess -> low

Acceptance:

- no unlabeled conclusions

---

### Task C.2: Evidence references

Each major claim should cite:

- source file/path
- run source
- metric source
- heuristic source

Acceptance:

- claims are traceable

---

### Task C.3: Tests

Add:

- `tests/test_triage_service.py`
- `tests/test_triage_exporter.py`
- `tests/test_triage_heuristics.py`

Should cover:

- no-run triage
- run-aware triage
- entry point detection
- exporter output
- recommendation confidence

Acceptance:

- triage backend is testable without Qt

---

## Suggested File Ownership

### Backend

- `backend/triage/service.py`
- `backend/triage/static_summary.py`
- `backend/triage/runtime_summary.py`
- `backend/triage/architecture_heuristics.py`
- `backend/triage/recommendations.py`
- `backend/triage/exporter.py`
- `backend/triage/cli.py`
- `backend/triage_window.py`

### Main App Integration

- `backend/main.py`

### Tests

- `tests/test_triage_service.py`
- `tests/test_triage_exporter.py`
- `tests/test_triage_heuristics.py`

---

## Acceptance Checklist

The feature is ready when all are true:

- triage backend generates a structured result for a loaded project
- triage works with no run selected
- triage becomes richer when a run is selected
- recommendations are evidence-backed and confidence-labelled
- JSON export works
- Markdown export works
- detached Qt triage window works
- CLI triage works
- results are useful on a real repo like `vox`

---

## Real-Repo Verification Plan

Use `vox` or another real project.

Verify:

1. Project summary is plausible
2. Entry point detection finds the expected launch file
3. Runtime-aware triage reflects selected run hotspots
4. Recommendations are not generic
5. Markdown export reads cleanly
6. CLI and Qt outputs agree on core findings

---

## Recommended Execution Order

Do this in order:

1. Pass 1 backend foundation
2. Pass 2 exporters
3. run on a real repo in terminal first
4. Pass 3 Qt window
5. Pass 4 CLI polish

Do not start with the detached window.
If the triage data model is weak, the window will only hide the problem.

---

## First Milestone Definition

Triage reaches first useful milestone when:

- backend service works
- Markdown and JSON export work
- a real repo triage report can be generated from terminal
- report contains useful entry points, hotspots, risks, and first actions

That is enough to prove value before UI polish.
