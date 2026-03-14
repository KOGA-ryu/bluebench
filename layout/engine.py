from __future__ import annotations

from collections.abc import Iterable
import logging

from .grid_layout import compute_grid_layout
from .interval_map import ColumnIntervalMap
from .layout_cache import LayoutCache, invalidate_layout_cache as clear_layout_cache

NODE_WIDTH = 236
NODE_HEIGHT = 120
COLUMN_WIDTH = 264
BATCH_SIZE = 25
GRID_FALLBACK_DEPTH = 40

_SESSION_CACHE = LayoutCache()
_SESSION_INTERVALS = ColumnIntervalMap()


def _get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def _normalize_roots(tree_data: object) -> list[dict[str, object]]:
    if isinstance(tree_data, dict):
        if "nodes" in tree_data and isinstance(tree_data["nodes"], list):
            return [dict(node) for node in tree_data["nodes"]]
        return [dict(tree_data)]
    if isinstance(tree_data, Iterable) and not isinstance(tree_data, (str, bytes)):
        return [dict(node) for node in tree_data]
    raise TypeError("tree_data must be a node mapping or iterable of node mappings")


def _normalize_expansion_state(expansion_state: object) -> dict[str, bool]:
    if not isinstance(expansion_state, dict):
        return {}
    normalized: dict[str, bool] = {}
    for key, value in expansion_state.items():
        normalized[str(key)] = bool(value)
    return normalized


def _sorted_children(node: dict[str, object]) -> list[dict[str, object]]:
    children = node.get("children", [])
    if not isinstance(children, list):
        return []

    normalized = [dict(child) for child in children]
    normalized.sort(
        key=lambda child: (
            -int(child.get("compute_tier", 0) or 0),
            -int(child.get("compute_tally", 0) or 0),
            str(child.get("type", "")),
            str(child.get("name", child.get("id", ""))).lower(),
        )
    )
    return normalized


def _branch_key(node_id: str, column: int, start_y: int, visible_child_ids: list[str]) -> str:
    return f"{node_id}|{column}|{start_y}|{'/'.join(visible_child_ids)}"


def _visible_batch(children: list[dict[str, object]], node: dict[str, object]) -> list[dict[str, object]]:
    requested = node.get("loaded_children")
    if isinstance(requested, int) and requested > 0:
        return children[:requested]
    return children[:BATCH_SIZE]


def reserve_space(column_intervals: ColumnIntervalMap, column: int, start_y: int, height: int) -> dict[str, int]:
    interval = column_intervals.reserve(column, start_y, start_y + height)
    return {"column": column, "start_y": interval.start, "end_y": interval.end}


def place_node(
    column_intervals: ColumnIntervalMap,
    *,
    node_id: str,
    parent_id: str | None,
    column: int,
    x: int,
    preferred_y: int,
    width: int = NODE_WIDTH,
    height: int = NODE_HEIGHT,
    logger: logging.Logger | None = None,
) -> dict[str, object]:
    active_logger = logger or _get_logger()
    y = column_intervals.find_free_start(column, preferred_y, height)
    reservation = reserve_space(column_intervals, column, y, height)
    active_logger.debug(
        "node placement",
        extra={"node_id": node_id, "column": column, "preferred_y": preferred_y, "placed_y": y},
    )
    active_logger.debug(
        "space reservation",
        extra={"node_id": node_id, "column": column, "start_y": reservation["start_y"], "end_y": reservation["end_y"]},
    )
    return {
        "id": node_id,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "column": column,
        "parent_id": parent_id,
    }


def _reuse_cached_node(
    column_intervals: ColumnIntervalMap,
    cached_node: dict[str, object],
    reserved_regions: list[dict[str, int]],
    output_nodes: list[dict[str, object]],
) -> dict[str, object]:
    reserve_space(
        column_intervals,
        int(cached_node["column"]),
        int(cached_node["y"]),
        int(cached_node["height"]),
    )
    reserved_regions.append(
        {
            "column": int(cached_node["column"]),
            "start_y": int(cached_node["y"]),
            "end_y": int(cached_node["y"]) + int(cached_node["height"]),
        }
    )
    snapshot = dict(cached_node)
    output_nodes.append(snapshot)
    return snapshot


