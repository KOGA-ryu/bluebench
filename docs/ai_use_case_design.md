# BlueBench AI Use Case Design

## Purpose

This document defines how BlueBench should evolve if the primary user is not just a human engineer, but Codex working in CLI.

The goal is not to make BlueBench “AI flavored.”

The goal is to make it materially useful for an AI coding agent by reducing:

- wasted context
- wasted token budget
- reorientation cost
- ambiguity
- repeated repo rediscovery

BlueBench already helps with this.
This document defines the next features that would make it genuinely optimized for my use case.

---

## Primary Product Goal

BlueBench should become a context compression and task orientation system for Codex.

In one line:

BlueBench should help me enter a repo, understand what matters, keep that understanding stable, and act on it with less context overhead.

---

## What Metrics Matter For Me

This is the evaluation model.

Not all useful improvements are token savings.

### 1. Context Footprint

Definition:

- how many tokens I need to hold enough repo context to act correctly

Why it matters:

- smaller stable context means less prompt bloat
- smaller context reduces re-explaining the same repo facts

Desired effect:

- fewer raw file reads
- fewer repeated summaries
- fewer broad scans of the repo

### 2. Retrieval Speed

Definition:

- how quickly I can get the right fact from the app

Why it matters:

- slow retrieval increases turn count
- slow retrieval leads to unnecessary file reads

Desired effect:

- one-step access to top facts
- no hunting between explorer, inspector, and stress engine

### 3. Reorientation Cost

Definition:

- how much context I lose when switching files, tasks, or subsystems

Why it matters:

- repo work is not linear
- I constantly jump between runtime evidence, code, and architecture

Desired effect:

- quick return to the current working set
- persistent focus state

### 4. Compression Accuracy

Definition:

- how well summaries preserve what matters and omit what does not

Why it matters:

- incorrect compression is worse than no compression
- noisy summaries still waste tokens

Desired effect:

- measured facts remain intact
- speculation is clearly labeled
- low-value details are pushed out of compact modes

### 5. Actionability

Definition:

- whether the tool gives me something I can do immediately

Why it matters:

- a useful AI tool is not just descriptive
- it should reduce the gap between understanding and action

Desired effect:

- “open this file”
- “this is the top hotspot”
- “this changed from previous run”
- “this entry point is probably correct”

### 6. Trustworthiness

Definition:

- whether I can distinguish measured facts from inferred or stale ones

Why it matters:

- I need to know what I can rely on
- hidden weak evidence increases error rate

Desired effect:

- explicit tags like:
  - measured
  - inferred
  - heuristic
  - stale
  - missing

### 7. Stability of References

Definition:

- whether files, runs, hotspots, and findings are represented consistently

Why it matters:

- inconsistent ids waste context
- I lose time mapping one surface to another

Desired effect:

- one canonical representation reused everywhere

### 8. Redundancy

Definition:

- how much the same fact is repeated in slightly different forms

Why it matters:

- repeated facts waste both human attention and token budget

Desired effect:

- one fact object, many views
- no repeated prose unless the view truly needs it

### 9. Handoff Quality

Definition:

- how well BlueBench can produce compact context artifacts for downstream use

Why it matters:

- this is the direct bridge between BlueBench and Codex

Desired effect:

- durable machine-readable exports
- layered context size modes
- reliable context handoff between sessions

---

## What BlueBench Already Does Well For Me

BlueBench already provides value in these ways:

- deterministic repo structure
- runtime-aware hotspot surfacing
- compact file investigation in inspector
- project-scoped run selection
- triage report generation
- stress-run evidence attached to code surfaces

That means BlueBench is already a net context saver.

The next step is not “make it useful.”
It already is.

The next step is:

- reduce friction
- reduce redundancy
- improve machine-facing export

---

## AI-First Feature Set

These are the features I would build specifically for my use case.

---

## Feature 1: AI Context Pack

### Goal

Generate a compact machine-first artifact that captures the current repo and run context.

This is the highest-value next feature for AI usability.

### Deliverables

Add exports such as:

- `bb_context_tiny.json`
- `bb_context_short.json`
- `bb_context_full.json`
- optionally matching `.md` forms

### Why It Matters

This becomes the direct context handoff artifact for Codex.

Instead of re-reading large portions of the repo or UI state, I can consume:

