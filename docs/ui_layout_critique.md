# BlueBench UI Layout Critique

This document critiques the current BlueBench UI layout with a narrow scope:

- `Explorer`
- `Stress Engine`

`Inspector` is intentionally excluded from redesign recommendations for now. Its current structure is coherent, information-dense, and already aligned with the product's reference-manual style.

## Summary

The current UI is functional, but the layout hierarchy is still uneven.

Main issues:

- the Explorer spends too much space on chrome and not enough on readable node state
- the Explorer cards still feel like transport shells rather than purpose-built compute surfaces
- the Stress Engine mixes spec editing and run observation in one vertical stack, which works mechanically but is visually heavy and cognitively noisy
- run context exists, but the app does not yet make the selected run feel central enough

The app is now usable. The next UI work should be refinement, not a redesign.

---

## Explorer Critique

### 1. The card body hierarchy is still weak

Current behavior:

- file/folder name is strong
- buttons are visible
- compute exists
- metadata exists
- but the eye does not immediately know what the most important non-header content is

Why it matters:

- the Explorer is now compute-aware
- if compute is the point, the node body needs a clearer primary visual layer
- right now the cards still read as "header + leftover content" more than "measured file state"

Recommendation:

- keep the header compact
- make the first body row the primary compute row
- visually separate:
  - tier
  - score
  - delta
- demote path and relationship summary below that

Suggested body structure:

```text
[header]

Tier 9      Score 84      +12
file / folder type

path
small relationship summary

                [i]
```

Implementation direction:

- increase contrast and font weight for the first compute row
- make `delta` visible on collapsed nodes when available
- reduce repeated labels like `Compute Tier:` and `Compute Score:` in collapsed-card mode
- use label-free compact tokens in body preview, and reserve full labels for expanded metadata

---

### 2. Collapsed vs expanded state is still not visually distinct enough

Current behavior:

- collapsed cards now show body content again
- metadata toggle works
- but expanded cards do not feel substantially different from collapsed cards

Why it matters:

- expansion should earn space
- if expanded metadata feels too similar, users stop using the state change as a tool

Recommendation:

- collapsed card:
  - show compact compute summary only
  - hide verbose metadata labels
- expanded card:
  - show full metadata labels
  - show external summary
  - show delta and relationship counts with more spacing

Implementation direction:

- introduce separate render modes in the node body:
  - `compact`
  - `expanded`
- do not rely only on CSS hiding
- generate different DOM fragments for the two states

---

### 3. The bottom-right metadata button is correct, but still visually secondary

Current behavior:

- the button now exists and is placed correctly
- it works
- but it still reads as an accessory, not an explicit third control

Why it matters:

- your node interaction model is strict and button-driven
- if the third button does not visually read as a peer to the top controls, discoverability drops

Recommendation:

- keep it in the bottom-right corner
- give it a stronger bounding treatment
- use explicit icon-state changes

Suggested states:

- collapsed metadata: `i`
- expanded metadata: `×` or `–`

Implementation direction:

- add a slightly darker button background plate or inset area in the lower-right
- make the metadata toggle the only element anchored to that lower-right corner
- avoid letting it visually blend into metadata content

---

### 4. Root column and expansion columns are correct structurally, but the viewport composition is cramped

Current behavior:

- frozen left column works
- scrolling works
- deterministic layout works

Weakness:

- the explorer viewport lacks enough spacing logic between global chrome and graph content
- cards begin too close to the frozen boundary and to each other visually

Recommendation:

- preserve deterministic coordinates
- add a stronger visual lane structure

Implementation direction:

- give each expansion column a faint lane background or banding
- slightly increase horizontal breathing room around column starts without changing layout math drastically
- add a subtle top gutter label treatment for:
  - parent column
  - expansion field

This should remain purely presentational. Do not move layout responsibility into the renderer.

---

### 5. Explorer metadata is informative but text-heavy for a graph surface

Current behavior:

- metadata includes type, score, tally, path, relationships
- this is good for correctness
- but the card body is still verbose relative to the available space

Recommendation:

- compress metadata language
- keep full wording only in Inspector

Example:

Instead of:

```text
Compute Tier: 9
Compute Score: 84.0
Compute Tally: 84.0
```

Use compact card mode:

```text
T9   S84   +12
```

Use expanded metadata mode:

```text
Tier: 9
Score: 84.0
Delta: +12.0
```

This better respects the Explorer's role as a glanceable overview.

---

### 6. The run context is not visually represented strongly enough in the Explorer area

Current behavior:

- the active run selector exists in the main window
- compute changes with the selected run

Weakness:

- the explorer canvas itself does not remind the user which run is active

Why it matters:

- compute is now selected-run-specific
- the user can forget what they are looking at

Recommendation:

- display a compact active run badge above the explorer canvas

Suggested content:

```text
Active Run: vox_ui_verify
```

Optional second line:

```text
mini_pc_n100_16gb · compute_heavy
```

This is small, but it materially improves trust.

---

## Stress Engine Critique

### 1. The editor stack and live output stack compete too hard for attention

