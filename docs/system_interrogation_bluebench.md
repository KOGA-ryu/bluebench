# BlueBench System Interrogation

This document answers the engineering-interrogation checklist against the current BlueBench system as implemented today: repository graph explorer, inspector windows, runtime instrumentation backend, and Stress Engine runner flow.

Format:
- `Question`
- `Answer`
- `Confidence`
- `Notes / Sources`

## Problem Definition

### 1. What exact problem is the system solving, stated in one sentence?
Answer: BlueBench measures and visualizes codebase structure and runtime hotspots so a developer can understand where complexity, cost, and failures concentrate in a repository.
Confidence: High
Notes / Sources: [README.md](/Users/kogaryu/dev/bluebench/README.md), [backend/instrumentation](/Users/kogaryu/dev/bluebench/backend/instrumentation), [backend/stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py)

### 2. Who or what consumes the output of the system?
Answer: The primary consumer is a human developer using the Qt desktop app; secondary consumers are the explorer, inspector, Stress Engine summary views, and saved `.bbtest` artifacts.
Confidence: High
Notes / Sources: [backend/main.py](/Users/kogaryu/dev/bluebench/backend/main.py), [backend/stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py)

### 3. What would happen if the system stopped running for one hour?
Answer: No new instrumented runs or explorer sessions could be launched, but previously saved summaries and source repos would remain intact.
Confidence: High
Notes / Sources: Desktop-local architecture; no always-on backend service exists today.

### 4. What would happen if it stopped running for one day?
Answer: Developers would lose a day of measurement and exploration capability, but there is no user-facing production outage because BlueBench is a tooling system rather than a serving path.
Confidence: High
Notes / Sources: Current app is an interactive desktop tool, not an always-on platform service.

### 5. What parts of the workload are actually necessary vs “nice to have”?
Answer: Necessary: project scanning, deterministic explorer, inspector code view, instrumented run execution, raw metrics capture, post-run summaries. Nice to have: richer visual polish, `.bbtest` workflows, relationship recursion UX, advanced comparison, AI assistance.
Confidence: Medium
Notes / Sources: Current implemented milestones in [backend/main.py](/Users/kogaryu/dev/bluebench/backend/main.py), [backend/stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py)

### 6. What is the expected size of input data today?
Answer: Today the system appears aimed at small to medium Python repos, roughly hundreds to low-thousands of files, with instrumented runs producing hundreds to low-thousands of summarized function rows and tens to hundreds of resource samples per run.
Confidence: Medium
Notes / Sources: Current scanners are Python-only and in-memory; no sharding or large-data infrastructure exists.

### 7. What is the expected size of input data in 2 years?
Answer: If the product keeps expanding, the likely target is multi-thousand-file repositories and many accumulated runs per project, likely tens of thousands of summarized rows across stored history.
Confidence: Low
Notes / Sources: Projection only; no explicit roadmap or capacity target exists in repo.

### 8. What is the worst case input size the system must survive?
Answer: Worst case it must survive a large monorepo with several thousand Python files and an instrumented script that triggers very high call counts without turning tracing overhead into the bottleneck.
Confidence: Medium
Notes / Sources: Stress prompt history and current instrumentation design emphasize summarized-per-function storage, not per-call rows.

### 9. Is the system optimized for latency or throughput?
Answer: It is optimized primarily for interactive latency and trustworthiness at single-user scale, not bulk throughput.
Confidence: High
Notes / Sources: Desktop UI, fixed-timer live polling, single-run subprocess model.

### 10. What level of accuracy is required before results become “good enough”?
Answer: Good enough means hotspot ordering and failure attribution must be directionally reliable enough that the top files/functions are actually the expensive ones, even if exact wall-clock attribution is not perfect.
Confidence: High
Notes / Sources: Instrumentation design stores measured self/total time, call counts, exceptions, and normalized scores; UI tiers come later.

## Workload & System Behavior

### 1. Is the workload continuous, periodic, or event-driven?
Answer: Mostly event-driven. Repository scanning starts from user selection; instrumentation runs start from explicit user action; live refresh is periodic while a run is active.
Confidence: High
Notes / Sources: [backend/main.py](/Users/kogaryu/dev/bluebench/backend/main.py), [backend/stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py)

### 2. What triggers work to begin?
Answer: User actions trigger all major work: selecting a project, opening the Stress Engine, starting a run, opening inspectors, expanding explorer nodes.
Confidence: High
Notes / Sources: Qt signal wiring in [backend/main.py](/Users/kogaryu/dev/bluebench/backend/main.py)

