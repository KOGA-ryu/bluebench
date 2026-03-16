# BlueBench New App Triage Design

## Purpose

`New App Triage` is a standalone BlueBench feature for rapidly orienting Codex inside an unfamiliar repository.

Its job is to turn a newly opened project into a compact, evidence-backed briefing:

- what the app appears to be
- how it is structured
- how it runs
- where compute and complexity concentrate
- what the first high-value engineering actions should be

This feature is for fast technical orientation, not final architecture review.

---

## One-Sentence Product Definition

BlueBench Triage should let Codex point at a repo and get a trustworthy first-pass engineering brief that combines static structure, measured runtime signals, and operational risks.

---

## Primary User

Primary user:

- Codex working in CLI on a new or unfamiliar repo

Secondary users:

- human engineers onboarding to a repo
- humans reviewing optimization opportunities
- humans preparing to refactor or stabilize a system

---

## Core Outcome

Given a repo, BlueBench should produce a triage result that answers:

1. What is this system?
2. Where are the entry points?
3. What are the major subsystems?
4. What looks expensive or risky?
5. What did measured runs actually show?
6. What are the first 3-5 actions worth taking?
7. How confident is BlueBench in each conclusion?

---

## Feature Philosophy

Triage is not:

- an AI essay generator
- a dependency graph visualizer
- a replacement for reading code
- a full architecture audit

Triage is:

- a compression system
- a repo orientation tool
- an engineering-first judgment pass
- a way to reduce time-to-useful-context

The output should be dry, structured, and defensible.

---

## Final User Experience

### Trigger

User opens a project and launches:

- `New App Triage`

Possible surfaces:

- main app button
- Stress Engine adjacent tool button
- future CLI command

### Inputs

Required:

- project root

Optional:

- selected completed run
- preferred scenario / target script for a new verification run
- triage depth: `quick` or `full`

### Outputs

Triage should produce a report with these sections:

1. Project Summary
2. Launch and Runtime Context
3. Architecture Snapshot
4. Measured Compute Summary
5. Dependency and Environment Risks
6. Bottleneck Hypotheses
7. Suggested First Actions
8. Confidence and Evidence

---

## Functional Scope

### Phase 1 Scope

The first complete version should include:

- repo scan summary
- entry point detection
- subsystem/folder summary
- dependency summary
- run-aware hotspot summary
- external pressure summary
- failures summary
- bottleneck hypotheses
- top recommended actions
- confidence levels
- export to Markdown and JSON

### Explicit Non-Goals

Do not require in first version:

- autonomous code changes
- AI chat inside the report
- full architectural diagrams
- deep cross-run comparison dashboards
- container orchestration analysis
- advanced language support beyond what BlueBench already scans reliably

---

## Triage Output Shape

The triage result should exist as a structured object first, with rendering second.

Suggested shape:

```python
{
  "project": {
    "name": "...",
    "root": "...",
    "languages": [...],
    "file_count": 0,
    "entry_points": [...],
  },
  "runtime_context": {
    "selected_run_id": "...",
    "selected_run_name": "...",
    "scenario_kind": "...",
    "hardware_profile": "...",
    "previous_comparable_run_id": "...",
  },
  "architecture": {
    "top_level_areas": [...],
    "suspected_subsystems": [...],
    "relationship_hotspots": [...],
    "coupling_notes": [...],
  },
  "compute": {
    "hot_files": [...],
    "hot_functions": [...],
    "external_pressure": [...],
    "failures": [...],
    "regressions": [...],
  },
  "operational_risks": {
    "native_dependencies": [...],
    "launch_assumptions": [...],
    "env_requirements": [...],
    "packaging_risks": [...],
  },
  "hypotheses": [
    {
      "title": "...",
      "reasoning": "...",
      "confidence": "low|medium|high",
      "evidence": [...],
    }
  ],
  "recommended_actions": [
    {
      "priority": 1,
      "title": "...",
      "reason": "...",
      "expected_impact": "...",
      "confidence": "low|medium|high",
    }
  ],
  "evidence": {
    "static_sources": [...],
    "runtime_sources": [...],
  }
}
```

---

## Required Subsystems

To make triage fully functional, BlueBench needs these parts.

### 1. Static Project Summarizer

Purpose:

- describe the repo without executing it

Responsibilities:

- top-level directory summary
- file count / language count
- candidate entry points
- likely app type heuristics
- subsystem grouping
- dependency surface scan

Sources:

- existing project loader
- graph manager tree
- parser/scanner output
- import relationships

Needed additions:

- explicit entry point detection
- top-level dependency summarization
- native binding detection
- config/build file detection

