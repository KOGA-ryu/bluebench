# BlueBench Inspector Layout Critique

This document critiques the current `NodeInspectorWindow` layout.

The goal is not to push immediate redesign. The current Inspector is already the strongest surface in BlueBench. This critique is meant to identify:

- what is already working
- what is slightly weak
- what should be improved later without disrupting the current interaction model

---

## Summary

The Inspector is currently the best-resolved part of the product.

Why:

- it has a clear information hierarchy
- it respects the product's text-first philosophy
- it supports both reference reading and diagnostic reading
- it avoids graph-visualization clutter
- it feels like a technical manual rather than a flashy dashboard

That said, it still has a few layout weaknesses:

- the top header is useful but underpowered visually
- the `Code / Relationships / Metadata` tab row is correct but still slightly generic
- compute content in Metadata is informative but not yet visually ranked enough
- Relationships is strong structurally but could be easier to scan at depth
- the window does not strongly distinguish between “reading mode” and “diagnostic mode”

So the judgment is:

- do not redesign it now
- do not destabilize it
- but there is meaningful polish available later

---

## What Is Already Good

### 1. The tab model is correct

Current order:

- `Code`
- `Relationships`
- `Metadata`

This is the right order.

Why:

- `Code` is the default working surface
- `Relationships` is the first analytical expansion
- `Metadata` is the supporting reference section

This ordering matches actual usage instead of pretending everything is equal.

Recommendation:

- keep this exactly as-is

---

### 2. The Inspector is text-first, which is correct

The Inspector is strongest when it behaves like a technical dossier.

That is already happening:

- compute is textual
- relationships are textual
- notes are textual
- outline is textual

This fits BlueBench better than a mini graph, a heatmap, or a chart-heavy inspector would.

Recommendation:

- preserve this philosophy

---

### 3. The fixed-size window is a strength, not a weakness

At `460 x 640`, the Inspector behaves like a controlled reading panel.

That gives it:

- predictability
- density
- disciplined layout constraints

It prevents the window from turning into a sprawling secondary app.

Recommendation:

- keep the fixed-size model for now

---

### 4. Notes and relationships fit naturally into the Inspector

The current placement of notes and relationship detail is conceptually right.

Why:

- the Explorer should not become overloaded
- the Inspector is the place where file-level detail becomes deep analysis

Recommendation:

- keep notes and compute-heavy detail in Inspector
- keep Explorer shallow

---

## Main Criticisms

### 1. The header block is too passive

Current behavior:

- title and meta are present
- file path and type are shown
- line and call-path context appear

Weakness:

- the header reads like plain metadata, not like the control header of an analytical document

Why it matters:

- the header is the anchor for everything below it
- when it is too visually weak, the tabs feel like they begin without a strong frame

Recommended future improvement:

- strengthen title hierarchy
- keep path secondary
- make the file identity more explicit

Suggested structure:

```text
engine.py
core/engine.py · module · line 42
active run: vox_ui_verify
```

At the moment, active run context is missing from the Inspector header. That is the main missing piece.

---

### 2. The Inspector does not surface active run context strongly enough

Current state:

- compute is driven by selected run
- but the window itself does not clearly remind the user which run is being used

This is the biggest remaining Inspector trust gap.

Why it matters:

- compute values are not absolute truth
- they belong to a chosen run
- if the Inspector does not show that clearly, users can over-trust stale context

Recommended future improvement:

- add a compact active-run line in the header or Metadata top section

Example:

```text
Active Run: vox_ui_verify
```

Optional:

```text
custom_script · mini_pc_n100_16gb
```

This is the most important Inspector enhancement I would make later.

---

### 3. The Code tab is correct, but the toolbar is visually underused

Current behavior:

- toolbar exists
- layout lock button exists
- otherwise it is visually sparse

Weakness:

- the toolbar does not yet feel like it owns meaningful state
- it currently behaves more like leftover chrome than a purposeful control strip

Recommendation:

- either strengthen it with real context
- or reduce it further if layout lock remains niche

Potential future direction:

- add active-run indicator
- add compute summary token
- keep actions minimal

If no additional controls are added, the toolbar could become visually slimmer.

---

### 4. The Outline control is useful but not visually integrated enough

Current behavior:

- the outline selector works
- compute appears inline
- selection is useful

Weakness:

- it still feels like a utility dropdown added above code, rather than part of the Code tab’s reading workflow

Recommendation:

- visually integrate outline with the code header zone
- consider a lighter label or inline heading above it

Example:

```text
Outline
[ Jump to definition... ]
```

This is a small change, but it would improve the reading flow.

---

### 5. Metadata is correct structurally, but the compute section is still too flat

Current behavior:

- file information
- compute data
- notes
- relationship summary
- external pressure

Weakness:

- all metadata sections feel similar in emphasis
- compute does not feel meaningfully more important than the supporting sections

Recommendation:

- later, give `Compute data` slightly stronger visual weight
- not with charts, just with hierarchy

Possible improvements:

- larger numeric lines for score/time
- stronger section title styling
- more compact support lines below

Right now it is readable, but not yet optimally ranked.

---

### 6. Function ranking is useful but visually repetitive

Current behavior:

- function ranking entries show all needed fields
- that is good for correctness

Weakness:

- each function block reads similarly
- the eye has to parse every row carefully

Recommendation:

- preserve text-first design
- tighten each row into a more scanable structure

Example:

```text
parser.py::parse_block
Score 91.4 · self 120 ms · total 410 ms · calls 8821
Exceptions 0
```

This is close to what exists now, but could benefit from more contrast between:

- name
- performance line
- failure line

The content is right. The presentation can still improve.

---

### 7. Relationships is structurally strong but deep trees still become visually noisy

Current behavior:

- chapter indexing works
- recursive calls tree works
- cross references work
- cycle detection works

This is strong architecture.

Weakness:

- once recursion depth grows, the visual density rises quickly
- repeated indentation alone becomes harder to scan

Recommended future improvement:

- keep text tree layout
- add slightly clearer hierarchy markers

Potential options:

- lighter indentation guides
- slightly different text tone for cross-reference rows
- slightly stronger style for top-level relationship entries

Do not replace this with a graph. Just improve scanability.

---

### 8. Notes are functionally good, but the Metadata tab does not yet make them feel reference-worthy

Current behavior:

- notes appear
- jump-to-code works

Weakness:

- notes currently feel like extracted annotations
- they do not yet feel like part of a coherent documentation layer

Recommendation:

- later, give notes slightly stronger titling and preview formatting
- keep them compact
- do not turn them into a notebook UI

This is a secondary refinement, not a priority.

---

## Suggested Future Improvements

These are the Inspector changes I would consider later, in order.

### 1. Add active run context to the Inspector header

Highest value, lowest risk.

### 2. Strengthen the compute section hierarchy in Metadata

Make measured compute feel like the primary analytical payload.

### 3. Improve function ranking row formatting

Keep text-first, but make scanning easier.

### 4. Integrate the outline control more cleanly into the Code tab header flow

Small but useful polish.

### 5. Improve deep relationship tree scanability

Only after the above.

---

## What Should Not Change

These parts should stay as they are for now:

- fixed window size
- tab order
- text-first relationship model
- code viewer read-only model
- notes integrated into Metadata
- no dependency graph in Inspector
- no chart-heavy compute view

These are strengths, not weaknesses.

---

## Final Judgment

The Inspector is already good enough to treat as a stable product surface.

It does not need redesign.

It needs only selective, trust-oriented polish:

- make run context explicit
- make compute hierarchy slightly stronger
- make dense sections easier to scan

That is the correct level of intervention.