### 3. How often does the system run?
Answer: There is no fixed schedule. It runs whenever a user launches the app and starts scans or stress runs.
Confidence: High
Notes / Sources: No scheduler or daemon exists.

### 4. What happens if multiple workloads arrive simultaneously?
Answer: Today the system handles that weakly. The explorer and graph work remain single-process in one desktop app, while multiple stress windows/runs are not deeply coordinated and could contend for CPU and disk.
Confidence: Medium
Notes / Sources: Current Stress Engine owns a single `QProcess` per window; no global run scheduler exists.

### 5. Is work processed individually or can it be batched?
Answer: Repository scanning and stress runs are processed individually; post-run aggregation batches summarized rows; live ranking and resource samples are incremental.
Confidence: High
Notes / Sources: [backend/instrumentation/collector.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/collector.py), [backend/instrumentation/aggregator.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/aggregator.py)

### 6. What is the slowest step in the pipeline right now?
Answer: For code exploration, likely repository scanning and graph construction. For stress runs, the slowest step is the instrumented target workload itself plus tracer overhead on hot call paths.
Confidence: Medium
Notes / Sources: No explicit benchmark data in repo; inferred from architecture.

### 7. Which steps depend on external systems?
Answer: Very few. The current system mainly depends on the local filesystem, Python runtime, Qt/WebEngine, and whatever the target script itself touches.
Confidence: High
Notes / Sources: No network/database service dependencies beyond local SQLite.

### 8. What happens when an external dependency becomes slow?
Answer: The instrumented run slows down, and BlueBench records the impact indirectly through external buckets and process-level metrics; the UI will lag only in proportion to the subprocess and DB polling delay.
Confidence: Medium
Notes / Sources: External bucket design in [backend/instrumentation/tracer.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/tracer.py)

### 9. What happens when an external dependency fails completely?
Answer: The target script can fail; BlueBench should still finalize the run, persist partial raw data, and surface failure/exception indicators in summary output.
Confidence: High
Notes / Sources: Failure capture in [backend/instrumentation/script_runner.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/script_runner.py), exception tracking in collector/tracer.

### 10. Can the system degrade gracefully under pressure?
Answer: Partially. It avoids per-call DB writes, uses summarized raw rows, and separates live polling from backend batches, but it does not yet have admission control, run queueing, or memory backpressure strategies.
Confidence: Medium
Notes / Sources: Current implementation choices in instrumentation modules; missing scheduler/backpressure mechanisms.

## Algorithms & Computation

### 1. What is the time complexity of the core algorithm?
Answer: There is no single core algorithm. Key paths are roughly linear or near-linear in current data size: AST scanning is O(files + syntax tree size), relationship indexing is O(nodes + edges), layout placement is near O(visible nodes + interval lookups), and aggregation is O(function rows + samples + file groups).
Confidence: Medium
Notes / Sources: [backend/core/graph_engine/graph_manager.py](/Users/kogaryu/dev/bluebench/backend/core/graph_engine/graph_manager.py), [layout/engine.py](/Users/kogaryu/dev/bluebench/layout/engine.py), [backend/instrumentation/aggregator.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/aggregator.py)

### 2. Is the current algorithm the simplest correct approach?
Answer: Mostly yes. The system intentionally uses straightforward deterministic placement, summarized tracing, and local SQLite rather than more complex distributed or probabilistic designs.
Confidence: High
Notes / Sources: Current code favors direct data structures and simple processing stages.

### 3. Could the algorithm be replaced with a more efficient mathematical model?
Answer: Some parts could. Live ranking could use stronger streaming approximations, and scoring could use more formal weighting models, but that is not the main bottleneck today.
Confidence: Medium
Notes / Sources: [backend/instrumentation/ranking.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/ranking.py), [backend/instrumentation/aggregator.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/aggregator.py)

### 4. Is the algorithm recalculating identical results repeatedly?
Answer: Yes, in a few places. Explorer metadata and graph merges are rebuilt on refresh; some UI summaries are reread from SQLite every timer tick; spec validation reparses all section editors on each edit.
Confidence: High
Notes / Sources: [backend/stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py), [backend/api/bridge.py](/Users/kogaryu/dev/bluebench/backend/api/bridge.py)

### 5. Can previous results be cached or reused?
Answer: Yes. Layout positions already are; relationship indexes are; run summaries are stored in SQLite; live UI could cache unchanged views more aggressively.
Confidence: High
Notes / Sources: [layout/layout_cache.py](/Users/kogaryu/dev/bluebench/layout/layout_cache.py), relationship index in [graph_manager.py](/Users/kogaryu/dev/bluebench/backend/core/graph_engine/graph_manager.py)