def _place_children(
    *,
    node: dict[str, object],
    parent_layout: dict[str, object],
    child_column: int,
    expansion_state: dict[str, bool],
    parent_index: dict[str, str],
    reserved_regions: list[dict[str, int]],
    output_nodes: list[dict[str, object]],
    column_intervals: ColumnIntervalMap,
    cache: LayoutCache,
    logger: logging.Logger,
) -> None:
    node_id = str(node["id"])
    children = _sorted_children(node)
    if not children:
        return

    batch = _visible_batch(children, node)
    if len(children) > len(batch):
        logger.debug("batch loading", extra={"node_id": node_id, "loaded": len(batch), "total": len(children)})

    visible_child_ids = [str(child["id"]) for child in batch]
    branch_key = _branch_key(node_id, child_column, int(parent_layout["y"]), visible_child_ids)
    cached_branch = cache.get_branch(branch_key)
    if cached_branch is None and all(child_id in cache.node_lookup for child_id in visible_child_ids):
        cached_branch = [dict(cache.node_lookup[child_id]) for child_id in visible_child_ids]

    if cached_branch is not None:
        for cached_node in cached_branch:
            _reuse_cached_node(column_intervals, cached_node, reserved_regions, output_nodes)

        for child in batch:
            child_id = str(child["id"])
            parent_index[child_id] = node_id
            if expansion_state.get(child_id) and child.get("type") == "folder":
                cached_layout = next((item for item in cached_branch if item["id"] == child_id), None)
                if cached_layout is not None:
                    _place_children(
                        node=child,
                        parent_layout=cached_layout,
                        child_column=max(int(cached_layout["column"]) + 1, 3),
                        expansion_state=expansion_state,
                        parent_index=parent_index,
                        reserved_regions=reserved_regions,
                        output_nodes=output_nodes,
                        column_intervals=column_intervals,
                        cache=cache,
                        logger=logger,
                    )
        return

    branch_nodes: list[dict[str, object]] = []
    x = child_column * COLUMN_WIDTH
    preferred_y = int(parent_layout["y"])

    for index, child in enumerate(batch):
        child_id = str(child["id"])
        parent_index[child_id] = node_id
        placement = place_node(
            column_intervals,
            node_id=child_id,
            parent_id=node_id,
            column=child_column,
            x=x,
            preferred_y=preferred_y + (index * NODE_HEIGHT),
            logger=logger,
        )
        branch_nodes.append(placement)
        output_nodes.append(placement)
        reserved_regions.append(
            {
                "column": child_column,
                "start_y": int(placement["y"]),
                "end_y": int(placement["y"]) + int(placement["height"]),
            }
        )

    cache.store_branch(branch_key, branch_nodes)

    for child in batch:
        child_id = str(child["id"])
        if expansion_state.get(child_id) and child.get("type") == "folder":
            child_layout = next(item for item in branch_nodes if item["id"] == child_id)
            _place_children(
                node=child,
                parent_layout=child_layout,
                child_column=max(int(child_layout["column"]) + 1, 3),
                expansion_state=expansion_state,
                parent_index=parent_index,
                reserved_regions=reserved_regions,
                output_nodes=output_nodes,
                column_intervals=column_intervals,
                cache=cache,
                logger=logger,
            )


