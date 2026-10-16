"""Lightweight ratchets for the modular-monolith boundaries."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from tests.support.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT
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
BROWSER_MUSICAL_PROFILE_OWNER = "web/dj-library.js"
BROWSER_MUSICAL_PROFILE_FUNCTIONS = {
    "camelotKey",
    "energyBand",
    "libraryRoles",
    "normalizedKey",
    "songEnergy",
    "timingProfile",
    "vocalProfile",
}


def module_name(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def internal_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    module_parts = module_name(path).split(".")
    current = module_parts if path.name == "__init__.py" else module_parts[:-1]
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
                imports.update(f"{name}.{alias.name}" for alias in node.names if alias.name != "*")
    return imports


def internal_dependency_graph() -> dict[str, set[str]]:
    modules = {module_name(path): path for path in PACKAGE.rglob("*.py")}
    return {
        name: {imported for imported in internal_imports(path) if imported in modules and imported != name}
        for name, path in modules.items()
    }


def browser_function_definitions(source: str) -> set[str]:
    """Return named declarations relevant to browser policy ownership checks."""
    function_names = re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", source)
    assigned_names = re.findall(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
        source,
    )
    return {*function_names, *assigned_names}


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_internal_python_import_graph_is_acyclic(self) -> None:
        graph = internal_dependency_graph()
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
        observed_legacy = set()
        for path in PACKAGE.rglob("*.py"):
            if "repositories" in path.relative_to(PACKAGE).parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQL.search(node.value):
                    fingerprint = f"{path.relative_to(ROOT)}:{node.value.strip()}"
                    if fingerprint in LEGACY_SQL:
                        observed_legacy.add(fingerprint)
                    else:
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual([], violations)
        self.assertEqual(LEGACY_SQL, observed_legacy, "Remove obsolete SQL exceptions when legacy debt is retired")

    def test_browser_musical_profile_derivation_has_one_owner(self) -> None:
        violations = []
        owner_path = ROOT / BROWSER_MUSICAL_PROFILE_OWNER
        owner_source = owner_path.read_text(encoding="utf-8")
        self.assertTrue(
            BROWSER_MUSICAL_PROFILE_FUNCTIONS <= browser_function_definitions(owner_source),
            "The declared browser musical-profile owner must retain the compatibility API",
        )
        for path in (ROOT / "web").rglob("*.js"):
            relative = str(path.relative_to(ROOT))
            if relative == BROWSER_MUSICAL_PROFILE_OWNER:
                continue
            source = path.read_text(encoding="utf-8")
            duplicated = BROWSER_MUSICAL_PROFILE_FUNCTIONS & browser_function_definitions(source)
            if duplicated:
                violations.append(f"{relative}: duplicated {', '.join(sorted(duplicated))}")
            if re.search(r"\b(?:const|let|var)\s+CAMELOT_KEYS\b", source):
                violations.append(f"{relative}: duplicated Camelot map")
            if re.search(r"\bmusical_profile\s*(?:\?\.|\.|\[)", source):
                violations.append(f"{relative}: reads serialized musical profile directly")
        self.assertEqual(
            [],
            violations,
            f"Consume profile helpers from {BROWSER_MUSICAL_PROFILE_OWNER}; do not recreate browser derivation",
        )

    def test_known_architecture_hotspots_do_not_grow(self) -> None:
        ceilings = {
            "audioextender/web/application.py": 3615,
            "audioextender/processing/track_processor.py": 829,
            "audioextender/processing/track_processing_stages.py": 289,
            "audioextender/infrastructure/operation_lifecycle.py": 246,
            "audioextender/repositories/facade.py": 127,
            "audioextender/repositories/schema.py": 248,
            "web/app.js": 918,
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