Current behavior:

- editors are on top
- validation below
- live output below
- editor collapse works

Weakness:

- the window feels like two full applications stacked vertically
- both regions demand attention even when only one matters

Why it matters:

- before launch, editing should dominate
- during a run, observation should dominate
- after completion, summary should dominate

Recommendation:

- keep the same architecture
- change emphasis by run state

Implementation direction:

- idle state:
  - editor area visually primary
  - live output visually quieter
- running state:
  - live output gets stronger border/title emphasis
  - editor area dims slightly but remains available
- completed state:
  - summary section becomes the strongest visual block

No pane manager is needed. This is a state styling problem.

---

### 2. The section editors are structurally sound but visually too generic

Current behavior:

- sections are correct
- text editors are functional
- validation is clear

Weakness:

- each section editor looks like the same plain text box
- the system has structure, but the layout does not communicate it

Recommendation:

- keep text editors
- make section identity stronger

Implementation direction:

- give each section a short descriptive subtitle above the editor
- example:
  - `Run`: naming and execution context
  - `Hardware`: baseline profile and overrides
  - `Scenario`: workload target
  - `Dashboard`: live output priorities
  - `Save / Export`: artifact settings

- add a one-line hint block instead of placeholder-heavy editors

This keeps the UI lightweight while reducing mental switching cost.

---

### 3. Validation is correct but visually underpowered relative to its importance

Current behavior:

- validation blocks run start
- errors appear in a compact panel

Weakness:

- the validation panel does not feel like the gatekeeper it actually is

Recommendation:

- preserve compactness
- improve severity signaling

Implementation direction:

- idle valid state:
  - muted border
  - short success text
- invalid state:
  - stronger border color
  - error count in title
  - section-level markers remain

Suggested title change:

```text
Validation
```

to

```text
Validation (3 errors)
```

This avoids adding heavy inline form decorations while making the block harder to miss.

---

### 4. The top bar is missing one critical affordance: explicit run context summary

Current behavior:

- open/save controls exist
- editor toggle exists

Weakness:

- once a run starts, the user has to look into the metadata block to remember what is running

Recommendation:

- add a compact run context strip near the top bar

Suggested content:

```text
vox_ui_verify · /Users/kogaryu/dev/vox · /Users/kogaryu/dev/vox/.venv/bin/python
```

This should truncate cleanly.

Why:

- interpreter choice now matters
- project root now matters
- run identity now matters

These should not be buried in the scrollable body.

---

### 5. The live hot-files panel is useful but too table-like for the available space

Current behavior:

- it shows useful numbers
- it is honest

Weakness:

- during a run, the list does not visually foreground movement

Recommendation:

- keep text-first layout
- add stronger ranking emphasis

Implementation direction:

- rank number column
- slightly larger file name
- lighter emphasis on raw numbers
- keep it dense

Example row:

```text
1  parser.py              84   4812 ms   18321
```

This is still textual, but easier to scan.

---

### 6. The summary area is present, but the transition from live state to completed state is not strong enough

Current behavior:

- run finishes
- summary updates

Weakness:

- the window does not produce a strong visual "this run is now complete" moment

Recommendation:

- preserve no-animation policy
- use layout emphasis instead

Implementation direction:

- when status becomes `completed`:
  - strengthen summary border/title
  - reduce event log contrast slightly
  - surface performance report block near the top of summary

This makes end-of-run interpretation faster.

---

### 7. The debug drawer is correct, but should stay intentionally ugly and secondary

Current behavior:

- useful for truth-checking
- not intended as primary UX

Recommendation:

- do not beautify it too much
- keep it collapsed
- keep it diagnostic

Implementation direction:

- simple monospace
- strong separation from summary
- no attempt to make it feel like a polished dashboard

This is one area where plainness improves trust.

---

## Concrete Layout Recommendations

These are the highest-value UI layout fixes, in order.

### Explorer

1. Introduce separate compact and expanded body render modes.
2. Make tier / score / delta the primary collapsed-body content.
3. Add an active-run badge above the explorer canvas.
4. Compress card metadata language.
5. Add subtle lane/background treatment for expansion columns.

### Stress Engine

1. Improve visual state emphasis for idle vs running vs completed.
2. Add a top-level run context strip.
3. Strengthen validation panel status signaling.
4. Add short descriptive subtitles for each section editor.
5. Improve hot-files scanability without making it chart-heavy.

---

## What Should Not Change Yet

These parts are currently correct enough and should not be churned:

- deterministic explorer layout model
- strict button-driven node interaction
- detached Stress Engine window model
- text-editor-based run spec workflow
- Inspector structure and tab model
- text-first relationships presentation

The next UI work should sharpen presentation, not change interaction philosophy.

---

## Suggested Next Pass

If this critique is turned into implementation work, the best sequence is:

1. Explorer compact vs expanded body redesign
2. active run badge in the main window
3. Stress Engine run context strip
4. Stress Engine validation and completion emphasis pass
5. hot-files and summary typography cleanup

That sequence improves clarity without destabilizing the underlying system.
