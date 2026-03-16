from __future__ import annotations

import ast
import os
from pathlib import Path

try:
    from backend.core.graph_engine.graph_manager import GraphManager
except ModuleNotFoundError:
    from core.graph_engine.graph_manager import GraphManager


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}


def analyze_function(function_node: ast.AST) -> tuple[int, set[str]]:
    loops = 0
    branches = 0
    calls = 0
    direct_calls: set[str] = set()

    def visit(node: ast.AST) -> None:
        nonlocal loops, branches, calls
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not function_node:
            return
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            loops += 1
        elif isinstance(node, ast.If):
            branches += 1
        elif isinstance(node, ast.Call):
            calls += 1
            if isinstance(node.func, ast.Name):
                direct_calls.add(node.func.id)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(function_node)
    return (loops * 3) + (branches * 2) + calls, direct_calls


class PythonRepoScanner:
    def __init__(
        self,
        graph_manager: GraphManager,
        repo_path: str | Path,
        include_prefixes: list[str] | None = None,
    ) -> None:
        self.graph_manager = graph_manager
        self.repo_path = Path(repo_path).resolve()
        self.include_prefixes = sorted(Path(prefix).as_posix().strip("/") for prefix in (include_prefixes or []) if str(prefix).strip())
        self.repository_node_id = self.repo_path.name
        self.parsed_trees: dict[str, ast.AST] = {}
        self.source_texts: dict[str, str] = {}
        self.module_map: dict[str, str] = {}
        self.package_map: dict[str, str] = {}
        self.function_name_index: dict[str, list[str]] = {}
        self.pending_call_edges: dict[str, set[str]] = {}
        self._static_file_records: dict[str, dict[str, object]] = {}

    def scan(self) -> None:
        self.graph_manager.clear()
        self.parsed_trees.clear()
        self.source_texts.clear()
        self.module_map.clear()
        self.package_map.clear()
        self.function_name_index.clear()
        self.pending_call_edges.clear()
        self._static_file_records.clear()
        self._ensure_repository_node()

        python_files = self._collect_python_files()
        for file_path in python_files:
            self._register_module_node(file_path)
            self._capture_static_file_record(file_path)

        for file_path in python_files:
            self._scan_file(file_path)

        self._resolve_pending_call_edges()

    def static_file_records(self) -> list[dict[str, object]]:
        return [dict(self._static_file_records[key]) for key in sorted(self._static_file_records)]

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
                    file_path = Path(root) / filename
                    relative_path = file_path.relative_to(self.repo_path).as_posix()
                    if self._include_relative_path(relative_path):
                        python_files.append(file_path)
        return sorted(python_files)

    def _include_relative_path(self, relative_path: str) -> bool:
        if not self.include_prefixes:
            return True
        normalized = Path(relative_path).as_posix()
        return any(normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in self.include_prefixes)

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

    def _scan_file(self, file_path: Path) -> None:
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

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_id = f"{relative_path}::{node.name}"
                self.graph_manager.add_node(
                    class_id,
                    node.name,
                    "class",
                    parent=relative_path,
                    file_path=relative_path,
                    line_number=node.lineno,
                )
                self.graph_manager.add_edge(relative_path, class_id, "contains")

            if isinstance(node, ast.FunctionDef):
                function_id = f"{relative_path}::{node.name}"
                complexity_score, direct_calls = analyze_function(node)
                self.graph_manager.add_node(
                    function_id,
                    node.name,
                    "function",
                    parent=relative_path,
                    file_path=relative_path,
                    line_number=node.lineno,
                )
                self.graph_manager.set_metadata(
                    function_id,
                    "compute_score",
                    complexity_score,
                )
                self.graph_manager.set_metadata(
                    function_id,
                    "line_start",
                    node.lineno,
                )
                self.graph_manager.set_metadata(
                    function_id,
                    "line_end",
                    getattr(node, "end_lineno", node.lineno),
                )
                self.graph_manager.add_edge(relative_path, function_id, "contains")
                self.function_name_index.setdefault(node.name, []).append(function_id)
                self.pending_call_edges[function_id] = direct_calls

    def _parse_file(self, file_path: Path) -> ast.AST | None:
        cache_key = file_path.relative_to(self.repo_path).as_posix()
        if cache_key in self.parsed_trees:
            return self.parsed_trees[cache_key]

        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeDecodeError):
            return None

        self.source_texts[cache_key] = source
        self.parsed_trees[cache_key] = tree
        return tree

    def _capture_static_file_record(self, file_path: Path) -> None:
        relative_path = file_path.relative_to(self.repo_path).as_posix()
        tree = self._parse_file(file_path)
        if tree is None:
            return
        source = self.source_texts.get(relative_path, "")
        imports: list[str] = []
        callable_count = 0
        class_count = 0
        framework_markers: set[str] = set()
        optional_imports: set[str] = set()
        native_imports: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
                    top_level = alias.name.split(".", 1)[0]
                    if top_level in {"AVFoundation", "AppKit", "Cocoa", "CoreAudio", "CoreFoundation", "CoreGraphics", "Foundation", "PySide6", "PyQt5", "PyQt6", "cv2", "numpy", "pandas", "torch"}:
                        native_imports.add(top_level)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
                    top_level = node.module.split(".", 1)[0]
                    if top_level in {"AVFoundation", "AppKit", "Cocoa", "CoreAudio", "CoreFoundation", "CoreGraphics", "Foundation", "PySide6", "PyQt5", "PyQt6", "cv2", "numpy", "pandas", "torch"}:
                        native_imports.add(top_level)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                callable_count += 1
            elif isinstance(node, ast.ClassDef):
                class_count += 1
            elif isinstance(node, ast.Try):
                for guarded in node.body:
                    if isinstance(guarded, ast.Import):
                        for alias in guarded.names:
                            optional_imports.add(alias.name.split(".", 1)[0])
                    elif isinstance(guarded, ast.ImportFrom) and guarded.module:
                        optional_imports.add(guarded.module.split(".", 1)[0])

        lowered = source.lower()
        if "qapplication(" in lowered or "pyside6" in lowered or "pyqt" in lowered:
            framework_markers.add("qt")
        if "fastapi(" in lowered or "from fastapi" in lowered:
            framework_markers.add("fastapi")
        if "flask(" in lowered or "from flask" in lowered:
            framework_markers.add("flask")
        if "argparse" in lowered or "click.command" in lowered or "typer.typer" in lowered:
            framework_markers.add("cli")

        self._static_file_records[relative_path] = {
            "path": relative_path,
            "imports": sorted(set(imports)),
            "has_main_guard": "__name__ == \"__main__\"" in source or "__name__ == '__main__'" in source,
            "callable_count": callable_count,
            "class_count": class_count,
            "framework_markers": sorted(framework_markers),
            "optional_imports": sorted(optional_imports),
            "native_imports": sorted(native_imports),
        }

    def _module_has_code(self, tree: ast.AST) -> bool:
        for node in getattr(tree, "body", []):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                return True
        return False

    def _resolve_pending_call_edges(self) -> None:
        for source_function_id, called_names in self.pending_call_edges.items():
            for called_name in called_names:
                for target_function_id in self.function_name_index.get(called_name, []):
                    self.graph_manager.add_edge(source_function_id, target_function_id, "calls")

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
