from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
import json


def _stable_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha1(encoded.encode("utf-8")).hexdigest()


@dataclass
class LayoutCache:
    project_signature: str | None = None
    expansion_signature: str | None = None
    grid_mode_locked: bool = False
    branch_positions: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    node_lookup: dict[str, dict[str, object]] = field(default_factory=dict)

    def set_project_tree(self, tree_data: object) -> bool:
        signature = _stable_digest(tree_data)
        if self.project_signature == signature:
            return False

        self.project_signature = signature
        self.expansion_signature = None
        self.grid_mode_locked = False
        self.branch_positions.clear()
        self.node_lookup.clear()
        return True

    def mark_expansion_state(self, expansion_state: object) -> bool:
        signature = _stable_digest(expansion_state)
        changed = self.expansion_signature is not None and self.expansion_signature != signature
        self.expansion_signature = signature
        return changed

    def get_branch(self, branch_key: str) -> list[dict[str, object]] | None:
        branch = self.branch_positions.get(branch_key)
        if branch is None:
            return None
        return [dict(node) for node in branch]

    def store_branch(self, branch_key: str, nodes: list[dict[str, object]]) -> None:
        snapshot = [dict(node) for node in nodes]
        self.branch_positions[branch_key] = snapshot
        for node in snapshot:
            self.node_lookup[str(node["id"])] = dict(node)

    def clear(self) -> None:
        self.project_signature = None
        self.expansion_signature = None
        self.grid_mode_locked = False
        self.branch_positions.clear()
        self.node_lookup.clear()


def invalidate_layout_cache(cache: LayoutCache) -> None:
    cache.clear()