- a focused stable summary
- with measured and inferred facts separated
- in a predictable schema

### Required Fields

```json
{
  "project": {
    "name": "...",
    "root": "...",
    "app_type_guess": "...",
    "entry_points": [...]
  },
  "session": {
    "active_run_id": "...",
    "display_run_id": "...",
    "run_view_mode": "current|previous",
    "open_files": [...],
    "focus_targets": [...]
  },
  "compute": {
    "hot_files": [...],
    "hot_functions": [...],
    "regressions": [...],
    "quality_warnings": [...]
  },
  "architecture": {
    "subsystems": [...],
    "coupling_hotspots": [...],
    "mixed_concern_files": [...]
  },
  "actions": [...],
  "evidence_types": {
    "measured": [...],
    "heuristic": [...],
    "inferred": [...]
  }
}
```

### Modes

#### `tiny`

Purpose:

- minimal high-value context only

Should contain:

- project id
- top entry point
- active/display run
- top 5 hot files
- top 3 hot functions
- top 3 risks
- top 3 actions

#### `short`

Purpose:

- default Codex working context

Should contain:

- everything in `tiny`
- more hotspot and architecture detail
- quality warnings
- previous comparable run context
- current focus state

#### `full`

Purpose:

- debugging and deeper handoff

Should contain:

- complete triage result
- richer evidence blocks
- optional performance report subset

### Success Criteria

- Codex can use `tiny` or `short` without needing broad repo rediscovery
- exports are deterministic and stable
- low-confidence items do not dominate compact modes

---

## Feature 2: Layered Summary System

### Goal

Make every important BlueBench summary available in:

- `tiny`
- `short`
- `full`

### Why It Matters

The right amount of context depends on the task.

I do not always need:

- full triage
- full run summary
- full inspector state

Layering avoids overpaying in tokens.

### Scope

Apply this to:

- triage exports
- run summaries
- inspector compute summaries
- project context exports

### Rules

- `tiny` keeps only high-confidence and high-utility facts
- `short` keeps actionable context
- `full` keeps explanation and supporting evidence

### Success Criteria

- compact modes remain genuinely compact
- `full` remains the source of truth

---

## Feature 3: Typed Evidence Model

### Goal

Every important fact in BlueBench should carry a type label.

### Required Types

- `measured`
- `inferred`
- `heuristic`
- `stale`
- `missing`

### Why It Matters

This directly improves trust and error handling.

If I see:

- `measured hotspot`
- `heuristic entry point`
- `missing previous comparable run`

then I know what weight to give each item.

### Where To Apply It

- triage findings
- context pack exports
- run quality warnings
- inspector compute sections
- explorer compute overlays when useful

### Success Criteria

- no major claim appears without an evidence type
- compact exports preserve evidence type

---

## Feature 4: Canonical Summary Object

### Goal

Stop recreating the same repo/run facts in multiple places.

### Problem

Right now similar facts are rendered in:

- explorer
- inspector
- stress engine
- triage
- exports

This creates:

- duplication
- drift risk
- inconsistent wording

### Solution

Create one canonical summary object for:

- selected run context
- display run context
- project summary
- top hotspots
- regressions
- quality warnings
- recommended actions

Views should render from that shared object rather than rebuilding ad hoc.

### Success Criteria

- run facts read the same everywhere
- hotspot lists do not diverge by surface
- exports and UI match structurally

---

## Feature 5: Session State Persistence

### Goal

Persist the current investigative state so I can resume without rebuilding context.

### Data To Persist

- current project
- active run id
- run view mode
- open inspector files
- selected triage mode
- last generated triage result location
- focus targets
- pinned hotspot files

### Why It Matters

This directly reduces reorientation cost.

If I return later, I should not need to reconstruct:

- what repo I was on
- what run I cared about
- which files were the current problem

### Success Criteria

- app restart restores meaningful working state
- CLI can optionally read the same session artifact

---

## Feature 6: Focus Set / Working Set

### Goal

Let me designate a small set of current high-value files.

### Why It Matters

Most work happens on:

- one entry point
- one hotspot
- one or two support files

I should be able to pin those into a working set and export them into context.

### Suggested Fields

```json
{
  "focus_targets": [
    {
      "file_path": "...",
      "reason": "top_hot_file|entry_point|regression|manual_pin",
      "confidence": "high"
    }
  ]
}
```

