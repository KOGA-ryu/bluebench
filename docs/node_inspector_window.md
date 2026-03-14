# Node Inspector Window

This document is the implementation reference for the BlueBench `NodeInspectorWindow` and the supporting `CodeViewer`.

Use it as grounding context for ChatGPT or Codex when discussing:

- inspector window behavior
- file opening behavior from the explorer
- code viewing and outline jumping
- line highlighting and compute overlays
- line annotation persistence
- known limitations and invariants

## Purpose

The inspector is a detached Qt window used to inspect the source file behind a selected node.

It is not embedded in the main window.
The main graph or explorer view stays in the center pane, and inspectors open separately.

Primary responsibilities:

- show the selected file path and node metadata
- show a jump menu for functions/classes in the current file
- render source code read-only
- highlight the selected definition or region
- support per-line annotations saved at project scope

## Entry Points

Relevant implementation lives in:

- [backend/main.py](/Users/kogaryu/dev/bluebench/backend/main.py)

Important classes and methods:

- `NodeInspectorWindow`
- `CodeViewer`
- `LineNumberArea`
- `LineAnnotationDialog`
- `BlueBenchWindow._update_inspector()`

## How Inspectors Open

Inspectors are created from `BlueBenchWindow._update_inspector()`.

Behavior:

- the backend bridge emits `nodeSelectionChanged`
- the main window receives a payload containing `node`
- if an inspector for the same `node_id` already exists, that window is refreshed, raised, and focused
- otherwise, a new `NodeInspectorWindow` is created and tracked in `self.node_windows`

This means:

- multiple inspector windows can be open at once
- there is only one inspector window per node id
- re-opening the same node does not create duplicates

When the project changes:

- `_close_all_node_windows()` is called
- all open inspector windows are closed and removed from the map

When an inspector closes:

- `NodeInspectorWindow.closeEvent()` calls the `on_close` callback
- the parent window removes it from `self.node_windows`

## Supported Node Types

The inspector is effectively designed for file-backed nodes.

Current practical inputs:

- `file` nodes from the deterministic explorer
- `module` nodes
- function/class nodes that carry `file_path` and line information

Important rule:

- if a node has no `file_path`, the code viewer is cleared

## Window Layout

The inspector window is a `QMainWindow` sized to `860x640` by default.

Its vertical layout contains:

1. toolbar
2. compact header block
3. outline selector
4. read-only `CodeViewer`

### Toolbar

Current toolbar content:

- a single lock button aligned right

Button text toggles between:

- `🔒 Lock Layout`
- `🔓 Unlock Layout`

Current reality:

- this only flips `self.layout_locked`
- it does not currently alter any external layout behavior
- treat it as UI state only unless you add new behavior

### Header

The header shows:

- `header_title`: file path if available, otherwise node name/id
- `header_meta`: compact metadata string

Metadata parts currently include:

- node type
- parent id or `-`
- line number or `-`
- optional `call path compute <n>` if provided

### Outline Selector

The outline selector is a `QComboBox` used to jump to definitions in the current file.

Behavior:

- first item is always `Jump to definition...`
- for `file` or `module` nodes, the file path is treated as the module id
- for other nodes, the parent id is used as the module id
- the graph manager is scanned for child nodes of type `function` or `class`
- those outline items are sorted by `line_number`
- function names are displayed with `()`
- selecting an item calls `CodeViewer.highlightLine(line_number)`

Implications:

- outline entries are file-local class/function nodes only
- the outline is derived from `graph_manager.nodes`, not from reparsing the file in the inspector

## CodeViewer

`CodeViewer` is a subclass of `QPlainTextEdit`.

Configuration:

- read-only in the inspector
- monospace font: `Menlo`, point size `11`
- Python syntax highlighting via `PythonHighlighter`
- custom line number gutter

### What It Supports

- line numbers
- line-number gutter rendering
- read-only source display
- jump-to-line
- region highlighting
- current node highlighting
- clickable gutter annotations

### Source Loading

`NodeInspectorWindow._update_code_viewer()`:

- resolves the source path as `project_path / relative_file_path`
- loads UTF-8 source text
- if load fails, shows `Unable to load source: <path>`
- resets and reapplies extra selections

