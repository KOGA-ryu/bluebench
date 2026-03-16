# Scanner Performance Plan

## Purpose

This document narrows the scanner review to one question:

> How should BlueBench improve scanner performance without changing scanner behavior prematurely?

This is an execution plan, not a redesign proposal.

## Current Measured State

Latest bounded self-verification report:

- run: `bluebench_real_verify_fastcheck4`
- status: `completed`
- runtime: `1615.02 ms`
- run quality: `strong`

Measured stage timings:

- `triage_generate`: `797.28 ms`
- `context_build`: `796.88 ms`

Top measured backend files:

1. `backend/scanner/python_parser/python_scanner.py`
   - `274.31 ms`
   - `28141 calls`
2. `backend/core/graph_engine/graph_manager.py`
   - `23.84 ms`
3. `backend/triage/static_summary.py`
   - `22.40 ms`

What this means:

- scanner cost is no longer catastrophic
- scanner cost is still first by a wide margin
- scanner performance is now the clearest remaining backend optimization target in the bounded verification path

## Current Structural State

The scanner already has several good performance traits:

- ignored directories are filtered early
- include-prefix bounding exists and works
- AST/source are cached during a scan
- static file records are reused by triage
- repeated parse work was already reduced

So this is not a "scanner is naive" situation.

It is a "scanner is now good enough to profile honestly" situation.

## Performance Findings

### High Confidence

1. The scanner remains the dominant measured backend hotspot.
2. Bounded scope is the single highest-leverage operational control.
3. Remaining scanner work is still too traversal-heavy per file.
4. Further scanner optimization should focus on per-file work collapse before deeper algorithm changes.

### Medium Confidence

1. A unified per-file extraction pass should still produce a measurable win.
2. Incremental file reuse will likely matter more for repeated project loads than for one-shot verification runs.
3. Import resolution and call-edge resolution are not the first performance problem to attack.

## What Is Probably Expensive Right Now

Based on code structure, not speculation:

### 1. Multiple Meaningful AST Traversals Per File

The scanner still performs separate work for:

- static file record extraction
- import edge extraction
- top-level symbol extraction
- function complexity/direct-call analysis

Even though parse reuse exists, the tree is still being walked in more than one substantial way.

### 2. Per-Function Recursive Traversal

`analyze_function()` recursively walks each top-level function body to compute:

- loops
- branches
- calls
- direct call names

This is necessary work, but it is also inherently proportional to function body size and count.

### 3. Full Scan Per Project Load

There is currently no persistent per-file reuse across project loads.

That means repeated operations still pay:

- file discovery
- file read
- AST parse
- node extraction

even when nothing changed.

### 4. Scanner Work Is On The Critical Path Twice

The scanner cost is not isolated.

It feeds:

- `triage_generate`
- `context_build`

That means any scanner inefficiency is effectively paid twice in the current verification flow.

## What Not To Do First

These are tempting but lower-value as first performance moves:

### 1. Do Not Start With Call-Edge Sophistication

Call-edge correctness is important, but it is not the first performance win.

Improving call modeling now risks larger code churn with unclear speed benefit.

### 2. Do Not Start With Parallel Scanning

Parallelism may help later, but it increases complexity around:

- shared graph state
- AST cache ownership
- deterministic ordering

There is still enough single-thread waste to remove first.

### 3. Do Not Start With Persistent On-Disk Caches

Persistent caching is attractive, but it is best applied after:

- output shape is more stable
- per-file extraction shape is cleaner

Otherwise BlueBench risks caching the wrong boundary.

## Execution Plan

### Pass 1: Add Scanner-Specific Timing Breakdown

Goal:

- measure scanner phases directly instead of inferring from total file hotspots

Work:

1. add internal timers for:
   - file discovery
   - parse/load
   - module registration
   - static file record extraction
   - symbol extraction
   - call-edge resolution
2. emit them into the performance report
3. keep output format simple and stable

Why first:

- this turns the next pass from informed guesswork into direct measurement

Acceptance criteria:

- performance report contains scanner phase timings
- timings add clarity without changing scan results

### Pass 2: Collapse Static Record And Import Extraction Into One Per-File Pass

Goal:

- reduce tree walking without changing output

Work:

1. produce one per-file extraction structure that captures:
   - imports
   - optional imports
   - native imports
   - framework markers
   - callable/class counts
   - top-level defs
2. feed both:
   - `_static_file_records`
   - graph-building logic
   from that structure
3. keep parse caching intact

Why second:

- this is the clearest non-invasive performance win still left

Acceptance criteria:

- scanner output remains equivalent
- scanner raw ms drops in bounded verification
- `triage_generate` and `context_build` both improve measurably

### Pass 3: Reduce Project Load Duplication Across Triage And Context

Goal:

- avoid paying the same scan cost twice in the verification flow

Work:

1. identify where `generate_triage()` and `build_context_pack()` repeat the same load path
2. allow one shared loaded project snapshot to be reused across both steps
3. keep this scoped to the caller path first, not as a global app rewrite

Why third:

- current stage timings show `triage_generate` and `context_build` are nearly identical
- that strongly suggests duplicated upstream work

Acceptance criteria:

- same verification run produces lower combined `triage_generate + context_build` time
- no visible behavior regressions in triage/context outputs

### Pass 4: Add Incremental File Reuse

Goal:

- avoid rescanning unchanged files on repeated project loads

Work:

1. compute per-file change keys:
   - mtime and size at minimum
   - hash if needed later
2. cache per-file scan results
3. rebuild indexes only for changed files
4. keep full rebuild fallback simple and safe

Why fourth:

- this is high leverage for repeated interactive use
- but it should come after the scanner’s extraction boundaries are cleaner

Acceptance criteria:

- repeated project loads on unchanged code are materially faster
- cache invalidation is correct
- fallback full scan remains available

## Repo Data Points To Preserve

These should stay in the repo as the baseline for scanner performance work:

### 1. Canonical Verification Target

- `tools/verification/bluebench_real_verify.py`

Reason:

- it is now the bounded, stable self-verification workload

### 2. Canonical Performance Baseline

Current baseline numbers to compare against:

- runtime: `1615.02 ms`
- scanner raw time: `274.31 ms`
- `triage_generate`: `797.28 ms`
- `context_build`: `796.88 ms`

These are the numbers future scanner passes should compare themselves to.

### 3. Existing Tests That Protect Scope Controls

- `tests/test_project_loader.py`

Reason:

- upstream boundary filtering and bounded prefixes are now part of the scanner performance strategy, not just correctness

## Non-Goals

This plan does not cover:

- call-edge correctness redesign
- method/nested-function coverage expansion
- scanner trust diagnostics
- graph model changes

Those are important, but they are not the first performance topic.

## Recommended Implementation Order

1. Pass 1: scanner-specific timing breakdown
2. Pass 2: collapse more per-file extraction work
3. Pass 3: shared project-load reuse across triage/context
4. Pass 4: incremental file reuse

## Bottom Line

The scanner is no longer "mysteriously slow."

It is specifically:

- measurable
- bounded
- still the hottest backend path

That means the next performance work should be disciplined:

- measure internal scanner phases
- remove remaining duplicated per-file work
- then reduce duplicated load paths across triage and context

That sequence should improve scanner cost without destabilizing the rest of BlueBench.
