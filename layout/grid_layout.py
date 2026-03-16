from __future__ import annotations

import logging


def compute_grid_layout(
    nodes: list[dict[str, object]],
    viewport_size: tuple[int, int] | dict[str, int] | None,
    *,
    grid_columns: int = 4,
    cell_width: int = 264,
    cell_height: int = 222,
    logger: logging.Logger | None = None,
) -> dict[str, object]:
    active_logger = logger or logging.getLogger(__name__)
    active_logger.debug("grid fallback", extra={"node_count": len(nodes), "grid_columns": grid_columns})

    viewport_width = 0
    if isinstance(viewport_size, dict):
        viewport_width = int(viewport_size.get("width", 0))
    elif isinstance(viewport_size, tuple):
        viewport_width = int(viewport_size[0])

    effective_width = max(viewport_width, grid_columns * cell_width)
    horizontal_margin = max(24, (effective_width - (grid_columns * cell_width)) // 2)
    laid_out_nodes: list[dict[str, object]] = []

    for index, node in enumerate(nodes):
        row = index // grid_columns
        column = index % grid_columns
        laid_out_nodes.append(
            {
                **node,
                "x": horizontal_margin + (column * cell_width),
                "y": 32 + (row * cell_height),
                "width": cell_width,
                "height": cell_height,
                "column": column,
            }
        )

    reserved_regions = [
        {
            "column": column,
            "start_y": 32 + (row * cell_height),
            "end_y": 32 + ((row + 1) * cell_height),
        }
        for row in range((len(nodes) + grid_columns - 1) // grid_columns)
        for column in range(min(grid_columns, max(0, len(nodes) - (row * grid_columns))))
    ]

    return {"nodes": laid_out_nodes, "reserved_regions": reserved_regions, "grid_mode": True}