### 6. Is sorting being used where partial sorting or filtering would suffice?
Answer: Yes in places. Live hot files and file summaries sort full lists even though only top N are displayed; `heapq.nlargest` style partial ranking would be enough.
Confidence: High
Notes / Sources: Storage/UI sorting in [backend/stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py), ranking snapshot in [backend/instrumentation/ranking.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/ranking.py)

### 7. Are there opportunities for precomputation?
Answer: Yes. Chapter indexes, relationship indexes, file metrics, canonical spec parsing, and summary deltas are all candidates for stronger precomputation.
Confidence: High
Notes / Sources: Existing precompute examples already exist in graph manager and aggregator.

### 8. Can approximations replace exact calculations without harming results?
Answer: In some places yes, especially live ranking and resource-pressure weighting, but not for raw persisted measurements such as per-function self/total time and exception counts.
Confidence: Medium
Notes / Sources: Instrumentation design explicitly preserves raw values.

### 9. What part of the algorithm grows fastest as input size increases?
Answer: The tracer overhead grows fastest with call frequency, and the graph/model side grows fastest with file count plus relationship density.
Confidence: High
Notes / Sources: Per-call profiling cost in [backend/instrumentation/tracer.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/tracer.py), relationship graph growth in [graph_manager.py](/Users/kogaryu/dev/bluebench/backend/core/graph_engine/graph_manager.py)

### 10. If the dataset doubled in size tomorrow, what part breaks first?
Answer: First pressure point is interactive responsiveness: tracer overhead during hot runs and UI refresh/summary rendering for larger live/result sets.
Confidence: Medium
Notes / Sources: No virtualization or run scheduler yet.

## Data & Memory

### 1. How many times does the same data move through memory?
Answer: Often multiple times: source files are read into AST, graph nodes are copied into tree/layout/render payloads, and run metrics move from in-memory accumulators to SQLite rows to UI summaries.
Confidence: High
Notes / Sources: Scanner + graph tree + renderer + storage flow across modules.

### 2. How many copies of the same data structure exist during processing?
Answer: Commonly at least two or three copies exist transiently, especially for graph/tree/layout payloads and JSON-serialized summary blobs.
Confidence: High
Notes / Sources: Deep copies in bridge/layout prep, JSON storage of summaries, UI state duplication.

### 3. Is data stored in a format optimized for machines or humans?
Answer: Mixed. In-memory structures are machine-oriented dict/list payloads; `.bbtest` and editor sections are human-editable text; SQLite summaries are machine-oriented but JSON fields are hybrid.
Confidence: High
Notes / Sources: [backend/stress_spec.py](/Users/kogaryu/dev/bluebench/backend/stress_spec.py), [backend/instrumentation/storage.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/storage.py)

### 4. Are there conversions happening repeatedly (JSON, text, parsing)?
Answer: Yes. Repeated conversions happen in `.bbtest` save/load, live state JSON fields, spec parse/merge, and summary display formatting.
Confidence: High
Notes / Sources: [backend/stress_engine.py](/Users/kogaryu/dev/bluebench/backend/stress_engine.py), [backend/instrumentation/storage.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/storage.py)

### 5. How large is the system’s memory footprint during peak load?
Answer: Unknown in measured terms. Likely modest for normal repos, but peak memory during large runs can rise due to Qt/WebEngine, parsed source text, graph copies, and retained run buffers.
Confidence: Low
Notes / Sources: No memory benchmark or telemetry beyond sampled process RSS.

### 6. Are objects fragmented in memory or stored contiguously?
Answer: Mostly fragmented Python objects: dicts, lists, dataclasses, AST nodes, Qt widgets, SQLite row objects.
Confidence: High
Notes / Sources: Python/Qt architecture by construction.

### 7. Can data structures be simplified or flattened?
Answer: Yes. Several dict payloads could become typed records, summary JSON blobs could be normalized further, and repeated UI row formatting could be flattened.
Confidence: High
Notes / Sources: Existing code uses many ad hoc dict payloads across graph and instrumentation modules.

### 8. Are large datasets loaded entirely into memory when streaming would work?
Answer: Yes in some paths. Source files are read whole, run summaries are often loaded whole for display, and graph/tree generation is in-memory rather than streamed.
Confidence: High
Notes / Sources: Scanner, graph tree, and UI summary code all load full objects.