def compute_layout(
    tree_data: object,
    expansion_state: object,
    parent_index: dict[str, str] | None,
    viewport_size: tuple[int, int] | dict[str, int] | None,
    grid_mode: bool = False,
) -> dict[str, object]:
    logger = _get_logger()
    logger.debug("layout start")

    expansion_map = _normalize_expansion_state(expansion_state)
    parent_lookup = parent_index if parent_index is not None else {}
    roots = _normalize_roots(tree_data)

    tree_changed = _SESSION_CACHE.set_project_tree(roots)
    expansion_changed = _SESSION_CACHE.mark_expansion_state(expansion_map)
    if tree_changed:
        _SESSION_INTERVALS.clear()

    if expansion_changed:
        logger.debug("layout start", extra={"expansion_changed": True})

    max_depth = _max_visible_depth(roots, expansion_map)
    if grid_mode or _SESSION_CACHE.grid_mode_locked or max_depth > GRID_FALLBACK_DEPTH:
        if max_depth > GRID_FALLBACK_DEPTH and not _SESSION_CACHE.grid_mode_locked:
            logger.debug("grid fallback", extra={"depth": max_depth})
        _SESSION_CACHE.grid_mode_locked = True
        flat_nodes = _flatten_visible_nodes(roots, expansion_map, parent_lookup)
        return compute_grid_layout(flat_nodes, viewport_size, logger=logger)

    placed_nodes: list[dict[str, object]] = []
    reserved_regions: list[dict[str, int]] = []

    for index, root in enumerate(_sorted_children({"children": roots})):
        node_id = str(root["id"])
        parent_lookup[node_id] = str(root.get("parent") or "")
        cached_root = _SESSION_CACHE.node_lookup.get(node_id)
        if cached_root is not None and int(cached_root.get("column", 0)) == 0:
            placement = _reuse_cached_node(_SESSION_INTERVALS, cached_root, reserved_regions, placed_nodes)
        else:
            placement = place_node(
                _SESSION_INTERVALS,
                node_id=node_id,
                parent_id=root.get("parent") if isinstance(root.get("parent"), str) else None,
                column=0,
                x=0,
                preferred_y=index * NODE_HEIGHT,
                logger=logger,
            )
            placed_nodes.append(placement)
            reserved_regions.append(
                {
                    "column": 0,
                    "start_y": int(placement["y"]),
                    "end_y": int(placement["y"]) + int(placement["height"]),
                }
            )
            _SESSION_CACHE.node_lookup[node_id] = dict(placement)

        if expansion_map.get(node_id) and root.get("type") == "folder":
            child_column = 1 if index % 2 == 0 else 2
            _place_children(
                node=root,
                parent_layout=placement,
                child_column=child_column,
                expansion_state=expansion_map,
                parent_index=parent_lookup,
                reserved_regions=reserved_regions,
                output_nodes=placed_nodes,
                column_intervals=_SESSION_INTERVALS,
                cache=_SESSION_CACHE,
                logger=logger,
            )

    return {"nodes": placed_nodes, "reserved_regions": reserved_regions, "grid_mode": False}


def _flatten_visible_nodes(
    roots: list[dict[str, object]],
    expansion_state: dict[str, bool],
    parent_index: dict[str, str],
) -> list[dict[str, object]]:
    flattened: list[dict[str, object]] = []

    def visit(node: dict[str, object], depth: int, parent_id: str | None) -> None:
        node_id = str(node["id"])
        parent_index[node_id] = parent_id or ""
        flattened.append(
            {
                "id": node_id,
                "parent_id": parent_id,
                "depth": depth,
                "width": NODE_WIDTH,
                "height": NODE_HEIGHT,
            }
        )
        if node.get("type") != "folder" or not expansion_state.get(node_id):
            return

        for child in _visible_batch(_sorted_children(node), node):
            visit(child, depth + 1, node_id)

    for root in _sorted_children({"children": roots}):
        visit(root, 0, None)

    return flattened


def _max_visible_depth(roots: list[dict[str, object]], expansion_state: dict[str, bool]) -> int:
    max_depth = 0

    def visit(node: dict[str, object], depth: int) -> None:
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        node_id = str(node["id"])
        if node.get("type") != "folder" or not expansion_state.get(node_id):
            return
        for child in _visible_batch(_sorted_children(node), node):
            visit(child, depth + 1)

    for root in _sorted_children({"children": roots}):
        visit(root, 0)

    return max_depth


def invalidate_layout_cache() -> None:
    clear_layout_cache(_SESSION_CACHE)
    _SESSION_INTERVALS.clear()
