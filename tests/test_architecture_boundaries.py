"""Lightweight ratchets for the modular-monolith boundaries."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "audioextender"
DOMAIN_PACKAGES = {
    "analysis",
    "audio",
    "core",
    "imports",
    "infrastructure",
    "library",
    "processing",
    "reporting",
    "repositories",
    "set_builder",
}
SQL = re.compile(
    r"\b(?:SELECT\s+(?:\*|COUNT\s*\([^)]*\)|[\w, ]+)\s+FROM|INSERT\s+INTO|"
    r"UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+TABLE)\b",
    re.I,
)
LEGACY_SQL = {
    "audioextender/library/backup.py:SELECT COUNT(*) FROM downloaded_tracks",
}


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def internal_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    current = module_name(path).split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name.startswith("audioextender"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = current[: len(current) - node.level + 1]
                name = ".".join([*prefix, *(node.module or "").split(".")]).rstrip(".")
            else:
                name = node.module or ""
            if name.startswith("audioextender"):
                imports.add(name)
    return imports


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_internal_python_import_graph_is_acyclic(self) -> None:
        modules = {module_name(path): path for path in PACKAGE.rglob("*.py")}
        graph = {
            name: {candidate for imported in internal_imports(path) for candidate in modules if imported == candidate}
            for name, path in modules.items()
        }
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                cycle = " -> ".join([*visiting[visiting.index(name) :], name])
                self.fail(f"Internal import cycle: {cycle}")
            if name in visited:
                return
            visiting.append(name)
            for dependency in sorted(graph[name]):
                visit(dependency)
            visiting.pop()
            visited.add(name)

        for name in sorted(graph):
            visit(name)

    def test_domain_packages_do_not_import_web_delivery(self) -> None:
        violations = []
        for package in sorted(DOMAIN_PACKAGES):
            for path in (PACKAGE / package).rglob("*.py"):
                for imported in internal_imports(path):
                    if imported == "audioextender.web" or imported.startswith("audioextender.web."):
                        violations.append(f"{path.relative_to(ROOT)} -> {imported}")
        self.assertEqual([], violations)

    def test_sql_stays_inside_repository_boundary(self) -> None:
        violations = []
        for path in PACKAGE.rglob("*.py"):
            if "repositories" in path.relative_to(PACKAGE).parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL.search(node.value):
                    fingerprint = f"{path.relative_to(ROOT)}:{node.value.strip()}"
                    if fingerprint not in LEGACY_SQL:
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual([], violations)

    def test_known_architecture_hotspots_do_not_grow(self) -> None:
        ceilings = {
            "audioextender/web/application.py": 3692,
            "audioextender/processing/track_processor.py": 835,
            "audioextender/processing/track_processing_stages.py": 300,
            "audioextender/infrastructure/operation_lifecycle.py": 275,
            "audioextender/repositories/facade.py": 150,
            "audioextender/repositories/schema.py": 275,
            "web/app.js": 1548,
            "web/set-builder.js": 663,
        }
        for relative, maximum in ceilings.items():
            with self.subTest(relative=relative):
                actual = len((ROOT / relative).read_text(encoding="utf-8").splitlines())
                self.assertLessEqual(actual, maximum, f"{relative} grew from its Phase 0 baseline")

    def test_track_processor_process_complexity_does_not_grow(self) -> None:
        path = PACKAGE / "processing" / "track_processor.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "process")
        branches = sum(
            isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match, ast.BoolOp))
            for node in ast.walk(function)
        )
        self.assertIsNotNone(function.end_lineno)
        assert function.end_lineno is not None
        self.assertLessEqual(function.end_lineno - function.lineno + 1, 70)
        self.assertLessEqual(branches, 5)


if __name__ == "__main__":
    unittest.main()