If `line_number` is present:

- `highlightNodeRegion()` is called

If `line_number` is missing:

- cursor moves to start of file

### Highlighting Rules

`highlightNodeRegion(line_number, line_start, line_end, compute_score)` can highlight:

- a full-line primary selection for the target line
- an optional compute region overlay across `line_start..line_end`

Compute overlay rules:

- only applied when `compute_score >= 4`
- score `<= 7` uses amber-like color `#d4a017`
- score `> 7` uses orange-red `#c1440e`
- overlay alpha is `110`

Primary selected line:

- uses background `#2d1f45`
- uses full-width selection formatting
- cursor is centered to that line

### Syntax Highlighting

`PythonHighlighter` currently highlights:

- Python keywords
- strings
- comments
- numbers
- function names after `def`
- class names after `class`

Color palette is custom and dark-theme oriented.

## Line Number Gutter

`LineNumberArea` is a separate child widget attached to `CodeViewer`.

Behavior:

- width scales with document line count
- background is `#111116`
- default line number color is `#888888`
- annotated lines are shown in `#4aa3ff`

Clicking the gutter:

- resolves the clicked line number
- opens the annotation dialog for that line

## Line Annotations

Annotations are persisted per project in:

- `.bluebench_annotations.json`

Path rule:

- saved in the project root, not globally

Schema shape:

```json
{
  "relative/file.py": {
    "12": {
      "marker": "note",
      "note": "text"
    }
  }
}
```

Supported markers in the dialog:

- `note`
- `optimization`
- `refactor`
- `investigate`

Annotation flow:

1. click a line number
2. `LineAnnotationDialog` opens
3. user edits marker and note
4. on accept, annotation is saved in memory and written to disk
5. gutter repaint reflects annotated lines

Failure behavior:

- malformed or unreadable annotation files are ignored
- failed writes are silently ignored

## Data Contract Expected By the Inspector

The inspector works best when the selected node payload includes:

- `id`
- `name`
- `type`
- `file_path`
- `line_number`
- `line_start`
- `line_end`
- `compute_score`
- `parent`

Optional:

- `call_path_total_compute`

Minimal viable payload for useful behavior:

- `id`
- `file_path`

Without `file_path`:

- no source file can be shown

Without `line_number`:

- file opens, but no target line is focused

## Current Integration with the Explorer

The rectangle-based deterministic explorer opens inspectors by calling backend `nodeSelected(node_id)` for file nodes.

That means:

- clicking a file header in the renderer should open or refresh the inspector
- folder nodes generally do not need inspectors
- inspector behavior is still code-centric, even though the explorer is folder/file-centric

## Behavioral Invariants

These are safe assumptions for prompts and future code changes:

- inspectors are detached windows, not docked panels
- duplicate inspector windows for the same node id are avoided
- source rendering is read-only
- outline jump targets are line-based
- annotations are persisted per project root
- `CodeViewer` is responsible for gutter, highlighting, and annotation I/O

## Current Limitations

Important limitations to know before asking ChatGPT for changes:

- the layout lock button does not currently affect any real layout logic
- inspector content is tailored to Python code files
- the outline is based on graph-manager children, not live parsing at open time
- annotation save/load failures are mostly silent
- syntax highlighting is simple and regex-based, not semantic
- no diff view, edit mode, search panel, or symbol tree beyond the combo box exists

## Good Prompting Guidance

If asking ChatGPT to modify the inspector, include:

- whether the change belongs in `NodeInspectorWindow`, `CodeViewer`, or both
- whether the change affects explorer-to-inspector payloads
- whether annotation persistence format may change
- whether behavior should remain read-only
- whether the outline selector should stay combo-box-based

Examples of precise requests:

- “Add a search box above `CodeViewer` without changing annotation behavior.”
- “Make the inspector display folder summary metadata when a folder node is selected.”
- “Replace the lock button with a pin button and wire actual behavior.”
- “Add marker color chips next to annotated gutter lines while preserving `.bluebench_annotations.json`.”

## Source of Truth

If this doc and implementation diverge, the source of truth is:

- [backend/main.py](/Users/kogaryu/dev/bluebench/backend/main.py)