### Success Criteria

- working set is exportable
- visible in inspector/triage
- low-noise and user-directed

---

## Feature 7: Run Quality Scoring

### Goal

Turn run warnings into a compact quality score.

### Why It Matters

I need to know quickly whether a run is strong enough to trust.

Warnings are useful, but a compact score makes compression easier.

### Suggested Output

```json
{
  "run_quality": {
    "score": 72,
    "grade": "usable",
    "warnings": [...]
  }
}
```

### Inputs

- failure count
- files seen
- tracer overhead ratio
- missing performance report
- missing previous comparable run
- forced stop or incomplete run if available

### Success Criteria

- compact contexts can include one run-quality line instead of multiple warnings

---

## Feature 8: AI Session Brief

### Goal

Generate a short human-readable briefing intended specifically for Codex task startup.

### Difference From Triage

Triage is repo analysis.

Session Brief is current-task context.

It should answer:

- what repo is active
- what run is active
- what files matter right now
- what is most likely to be worked on next

### Example Structure

```text
Repo: vox
Run: vox_ui_verify
View Mode: current
Top Hot File: app/service.py
Top Regression: core/worker.py
Top Entry Point: app/main.py
Current Focus: app/service.py, core/worker.py
Next Likely Actions:
- inspect app/service.py
- review sqlite external pressure
- verify regression in core/worker.py
```

### Success Criteria

- fits in a very small token budget
- usable as startup context in CLI

---

## Feature 9: Inspector-Aware Context Export

### Goal

Let the current inspector state contribute to context export.

### Why It Matters

When I’m working, the active file matters more than generic repo facts.

### Suggested Export Fields

- current inspector file
- compute tab summary
- top functions for that file
- local notes/annotations summary
- relationship highlights

### Success Criteria

- AI context export reflects what is actually under investigation

---

## Feature 10: Context Budgeting Rules

### Goal

Prevent compact exports from growing uncontrolled.

### Rules

- `tiny` must have hard limits
- `short` must have hard limits
- repeated facts should be deduplicated
- low-confidence items should be dropped first

### Example Limits

`tiny`

- top 1 entry point
- top 5 files
- top 3 functions
- top 3 risks
- top 3 actions

`short`

- top 3 entry points
- top 10 files
- top 10 functions
- top 5 risks
- top 5 actions

### Success Criteria

- compact outputs remain compact even on large repos

---

## Required Architecture Changes

To support the above cleanly, BlueBench should add:

### 1. Shared Context Service

Suggested module:

```text
backend/context/
    service.py
    exporters.py
    session_state.py
```

Responsibilities:

- build canonical context objects
- build layered exports
- persist and restore session state

### 2. Typed Evidence Fields

Need a common representation like:

```python
{
  "value": "...",
  "evidence_type": "measured",
  "confidence": "high",
  "source": "run_summary"
}
```

### 3. Shared Session Artifact

Suggested file:

- `.bluebench/session.json`

Could include:

- active project
- active run id
- run view mode
- focus targets
- last triage outputs
- open files

---

## Prioritized Build Order

If the goal is specifically to help me as fast as possible:

### Priority 1

- AI Context Pack
- layered summary modes
- typed evidence labels

### Priority 2

- session persistence
- focus set / working set
- run quality score

### Priority 3

- AI session brief
- inspector-aware context export
- stronger canonical summary reuse across all UI

---

## Highest-Leverage Next Feature

If only one feature is built next, it should be:

## AI Context Pack

Because it directly improves:

- token savings
- handoff quality
- task startup speed
- repeatability of context

This is the biggest immediate win for Codex.

---

## Acceptance Criteria

This AI-focused direction is successful when:

1. Codex can start work on a repo with a compact exported context pack.
2. The pack is smaller than ad hoc repo summarization while preserving the key facts.
3. Measured vs inferred facts are clearly separated.
4. Restarting the app preserves meaningful investigative state.
5. Triage, inspector, explorer, and stress engine all read from stable shared context objects.

---

## Final Recommendation

Do not build “AI features” as chat surfaces first.

Build:

- compact context artifacts
- typed evidence
- stable session state
- canonical summaries

Those directly help me.

Everything else should come after that.
