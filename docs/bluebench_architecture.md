# bluebench architecture

## graph model

Blue Bench models a codebase as a directed architecture graph managed by `GraphManager`.

Core graph data is structural:

- `nodes`
- `edges`

Each node stores only structural fields:

- `id`
- `name`
- `type`
- `parent`
- `file_path`
- `line_number`

Each edge stores:

- `source`
- `target`
- `type`

The graph is scanned from Python repositories and then sliced into smaller views for rendering, such as module-focused views.

## node types

The current node types are:

- `subsystem`
- `module`
- `class`
- `function`
- `cluster`

Notes:

- `subsystem` typically represents the repository root.
- `module` represents a Python source file.
- `class` and `function` represent top-level definitions discovered from Python AST parsing.
- `cluster` is a renderer-only synthetic node used to collapse large groups of children.

## relationships

The current relationship types are:

- `contains`
- `imports`
- `calls`
- `planned_flow`

Definitions:

- `contains`: parent-child relationship such as module to class or function
- `imports`: module-level import relationship between Python files in the same repository
- `calls`: simple direct function-call relationship between discovered top-level functions
- `planned_flow`: placeholder relationship type used by early seed/demo data

Module-focused graph views currently include:

- the selected module
- its contained classes/functions
- modules it imports
- modules that import it
- call edges when both endpoints are inside the visible slice

## annotation system

Blue Bench separates node structure from node metadata.

`GraphManager` keeps metadata in a separate `node_metadata` store keyed by `node_id`.

Current metadata fields:

- `markers`
- `notes`
- `compute_score`
- `runtime_stats`
- `experiments`

Markers are currently used for lightweight tagging and future optimization workflows.

Supported marker categories:

- `optimization`
- `performance`
- `refactor`
- `investigate`

The code viewer also supports line-level annotations stored per file and line number. These are persisted in:

- `.bluebench_annotations.json`

at the project root.

## ui layout

### main window

The main Qt window currently has two primary panels in a horizontal splitter:

- navigator panel
- graph canvas

The navigator contains:

- project tree
- file/module tree
- hotkey reference

The center area contains:

- layout selector
- embedded web graph renderer

Node inspection is no longer embedded in the main window.

### node inspector windows

Selecting a node opens a detachable `NodeInspectorWindow`.

Each node inspector window contains:

- compact header
- outline selector for classes/functions in the current file
- read-only `CodeViewer`

The code viewer supports:

- line numbers
- Python syntax highlighting
- selected-line highlighting
- clickable gutter annotations

Multiple node inspector windows can be open at once, and reselecting the same node focuses the existing window instead of creating a duplicate.

### graph renderer

The graph renderer is an HTML/D3 view hosted inside Qt WebEngine and connected through Qt WebChannel.

Current renderer behavior includes:

- deterministic layouts: `horizontal`, `vertical`, `radial`, `grid`
- node expansion and collapse
- focus lens mode
- relationship highlighting
- cluster nodes for large child groups
- marker badges on nodes

The renderer is designed to keep large repository views explorable without loading the full graph into view at once.
