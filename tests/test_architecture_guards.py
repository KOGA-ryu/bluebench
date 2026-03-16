from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent


class ArchitectureGuardTests(unittest.TestCase):
    def test_derive_does_not_depend_on_adapters_or_reports(self) -> None:
        violations = _collect_import_violations(
            REPO_ROOT / "backend" / "derive",
            forbidden_prefixes=("backend.adapters", "backend.reports", "backend.main", "backend.stress_engine"),
        )
        self.assertEqual(violations, [])

    def test_reports_do_not_import_hotspot_or_comparison_logic_directly(self) -> None:
        violations = _collect_import_violations(
            REPO_ROOT / "backend" / "reports",
            forbidden_prefixes=("backend.derive.hotspot_ranker", "backend.derive.run_comparator"),
        )
        self.assertEqual(violations, [])

    def test_codex_adapters_do_not_depend_on_ui_surfaces(self) -> None:
        violations = _collect_import_violations(
            REPO_ROOT / "backend" / "adapters" / "codex",
            forbidden_prefixes=("backend.main", "backend.stress_engine", "backend.triage_window"),
        )
        self.assertEqual(violations, [])


def _collect_import_violations(root: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module_name: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    if _matches_forbidden(module_name, forbidden_prefixes):
                        violations.append(f"{path.relative_to(REPO_ROOT)} imports {module_name}")
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module
                if module_name and _matches_forbidden(module_name, forbidden_prefixes):
                    violations.append(f"{path.relative_to(REPO_ROOT)} imports {module_name}")
    return violations


def _matches_forbidden(module_name: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    return any(module_name == prefix or module_name.startswith(prefix + ".") for prefix in forbidden_prefixes)


if __name__ == "__main__":
    unittest.main()
