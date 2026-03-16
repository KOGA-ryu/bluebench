# BlueBench UI Layout Tasks

This document turns the UI critique into implementation work.

Scope:

- `Explorer`
- `Stress Engine`

Out of scope:

- `Inspector`
- layout engine redesign
- Docker orchestration
- AI features
- multi-run comparison UI

---

## Priority Order

1. Explorer compact vs expanded body modes
2. Explorer active run badge
3. Stress Engine run context strip
4. Stress Engine validation emphasis pass
5. Stress Engine state emphasis pass
6. Explorer lane/background treatment
7. Stress Engine section editor guidance text
8. Hot-files readability cleanup

---

## Task 1: Explorer Compact vs Expanded Body Modes

### Goal

Make collapsed and expanded node states meaningfully different.

### Problem

Current explorer cards technically work, but collapsed nodes still feel too verbose and expanded nodes do not earn enough extra clarity.

### Requirements

- collapsed cards show compact compute-first content
- expanded cards show full metadata labels
- metadata toggle remains bottom-right
- no layout changes
- no interaction model changes

### Collapsed card target

Show:

- tier
- score
- delta if available
- type

Hide:

- long metadata labels
- verbose path copy where possible
- relationship details beyond a very short summary

### Expanded card target

Show:

- tier
- score
- tally
- delta
- path
- relationship counts
- shallow external summary

### Acceptance criteria

- collapsed and expanded cards are visually distinct
- compact cards are faster to scan than current cards
- expanded cards remain readable at current node size
- no node interaction behavior changes

---

## Task 2: Explorer Active Run Badge

### Goal

Make the selected run visible directly above the explorer canvas.

### Problem

Compute is selected-run-specific, but the explorer surface does not clearly remind the user which run they are viewing.

### Requirements

- add a compact badge or strip above the explorer area
- show:
  - active run name
  - scenario kind if available
  - hardware profile if space allows
- if no run is selected, show a neutral empty state

### Example

```text
Active Run: vox_ui_verify
mini_pc_n100_16gb · custom_script
```

### Acceptance criteria

- user can tell which run powers current explorer compute without opening Stress Engine
- no extra dialogs or complex selection UI added

---

## Task 3: Stress Engine Run Context Strip

### Goal

Expose run identity and execution context at the top of the Stress Engine window.

### Problem

Interpreter, project root, and run identity are currently buried in the metadata block.

### Requirements

- add a compact context strip near the top bar
- display:
  - run name
  - project root
  - interpreter path
- text should truncate cleanly

### Acceptance criteria

- user can confirm target interpreter and project root before and during a run
- no need to inspect deep metadata just to validate launch context

---

## Task 4: Stress Engine Validation Emphasis Pass

### Goal

Make validation status feel important without cluttering the editors.

### Problem

Validation already blocks invalid runs, but the current panel does not visually reflect its authority.

### Requirements

- keep the compact validation panel
- strengthen invalid-state styling
- include error count in the validation title or leading line
- preserve section-level error markers

### Acceptance criteria

- invalid specs are visually obvious before `Start Run`
- valid specs feel clearly ready without adding noisy inline form errors

---

## Task 5: Stress Engine State Emphasis Pass

### Goal

Adjust layout emphasis based on run state.

### Problem

Idle, running, and completed states currently share nearly the same visual weight.

### Requirements

- idle:
  - editors visually primary
- running:
  - live output visually primary
- completed:
  - summary visually primary

### Constraints

- no animation requirement
- no pane manager redesign
- keep the current vertical stack model

### Acceptance criteria

- visual emphasis changes with run state
- users can tell at a glance whether the window is in authoring, monitoring, or review mode

---

## Task 6: Explorer Lane / Background Treatment

### Goal

Improve explorer readability without changing node coordinates.

### Problem

The deterministic layout works, but expansion columns visually blend together.

### Requirements

- add subtle column or lane treatment
- do not alter positions from the layout engine
- do not add graph edges

### Possible treatments

- faint alternating column bands
- subtle top gutter labels
- slightly stronger root-column separation

### Acceptance criteria

- users can distinguish major column regions more easily
- the change remains purely presentational

---

## Task 7: Stress Engine Section Editor Guidance

### Goal

Make section editors feel structured without abandoning text-based editing.

### Problem

The five section editors work, but all of them currently feel like generic text areas.

### Requirements

- add a short subtitle or hint above each section editor
- keep editors plain-text
- do not replace with dynamic forms

### Suggested subtitles

- `Run`: run identity and execution context
- `Hardware`: profile and overrides
- `Scenario`: target workload
- `Dashboard`: live output priorities
- `Save / Export`: artifact settings

### Acceptance criteria

- new users can understand the purpose of each section faster
- editing remains lightweight and copy/paste friendly

---

## Task 8: Hot-Files Readability Cleanup

### Goal

Make the live hot-files list faster to scan.

### Problem

The panel is correct but visually flat.

### Requirements

- preserve text-first presentation
- improve ranking legibility
- keep density

### Implementation direction

- add an explicit rank column
- slightly emphasize file name
- slightly de-emphasize numeric columns

### Acceptance criteria

- top hot files are easier to scan during active runs
- no charts or heavy visual components added

---

## Suggested Execution Plan

### Pass 1

- Task 1
- Task 2
- Task 3

Reason:

These give the strongest immediate improvement to app coherence.

### Pass 2

- Task 4
- Task 5
- Task 8

Reason:

These improve operational clarity in the Stress Engine.

### Pass 3

- Task 6
- Task 7

Reason:

These are useful refinements, but less urgent than state clarity and run-context trust.

---

## Definition of Done

This UI refinement phase is done when:

- explorer cards are compute-first and easy to scan
- active run context is visible in the main app
- Stress Engine clearly communicates what is being run and in what state
- validation feels authoritative
- summary and hot-file outputs are easier to read
- no interaction regressions are introduced

---

## Non-Goals

Do not do these during this pass:

- redesign the layout engine
- redesign the inspector
- add charts
- add dependency graphs
- add comparison dashboards
- add AI recommendations
- add animation-heavy transitions

This should stay a refinement phase, not a new subsystem phase.
