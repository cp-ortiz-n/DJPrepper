"""Guard the domain package layout against another flat-helper regression."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "audioextender"
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
}


class PackageStructureTests(unittest.TestCase):
    def test_expected_domain_packages_exist(self) -> None:
        present = {
            path.name
            for path in PACKAGE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }
        self.assertEqual(DOMAIN_PACKAGES, present)

    def test_legacy_helpers_contains_no_source_modules(self) -> None:
        helpers = PROJECT_ROOT / "helpers"
        self.assertFalse(helpers.exists() and any(helpers.rglob("*.py")))

    def test_application_package_never_imports_legacy_helpers(self) -> None:
        violations: list[str] = []
        for source in PACKAGE_ROOT.rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("helpers"):
                    violations.append(f"{source.relative_to(PROJECT_ROOT)}:{node.lineno}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("helpers"):
                            violations.append(f"{source.relative_to(PROJECT_ROOT)}:{node.lineno}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