### 9. How often is disk access required?
Answer: Frequently but locally: source file reads for scanning and inspection, SQLite writes for runs and summaries, `.bbtest` reads/writes, and layout/export artifacts.
Confidence: High
Notes / Sources: [backend/instrumentation/storage.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/storage.py), [backend/main.py](/Users/kogaryu/dev/bluebench/backend/main.py)

### 10. Are there opportunities to compress or reduce stored data?
Answer: Yes. Live state tails, JSON blobs in summary tables, repeated file-path strings, and external bucket detail could all be reduced or normalized.
Confidence: Medium
Notes / Sources: Current storage prioritizes simplicity over compactness.

## Architecture & Scaling

### 1. Which parts of the system must run sequentially?
Answer: A single instrumented run’s trace/aggregation finalization is sequential in practice; canonical spec validation before start is sequential; UI event handling on the Qt main thread is sequential.
Confidence: High
Notes / Sources: Qt main-thread model, single-process runner design.

### 2. Which parts could run in parallel?
Answer: Multiple independent runs, repository scans for different projects, summary generation for separate runs, and some relationship/index precomputation could run in parallel.
Confidence: Medium
Notes / Sources: Current code does not coordinate this, but the boundaries exist naturally.

### 3. Is the system CPU bound, memory bound, or IO bound?
Answer: It depends on mode. Instrumented runs are usually CPU-bound on tracing-heavy workloads; repository scanning mixes CPU and filesystem IO; UI rendering is mostly CPU/UI-thread bound at current scale.
Confidence: Medium
Notes / Sources: No unified profiling dataset yet.

### 4. If the system were 10× larger, what architecture change would be required?
Answer: The main changes would be: background worker isolation for scanning/indexing, stricter result caching, top-N/streaming views instead of full-list redraws, and probably a stronger run/job manager instead of direct per-window subprocess ownership.
Confidence: Medium
Notes / Sources: Inferred from current single-user desktop architecture.

### 5. What single component represents the largest bottleneck?
Answer: Today the most likely bottleneck is the Python profiler/tracer overhead on hot code paths during instrumented runs.
Confidence: Medium
Notes / Sources: [backend/instrumentation/tracer.py](/Users/kogaryu/dev/bluebench/backend/instrumentation/tracer.py)

### 6. How would the system behave if deployed on multiple machines?
Answer: Poorly without redesign. It is currently local-desktop oriented, stores to local SQLite, assumes local filesystem access, and has no distributed coordination or remote execution model.
Confidence: High
Notes / Sources: Local Qt + local SQLite + local path assumptions throughout code.

### 7. Where are the natural boundaries for splitting services or modules?
Answer: Natural boundaries are: repository scanning/indexing, explorer/graph serving, instrumentation execution, summary aggregation, and artifact persistence.
Confidence: High
Notes / Sources: Existing package boundaries already hint at this split.

### 8. What instrumentation exists to detect performance issues?
Answer: The system currently has runtime instrumentation for target scripts, some debug logging for layout/relationships, SQLite summaries, and live CPU/RSS sampling. It does not yet instrument its own UI/render/scanner performance deeply.
Confidence: High
Notes / Sources: [backend/instrumentation](/Users/kogaryu/dev/bluebench/backend/instrumentation), layout logs in [layout/engine.py](/Users/kogaryu/dev/bluebench/layout/engine.py)

### 9. What metrics should be collected to understand system health?
Answer: Key metrics should include scan duration, graph node/edge counts, visible node count, layout time, render refresh time, trace overhead percentage, run duration, function row count, sample count, SQLite write latency, aggregation duration, and UI timer lag.
Confidence: High
Notes / Sources: Some of these are already partly available; several are still missing.

### 10. If performance suddenly dropped by 70%, how would you find the cause?
Answer: First isolate whether the drop is in scan, run, aggregation, or UI refresh. Then inspect live CPU/RSS, run summaries, function counts, sample counts, external bucket totals, and any recent repo/UI changes. After that, add targeted timing around tracer callbacks, SQLite operations, graph rebuilds, and renderer refresh calls.
Confidence: High
Notes / Sources: Current code has enough structure to instrument these stages separately, but not all timings are already emitted.

## Key Unknowns

- Real repository size targets are not documented.
- Acceptable tracer overhead is not benchmarked.
- Peak memory footprint is not measured.
- Multi-run concurrency behavior is mostly untested.
- Stress Engine usability under large summaries has not been benchmarked.

These are the highest-value areas for deeper research before aggressive optimization.
