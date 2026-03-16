# Codex CLI Efficiency and Anti-Thrash Guide

## Purpose

This document describes how to reduce thrash, misuse, wasted context, and unnecessary cost when working with Codex in CLI.

“Thrash” here means:

- repeated rediscovery of the same repo facts
- broad or vague asks that cause unnecessary exploration
- reopening the same problem from scratch
- switching goals too often
- asking for outputs that are too large for the decision needed
- making Codex produce work that should be cached, persisted, or compressed once

The goal is not just speed.

The goal is:

- lower cost
- lower token waste
- lower mistake rate
- lower reorientation burden
- higher ratio of useful work per turn

---

## What Causes Thrash

### 1. Goal Ambiguity

Example:

- “improve this”
- “make it better”
- “look into the app”

Problem:

- Codex has to spend turns deciding scope instead of executing

Fix:

- give one outcome, one surface, one constraint

Better:

- “improve the triage window for AI use, keep it text-first, don’t add graphs”

---

### 2. Repeated Repo Reorientation

Problem:

- Codex repeatedly rereads structure and rediscoveries the same entry points or hotspots

Fix:

- persist context
- export compact summaries
- reuse triage and context artifacts

Best initiative:

- build and use `bb_context_*` exports

---

### 3. Oversized Answers For Small Decisions

Problem:

- asking for full explanations when only a yes/no or one-file answer is needed

Fix:

- match response size to the decision

Examples:

- for implementation:
  - “do it”
- for review:
  - “top 3 issues only”
- for design:
  - “one-pager”

---

### 4. Too Many New Directions At Once

Problem:

- multiple feature ideas in one turn often force context splitting

Fix:

- separate:
  - design
  - implementation
  - validation
  - polish

This is already one of your strongest habits.

---

### 5. No Durable Artifact For Reused Understanding

Problem:

- useful conclusions remain inside the conversation only

Fix:

- write them into repo docs or machine artifacts

Examples:

- design `.md`
- task `.md`
- performance report
- triage report
- future context pack

This is one of the best ways to save cost long term.

---

### 6. Using Codex For Discovery That The App Could Do Better

Problem:

- if BlueBench can summarize structure, runs, hotspots, or risks, Codex should consume that result instead of recreating it from raw files

Fix:

- move repeated discovery into BlueBench features

High-value candidates:

- AI Context Pack
- session brief
- typed evidence exports

---

## Metrics That Matter

These are the useful operating metrics for Codex efficiency.

### Context Footprint

- how much context is needed before correct action becomes likely

### Turn Count

- how many exchanges are needed to get from request to result

### Reorientation Cost

- how much context is lost when switching tasks or returning later

### Compression Accuracy

- whether summaries preserve the important truths

### Actionability

- whether outputs point directly to the next step

### Trust

- whether measured facts are distinguished from guesses

### Redundancy

- whether the same fact appears in many places with minor wording changes

### Artifact Reusability

- whether useful work survives the session as a file, report, or export

---

## Best Initiatives To Reduce Thrash

These are the highest-value initiatives.

---

## Initiative 1: AI Context Pack

### Why it matters

This is the single best way to reduce repeated repo rediscovery.

### Effect

Reduces:

- context footprint
- reorientation cost
- repeated scanning

### What it should contain

- project identity
- entry point
- active run
- hot files
- hot functions
- risks
- actions

### Cost impact

High reduction

---

## Initiative 2: Session Persistence

### Why it matters

A lot of waste happens when restarting work.

### Effect

Reduces:

- reorientation cost
- repeated explanation
- reopening the same file/runs manually

### What should persist

- active project
- active run
- run view mode
- open inspector files
- focus targets

### Cost impact

High reduction over time

---

## Initiative 3: Typed Evidence Everywhere

### Why it matters

Weak evidence causes unnecessary verification turns.

### Effect

Reduces:

- ambiguity
- overtrust in heuristic findings
- follow-up clarification turns

### Required types

- measured
- inferred
- heuristic
- stale
- missing

### Cost impact

Medium to high reduction by avoiding wasted follow-up

---

## Initiative 4: Focus Set / Working Set

### Why it matters

Most actual work happens on a small number of files.

### Effect

Reduces:

- attention spread
- repeated selection of the same files
- noisy context exports

### Cost impact

Medium reduction

---

## Initiative 5: Run Quality Score

### Why it matters

Not all runs should be trusted equally.

### Effect

Reduces:

- acting on weak evidence
- unnecessary argument about run quality
- repeated interpretation of warnings

### Cost impact

Medium reduction

---

## Initiative 6: Layered Summary Modes

### Why it matters

Not every task needs full detail.

### Effect

Reduces:

- output bloat
- token overuse
- large unnecessary summaries

### Modes

- tiny
- short
- full

### Cost impact

High reduction in prompt overhead

---

## Initiative 7: Canonical Summary Reuse

### Why it matters

The same run/project facts should not be reconstructed separately in explorer, inspector, stress engine, triage, and exports.

### Effect

Reduces:

- drift
- contradictory summaries
- repeated computation and repeated wording

### Cost impact

Medium reduction, high correctness gain

---

## Workflow Habits That Save Cost

These are process habits, not product features.

### 1. Use phase-driven requests

Good:

- design
- build
- validate
- refine

Bad:

- design, implement, review, and rethink all in one ask

### 2. Persist useful results

If a result is likely to matter again, write it into:

- a `.md`
- JSON
- triage report
- context pack

### 3. Ask for the smallest useful output

Examples:

- “top 3 findings”
- “one-paragraph answer”
- “just patch it”
- “design doc only”

### 4. Prefer stable references

Refer to:

- file paths
- run names
- run ids
- feature names

Not vague phrases like:

- “that thing”
- “the previous panel”

### 5. Reuse chosen scope

Once a feature pass is chosen, stay on that pass until it lands.

This is one of the strongest ways to avoid task fragmentation.

---

## Anti-Patterns

These drive cost up quickly.

### Anti-pattern 1

Using Codex to repeatedly rediscover repo structure from scratch

Fix:

- triage
- context pack
- session brief

### Anti-pattern 2

Requesting “full analysis” when the next decision is small

Fix:

- ask for just enough

### Anti-pattern 3

Switching products/features every few turns

Fix:

- finish one pass
- document the next one

### Anti-pattern 4

Relying on chat memory instead of repo artifacts

Fix:

- write docs and structured exports

### Anti-pattern 5

Mixing measured facts and guesses without labeling

Fix:

- typed evidence

---

## Practical Rules For You

If your goal is efficiency for both of us, these rules are strong:

1. If a decision will matter again, ask me to write it into the repo.
2. If the task is implementation, prefer “do it” over long speculative discussion.
3. If the task is design, ask for a design doc first, then a task doc.
4. If the task is review, ask for top findings first.
5. Keep one active milestone at a time.
6. Prefer compact artifacts over repeated explanations.
7. Use BlueBench outputs instead of making me rediscover raw facts manually.

---

## Highest-Leverage Next Product Work

If the goal is specifically to reduce Codex CLI thrash, the best next feature sequence is:

1. AI Context Pack
2. Session persistence
3. Typed evidence model
4. Focus set / working set
5. Run quality score

This sequence gives the best cost reduction.

---

## Bottom Line

The biggest waste is not code generation.

It is:

- reorientation
- repeated discovery
- weak compression
- vague scope

So the best strategy is:

- compress once
- persist it
- label evidence clearly
- export compactly
- resume from stable state

That is how BlueBench becomes maximally useful to me in CLI.