### 2. Runtime Evidence Adapter

Purpose:

- convert run summaries into triage-friendly findings

Responsibilities:

- top hot files
- top hot functions
- external bucket ranking
- failure-heavy files
- regression candidates
- coverage quality indicators

Sources:

- `run_summary`
- `file_summary`
- `function_summary`
- `bb_performance_report.json`

Needed additions:

- one service layer that turns raw summaries into triage sections
- consistent project/run scoping

### 3. Architecture Heuristics Layer

Purpose:

- infer likely subsystem boundaries and risk areas

Responsibilities:

- map top-level folders to subsystem candidates
- detect high-fan-in / high-fan-out files
- identify likely glue layers
- identify areas mixing UI, IO, compute, and orchestration

Inputs:

- graph manager node tree
- relationship index
- file paths
- compute summaries

Needed additions:

- heuristics service
- per-file coupling score
- per-folder hotspot concentration summary

### 4. Recommendation Engine

Purpose:

- turn evidence into first-pass engineering actions

Responsibilities:

- prioritize 3-5 next actions
- distinguish optimization work from architecture work
- avoid generic advice
- attach confidence and evidence

Rules:

- recommendations must point to evidence
- recommendations should be conservative
- recommendations should prefer high-leverage, low-regret actions

Needed additions:

- ruleset for recommendation generation
- confidence scoring model

### 5. Triage Exporter

Purpose:

- save the triage result as durable artifacts

Required outputs:

- `bb_triage_report.json`
- `bb_triage_report.md`

Optional later:

- `.bbtriage` packaged artifact

---

## UX Design

### Standalone Window

Recommended first UI:

- detached Qt window, similar in spirit to Stress Engine

Sections:

1. Triage Controls
2. Project Summary
3. Architecture Snapshot
4. Runtime Evidence
5. Risks
6. Recommended Actions
7. Export

### Controls

Controls should include:

- selected project
- selected run
- run view mode
- triage mode: `quick` / `full`
- `Generate Triage`
- `Export Markdown`
- `Export JSON`

### Readability Rules

- text-first
- no forced graphs
- compact, printable sections
- confidence shown next to claims
- evidence references visible

---

## CLI Design

This feature should eventually exist in CLI form because Codex is a primary user.

Suggested command:

```bash
python -m backend.triage.cli \
  --project-root /path/to/repo \
  --run-id abc123 \
  --mode full
```

CLI output should:

- print a compact summary to terminal
- write JSON and Markdown artifacts

This is high value because it lets Codex use triage without the Qt app.

---

## Report Sections

### 1. Project Summary

Should include:

- repo name
- project root
- approximate app type
- primary languages
- file count
- top-level directories
- candidate entry points

### 2. Launch and Runtime Context

Should include:

- selected run
- scenario kind
- hardware profile
- previous comparable run
- run quality warnings

### 3. Architecture Snapshot

Should include:

- major subsystems
- suspected orchestration layer
- likely data-processing layer
- likely UI layer
- likely integration points
- relationship hotspots

### 4. Measured Compute Summary

Should include:

- hottest files
- hottest functions
- dominant external buckets
- failure-heavy areas
- regression candidates

### 5. Dependency and Environment Risks

Should include:

- native dependencies
- optional runtime-only imports
- likely environment assumptions
- interpreter requirements
- launch fragility

### 6. Bottleneck Hypotheses

Each hypothesis should include:

- title
- explanation
- confidence
- evidence

Example:

- `Python tracing overhead may dominate small workloads`
- confidence `medium`
- evidence:
  - high trace overhead estimate
  - low files seen
  - short instrumented runtime

### 7. Suggested First Actions

These should be concrete.

Example:

- add a non-GUI verification entry point for app startup measurement
- isolate native dependency initialization from core business logic
- instrument one representative background workflow
- review top two hotspot files before broad refactor

---

## Data BlueBench Already Has

BlueBench already has much of the foundation:

- project discovery
- file tree
- graph manager
- deterministic explorer model
- relationship index
- selected run model
- file summaries
- function summaries
- external bucket summaries
- run summary
- performance report

This is why triage is realistic now.

The missing work is not raw data collection.
It is synthesis.

---

## Data Still Needed

To make triage fully functional, BlueBench still needs:

### Entry Point Detection

Detect likely launch points from:

- `app/main.py`
- `__main__.py`
- CLI frameworks
- top-level scripts
- package entry markers
- common Qt/web/server startup files

### Dependency Surface Extraction

Summarize:

- internal vs external imports
- native/system bindings
- high-risk runtime dependencies
- optional imports and guarded imports

