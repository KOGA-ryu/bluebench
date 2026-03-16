# BlueBench Inspector Layout Tasks

This document turns the Inspector critique into implementation work.

Scope:

- `NodeInspectorWindow`

Out of scope:

- Explorer redesign
- Stress Engine redesign
- code viewer behavior changes
- relationship graph visualization
- charts and heavy compute dashboards

---

## Priority Order

1. Add active run context to the Inspector header
2. Strengthen compute summary hierarchy in Metadata
3. Improve function ranking row formatting
4. Integrate outline more cleanly into Code tab header flow
5. Improve deep relationship scanability

---

## Task 1: Add Active Run Context To Header

### Goal

Make it obvious which run powers current compute values.

### Problem

Compute in the Inspector is selected-run-specific, but the current header does not surface that strongly enough.

### Requirements

- show active run name in the header when available
- optionally show scenario and hardware profile
- remain compact and text-first

### Acceptance criteria

- a user can identify the current compute context without leaving the Inspector
- no extra tabs or dialogs are introduced

---

## Task 2: Strengthen Compute Summary Hierarchy

### Goal

Make compute feel like the primary analytical payload in Metadata.

### Problem

The current compute section is correct, but too visually flat relative to the rest of Metadata.

### Requirements

- make score/time more prominent than support lines
- keep text-first presentation
- avoid charts

### Acceptance criteria

- users can identify the important compute numbers in a few seconds
- support information remains available but secondary

---

## Task 3: Improve Function Ranking Row Formatting

### Goal

Make the function ranking list easier to scan.

### Problem

Each function block contains the right information, but the rows read too similarly.

### Requirements

- strengthen function name hierarchy
- separate performance line from failure line
- keep content dense

### Acceptance criteria

- hottest functions can be scanned quickly
- no information is lost

---

## Task 4: Integrate Outline More Cleanly

### Goal

Make the outline selector feel like part of the Code tab header flow.

### Problem

The selector works but still feels like a utility dropdown placed above the code view.

### Requirements

- add a light heading or contextual wrapper
- preserve current behavior

### Acceptance criteria

- the Code tab reads more like a structured document view

---

## Task 5: Improve Deep Relationship Scanability

### Goal

Preserve the current text tree model while making deep structures easier to read.

### Problem

Recursive relationship trees become visually noisy at depth.

### Requirements

- keep text-first relationship rendering
- improve hierarchy cues
- do not replace with a graph

### Acceptance criteria

- deeper relationship trees remain readable without changing the underlying model

---

## Suggested Execution Plan

### Pass 1

- Task 1
- Task 2
- Task 3

### Pass 2

- Task 4
- Task 5

---

## Non-Goals

Do not do these in this refinement phase:

- add charts
- add dependency graphs
- redesign the fixed-size window model
- turn Metadata into a dashboard
- replace the Code tab with a custom code browser

The Inspector should remain compact, dry, and reference-like.
