from __future__ import annotations

import ast
import os
from pathlib import Path

try:
    from backend.core.graph_engine.graph_manager import GraphManager
except ModuleNotFoundError:
    from core.graph_engine.graph_manager import GraphManager


IGNORED_DIRECTORIES = {".git", "venv", "__pycache__", "node_modules"}


class PythonRepoScanner:
    def __init__(self, graph_manager: GraphManager, repo_path: str | Path) -> None:
        self.graph_manager = graph_manager
        self.repo_path = Path(repo_path).resolve()
        self.repository_node_id = self.repo_path.name
        self.parsed_trees: dict[str, ast.AST] = {}
        self.module_map: dict[str, str] = {}
        self.package_map: dict[str, str] = {}
        self.function_name_index: dict[str, list[str]] = {}

    def scan(self) -> None:
        self.graph_manager.clear()
        self.parsed_trees.clear()
        self.module_map.clear()
        self.package_map.clear()
        self.function_name_index.clear()
        self._ensure_repository_node()

        python_files = self._collect_python_files()
        for file_path in python_files:
            self._register_module_node(file_path)

        for file_path in python_files:
            self._scan_module_structure(file_path)

        for file_path in python_files:
            self._scan_imports(file_path)
            self._scan_function_calls(file_path)

    def _ensure_repository_node(self) -> None:
        if not self.graph_manager.has_node(self.repository_node_id):
            self.graph_manager.add_node(
                self.repository_node_id,
                self.repo_path.name,
                "subsystem",
            )

    def _collect_python_files(self) -> list[Path]:
        python_files: list[Path] = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [directory for directory in dirs if directory not in IGNORED_DIRECTORIES]
            for filename in files:
                if filename.endswith(".py"):
                    python_files.append(Path(root) / filename)
        return sorted(python_files)

    def _register_module_node(self, file_path: Path) -> None:
        tree = self._parse_file(file_path)
        if tree is None:
            return

        relative_path = file_path.relative_to(self.repo_path).as_posix()
        module_name = self._module_name_for_path(file_path)
        module_has_code = self._module_has_code(tree)

        if not module_has_code:
            return

        self.graph_manager.add_node(
            relative_path,
            file_path.stem,
            "module",
            parent=self.repository_node_id,
            file_path=relative_path,
            line_number=1,
        )

        self.module_map[module_name] = relative_path
        package_name = self._package_name_for_path(file_path)
        if package_name:
            self.package_map[package_name] = relative_path

    def _scan_imports(self, file_path: Path) -> None:
        relative_path = file_path.relative_to(self.repo_path).as_posix()
        if not self.graph_manager.has_node(relative_path):
            return

        tree = self._parse_file(file_path)
        if tree is None:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = self._resolve_import_target(alias.name)
                    if target is not None:
                        self.graph_manager.add_edge(relative_path, target, "imports")

            if isinstance(node, ast.ImportFrom):
                imported_modules = self._resolve_from_import_targets(file_path, node)
                for target in imported_modules:
                    self.graph_manager.add_edge(relative_path, target, "imports")

    def _scan_module_structure(self, file_path: Path) -> None:
        module_id = file_path.relative_to(self.repo_path).as_posix()
        if not self.graph_manager.has_node(module_id):
            return

        tree = self._parse_file(file_path)
        if tree is None:
            return

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_id = f"{module_id}::{node.name}"
                self.graph_manager.add_node(
                    class_id,
                    node.name,
                    "class",
                    parent=module_id,
                    file_path=module_id,
                    line_number=node.lineno,
                )
                self.graph_manager.add_edge(module_id, class_id, "contains")

            if isinstance(node, ast.FunctionDef):
                function_id = f"{module_id}::{node.name}"
                self.graph_manager.add_node(
                    function_id,
                    node.name,
                    "function",
                    parent=module_id,
                    file_path=module_id,
                    line_number=node.lineno,
                )
                self.graph_manager.add_edge(module_id, function_id, "contains")
                self.function_name_index.setdefault(node.name, []).append(function_id)

    def _scan_function_calls(self, file_path: Path) -> None:
        module_id = file_path.relative_to(self.repo_path).as_posix()
        if not self.graph_manager.has_node(module_id):
            return

        tree = self._parse_file(file_path)
        if tree is None:
            return

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue

            source_function_id = f"{module_id}::{node.name}"
            for called_name in self._collect_direct_calls(node):
                for target_function_id in self.function_name_index.get(called_name, []):
                    self.graph_manager.add_edge(source_function_id, target_function_id, "calls")

    def _parse_file(self, file_path: Path) -> ast.AST | None:
        cache_key = file_path.relative_to(self.repo_path).as_posix()
        if cache_key in self.parsed_trees:
            return self.parsed_trees[cache_key]

        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return None

        self.parsed_trees[cache_key] = tree
        return tree

    def _module_has_code(self, tree: ast.AST) -> bool:
        for node in getattr(tree, "body", []):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                return True
        return False

    def _collect_direct_calls(self, function_node: ast.FunctionDef) -> set[str]:
        called_names: set[str] = set()
        for statement in function_node.body:
            called_names.update(self._collect_calls_from_node(statement))

        return called_names

    def _collect_calls_from_node(self, node: ast.AST) -> set[str]:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return set()

        called_names: set[str] = set()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called_names.add(node.func.id)

        for child in ast.iter_child_nodes(node):
            called_names.update(self._collect_calls_from_node(child))

        return called_names

    def _resolve_import_target(self, module_name: str) -> str | None:
        candidate = module_name
        while candidate:
            if candidate in self.module_map:
                return self.module_map[candidate]
            if candidate in self.package_map:
                return self.package_map[candidate]
            if "." not in candidate:
                break
            candidate = candidate.rsplit(".", 1)[0]
        return None

    def _resolve_from_import_targets(self, file_path: Path, node: ast.ImportFrom) -> list[str]:
        base_module = self._resolve_base_module(file_path, node.module, node.level)
        targets: list[str] = []

        if base_module:
            base_target = self._resolve_import_target(base_module)
            if base_target is not None:
                targets.append(base_target)

        for alias in node.names:
            if alias.name == "*":
                continue

            if base_module:
                candidate = f"{base_module}.{alias.name}"
            else:
                candidate = alias.name

            target = self._resolve_import_target(candidate)
            if target is not None:
                targets.append(target)

        return targets

    def _resolve_base_module(
        self,
        file_path: Path,
        module_name: str | None,
        level: int,
    ) -> str:
        if level == 0:
            return module_name or ""

        current_module = self._module_name_for_path(file_path)
        package_parts = current_module.split(".")[:-1]
        parent_depth = max(len(package_parts) - (level - 1), 0)
        base_parts = package_parts[:parent_depth]

        if module_name:
            base_parts.extend(module_name.split("."))

        return ".".join(part for part in base_parts if part)

    def _module_name_for_path(self, file_path: Path) -> str:
        relative_path = file_path.relative_to(self.repo_path)
        parts = list(relative_path.parts)
        parts[-1] = Path(parts[-1]).stem

        if parts[-1] == "__init__":
            parts = parts[:-1]

        return ".".join(parts)

    def _package_name_for_path(self, file_path: Path) -> str:
        relative_path = file_path.relative_to(self.repo_path)
        if relative_path.name != "__init__.py":
            return ""
        return ".".join(relative_path.parts[:-1])