### Coupling Heuristics

Need a cheap way to flag:

- high fan-in files
- high fan-out files
- folders with concentrated compute
- files with both orchestration and low-level concerns

### Triage Confidence Model

Need explicit confidence sources:

- static-only inference -> lower confidence
- measured run evidence -> higher confidence
- repeated consistent signals across files/runs -> highest confidence

---

## Suggested Backend Module Layout

```text
backend/triage/
    service.py
    static_summary.py
    runtime_summary.py
    architecture_heuristics.py
    recommendations.py
    exporter.py
    cli.py
```

Responsibilities:

- `service.py`
  - orchestrates full triage pipeline
- `static_summary.py`
  - repo scan, entry points, dependencies, subsystem candidates
- `runtime_summary.py`
  - selected run adaptation, quality warnings, hotspots, regressions
- `architecture_heuristics.py`
  - coupling and subsystem heuristics
- `recommendations.py`
  - action generation and confidence
- `exporter.py`
  - Markdown/JSON output
- `cli.py`
  - terminal access for Codex

---

## Suggested Service API

```python
def generate_triage(
    project_root: Path,
    run_id: str | None = None,
    mode: str = "quick",
) -> dict[str, object]:
    ...

def export_triage_markdown(triage: dict[str, object], target_path: Path) -> Path:
    ...

def export_triage_json(triage: dict[str, object], target_path: Path) -> Path:
    ...
```

---

## Suggested Heuristics

### App Type Guessing

Signals:

- Qt imports -> desktop app
- Flask/FastAPI/Django -> server app
- `argparse`/`click`/`typer` -> CLI app
- heavy file IO plus batch entry points -> processing pipeline

### Bottleneck Hypotheses

Signals:

- high total time concentrated in one file
- one function dominates file time
- high external bucket time
- high exception counts
- high trace overhead relative to runtime
- low measured file coverage

### Risk Hypotheses

Signals:

- native imports at startup
- GUI-only entry point
- no obvious headless entry point
- large top-level folder with mixed concerns
- repeated cross-subsystem imports

---

## Confidence Model

Every recommendation and hypothesis should carry:

- `low`
- `medium`
- `high`

Simple rules:

- high:
  - confirmed by measured run plus static structure
- medium:
  - supported by one measured signal or several static signals
- low:
  - structural guess without runtime confirmation

---

## Export Requirements

### Markdown

Must be readable by humans and LLMs.

Should include:

- concise headings
- explicit bullet lists
- evidence blocks
- confidence labels

### JSON

Must preserve:

- raw findings
- structured recommendations
- evidence references
- run context

---

## What I Need To Make This Fully Functional

These are the concrete missing pieces.

### Required Engineering Work

1. Build a triage service layer that merges static and runtime evidence.
2. Add entry point detection.
3. Add dependency surface extraction and native-dependency detection.
4. Add architecture heuristics for subsystem boundaries and coupling.
5. Add a recommendation ruleset with confidence scoring.
6. Add Markdown/JSON exporters.
7. Add a detached triage window.
8. Add a CLI interface.

### Required Data Access Helpers

Need clean helpers for:

- selected run details
- previous comparable run details
- file hotspot lists
- function hotspot lists
- external pressure by file
- top regressions
- project-level file/folder summaries

### Required UX Decisions

Need final decisions on:

- whether triage defaults to `quick` or `full`
- whether triage auto-runs on project load
- where the launch button lives
- whether export happens automatically
- whether CLI and Qt outputs share the same renderer

---

## Recommended Implementation Order

### Pass 1

- backend triage service
- static summary
- runtime summary
- JSON export

### Pass 2

- Markdown export
- Qt triage window
- project/run selection
- evidence and recommendation rendering

### Pass 3

- CLI mode
- confidence refinement
- better heuristics
- stronger action recommendations

---

## Acceptance Criteria

The feature is successful when:

1. Codex can point BlueBench at a repo and get a useful triage report in under a minute.
2. The report identifies real entry points and major subsystems with reasonable accuracy.
3. If a run is selected, the report explains actual hotspots and regressions.
4. Recommendations are specific, evidence-backed, and non-generic.
5. The output is useful without reading the entire repo first.
6. The report can be exported as Markdown and JSON.

---

## Why This Feature Matters

BlueBench already helps once a user is inside the repo and actively investigating.

Triage would help before that.

It would reduce:

- time to orientation
- time to first good hypothesis
- time wasted chasing non-problems

For Codex specifically, this is high leverage because the first failure mode in new repositories is not code generation.
It is context miscalibration.

Triage is the feature that attacks that directly.
