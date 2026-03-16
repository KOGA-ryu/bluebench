# Scanner Report

## Scope

This report covers the current Python scanner implementation in:

- `backend/scanner/python_parser/python_scanner.py`
- `backend/core/project_manager/project_loader.py`
- its immediate reuse path into triage/static summary

No code changes were made as part of this report.

## Executive Summary

The scanner is currently good enough to power BlueBench's graph, triage, and bounded self-verification flows, but it is also the clearest remaining backend hotspot and one of the main correctness bottlenecks in the project model.

The central reality is:

- the scanner is still the dominant measured hotspot in self-verification runs
- its data model is intentionally shallow
- that shallow model now mismatches parts of the rest of the system, especially runtime instrumentation

In short:

- performance is acceptable for bounded verification, but still expensive
- correctness is acceptable for coarse repo orientation, but not for high-fidelity symbol truth
- future growth risk is not "scanner is broken"
- future growth risk is "scanner stays coarse while the rest of BlueBench gets more precise"

## What The Scanner Does Today

At a high level, the scanner:

1. walks the repo with ignored-directory filtering
2. parses Python files once and caches AST/source text in memory for the scan
3. registers module nodes for files that contain top-level class or function definitions
4. captures static file records for triage reuse
5. scans imports, top-level classes, and top-level functions
6. computes simple function complexity and direct-call names
7. resolves direct-call edges by function name

Important implementation traits:

- ignored directories are filtered early (`.venv`, `site-packages`, caches, `node_modules`, `build`, `dist`)
- include-prefix bounding exists and is now a major performance lever
- static file records are reused by triage to avoid a second parse step later
- module, package, and function-name indexes are built in-memory during the scan only

## Measured Evidence

Latest completed bounded self-verification report:

- run: `bluebench_real_verify_fastcheck4`
- status: `completed`
- runtime: `1615.02 ms`
- trace overhead estimate: `256.22 ms`
- run quality: `strong`

Stage timings:

- `triage_generate`: `797.28 ms`
- `context_build`: `796.88 ms`

Top files by raw measured time:

1. `backend/scanner/python_parser/python_scanner.py`
   - `274.31 ms`
   - `28141 calls`
2. `backend/core/graph_engine/graph_manager.py`
   - `23.84 ms`
3. `backend/triage/static_summary.py`
   - `22.40 ms`

Interpretation:

- the scanner remains the dominant backend hotspot in the bounded verification path
- previous fixes materially improved runtime, but they did not move the hotspot elsewhere
- the current performance story is "scanner is better, but still first in line for more optimization"

## Strengths

### 1. Early Boundary Filtering Is Now Sensible

The scanner excludes obvious non-project noise early:

- `.venv`
- `site-packages`
- cache directories
- `node_modules`
- `build`
- `dist`

This is important because earlier versions were polluted by vendor noise and produced misleading architecture summaries.

### 2. Include Prefixes Are High Leverage

Bounded scanning is the single strongest practical control added so far.

It allows:

- faster verification runs
- focused triage/context generation
- lower scanner cost without redesigning the scanner

### 3. Parse Reuse Is Better Than It Was

The scanner now:

- caches parsed ASTs
- caches source text
- exposes static file records for downstream reuse

That means it is no longer paying the full "reparse everything again" tax that it used to.

### 4. The Scanner Is Deterministic

For a given repo slice, it produces stable output:

- sorted file collection
- deterministic node registration
- deterministic relationship building

That matters for repeatability and debugging.

## Weaknesses

### 1. The Symbol Model Is Too Shallow

The scanner only creates graph nodes for:

- modules
- top-level classes
- top-level functions

It does not model:

- instance methods
- classmethods
- staticmethods
- nested functions
- async functions as first-class graph nodes in `_scan_file`

This is the largest structural mismatch in the subsystem.

Why it matters:

- runtime instrumentation measures methods and richer callable shapes
- the scanner graph cannot represent those symbols
- inspector and compute views are therefore more precise than the structural graph beneath them

This is a long-term consistency risk.

### 2. Module Inclusion Rules Are Lossy

A module node is only registered if `_module_has_code()` finds a top-level `ClassDef` or `FunctionDef`.

That means files with only:

- imports
- constants
- side effects
- a `__main__` guard
- configuration declarations

may be omitted from the graph as modules.

Why it matters:

- entry or setup files can disappear structurally
- import-only glue modules can be real architectural choke points
- the graph can underrepresent operationally important files

### 3. Call Resolution Is Name-Based and Scope-Blind

Direct calls are stored as bare function names and resolved later through `function_name_index`.

This means:

- `foo()` can resolve to multiple unrelated functions with the same name
- method calls are not modeled correctly
- scope and module context are ignored

This is a correctness trap, not just a limitation.

The call graph is best understood as a coarse hint system, not a faithful call model.

### 4. Import Resolution Is Intentionally Simple

Import handling is useful but not deep.

Known limitations:

- star imports are ignored
- aliasing is shallow
- dynamic imports are invisible
- package/module resolution is heuristic, not semantic

This is acceptable for lightweight orientation, but not for precise dependency truth.

### 5. Scanner Work Is Still Duplicated Internally

The scanner now avoids duplicate parse, but still does more than one meaningful AST traversal per file:

- `_capture_static_file_record()` walks the tree
- `_scan_file()` walks the tree for imports
- `_scan_file()` also iterates `tree.body`

This is better than before, but not yet minimal.

### 6. Failure Visibility Is Weak

Unreadable or invalid files are silently dropped on parse failure:

- `OSError`
- `SyntaxError`
- `UnicodeDecodeError`

The current behavior is pragmatic, but it creates a trust problem:

- missing files do not surface clearly
- graph omissions can look like truth instead of partial truth

## Scaling Characteristics

### Current Complexity Shape

Roughly:

- file discovery: `O(files)`
- AST parse: `O(total source size)`
- AST walks: `O(total AST nodes)`
- call-edge resolution: proportional to pending direct-call names and name collisions

The fastest-growing cost center is still per-file AST work.

### What Breaks First As Scope Grows

In likely order:

1. scanner runtime
2. memory used by cached trees and source texts
3. correctness drift from name-based call resolution
4. graph usefulness for method-heavy codebases

### What Bounded Scope Is Hiding

Bounded prefixes make verification fast, but they also hide the real scaling behavior of full-repo scans.

That is fine for verification, but it means:

- full-repo latency risk still exists
- bounded verification should not be mistaken for full-repo scalability proof

## Pain Points And Traps

### Trap 1: Mistaking The Graph For Canonical Symbol Truth

The scanner graph is not a full semantic model.

If later features assume it is canonical for methods or precise call relationships, they will drift into false confidence.

### Trap 2: Letting Runtime Precision Outgrow Static Precision

Instrumentation already sees richer callable behavior than the scanner can express.

If that gap widens, BlueBench will increasingly have:

- precise runtime evidence
- coarse structural anchors

That makes explanation harder, not easier.

### Trap 3: Silent Omission

A file that fails to parse or is filtered out leaves little visible evidence.

That is dangerous because users may interpret absence as irrelevance rather than scanner incompleteness.

### Trap 4: Over-Investing In Call Edges Before Symbol Identity Improves

Call-edge correctness is currently limited by name-based resolution.

Optimizing or enriching that graph too aggressively before improving symbol identity will produce better-looking wrong answers.

### Trap 5: Growing Feature Consumers Faster Than Scanner Guarantees

The scanner is already consumed by:

- graph construction
- relationship indexing
- triage
- context export

Every new consumer increases the cost of scanner mistakes and omissions.

## Opinion

The scanner is not in bad shape. It is in an honest "first serious implementation" shape.

That is different.

It now has:

- reasonable boundaries
- measurable performance
- deterministic behavior
- enough reuse to avoid obvious waste

But it also has a clear ceiling:

- it is still a coarse scanner feeding a system that is becoming more exact

If BlueBench stayed a repo-orientation tool only, this scanner could survive a long time with modest optimization.

If BlueBench keeps deepening runtime analysis and compute explanation, then scanner precision becomes a strategic issue, not just a performance issue.

## Findings

### High Confidence Findings

1. The scanner is still the primary measured hotspot in self-verification.
2. Bounded scanning is currently the most effective operational control.
3. The scanner's symbol model is materially shallower than the runtime instrumentation model.
4. Name-based call resolution is the biggest correctness weakness in the current scanner.
5. Module registration rules can omit operationally important files.

### Medium Confidence Findings

1. Further AST-pass consolidation should still reduce scanner cost.
2. Method-aware symbol modeling would improve cross-system consistency significantly.
3. Full-repo scans are likely to become a user-facing latency problem again as feature scope grows.

## Plan

### Phase 1: Trust And Visibility

Goal:

- make scanner incompleteness visible before making it more sophisticated

Actions:

1. Record skipped-file diagnostics during scan.
2. Surface counts for:
   - scanned files
   - skipped files
   - parse failures
   - bounded-prefix mode
3. Mark graph-derived outputs as partial when files are skipped.

Why first:

- this improves trust immediately without increasing model complexity

### Phase 2: Collapse More Per-File Work

Goal:

- reduce scanner cost without changing semantics

Actions:

1. Consolidate import extraction and static-record extraction into a single per-file traversal.
2. Reduce repeated tree walking where static summary and scan data overlap.
3. Measure scanner stage timings separately from downstream graph/triage work.

Success criteria:

- scanner raw ms drops measurably in bounded verification
- output remains byte-for-byte equivalent where expected

### Phase 3: Improve Symbol Coverage

Goal:

- reduce the gap between static graph and runtime truth

Actions:

1. Add method nodes for classes.
2. Add async function nodes explicitly.
3. Decide policy for nested functions:
   - either first-class support
   - or explicit non-support with visible labeling
4. Revisit `_module_has_code()` so import-only or entry-significant modules are not dropped silently.

Why this matters:

- this is the phase that improves structural truth, not just speed

### Phase 4: Replace Name-Only Call Linking

Goal:

- stop producing misleading call edges

Actions:

1. Move from bare-name indexing to module-aware call candidate resolution.
2. Prefer scoped resolution within file/module before global name fallback.
3. If ambiguity remains, represent uncertainty instead of pretending certainty.

Important rule:

- do not optimize the existing call graph heavily before doing this

### Phase 5: Add Incremental Or Persistent Scanner Reuse

Goal:

- avoid rescanning unchanged files on repeated project loads

Actions:

1. add file hash or mtime-based change detection
2. cache per-file scanner output
3. rebuild only changed file records and affected indexes

Why later:

- it is high leverage, but only worth doing after scanner output shape is more stable

## Recommended Execution Order

1. Phase 1: Trust and visibility
2. Phase 2: More per-file work collapse
3. Phase 3: Better symbol coverage
4. Phase 4: Better call resolution
5. Phase 5: Incremental reuse

## Bottom Line

The scanner is no longer a vague suspect. It is a measured subsystem with a clear profile:

- it is the hottest backend path in verification
- it is useful
- it is deterministic
- it is still structurally shallow

The right next move is not a rewrite.

The right next move is:

- expose partial-truth conditions
- reduce remaining duplicate work
- then raise symbol fidelity in the places where BlueBench already depends on more precise truth
