"""Guard the domain package layout against another flat-helper regression."""

from __future__ import annotations

import ast
import unittest

from tests.support.paths import PROJECT_ROOT

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
    "set_builder",
    "web",
}


class PackageStructureTests(unittest.TestCase):
    def test_test_suite_is_grouped_by_runtime_and_scope(self) -> None:
        tests = PROJECT_ROOT / "tests"
        expected = {"browser", "fixtures", "integration", "javascript", "support", "unit"}
        present = {path.name for path in tests.iterdir() if path.is_dir() and not path.name.startswith("__")}
        self.assertTrue(expected.issubset(present))
        self.assertEqual([], sorted(path.name for path in tests.glob("test_*.py")))
        self.assertEqual([], sorted(path.name for path in tests.glob("*.test.js")))

    def test_expected_domain_packages_exist(self) -> None:
        present = {path.name for path in PACKAGE_ROOT.iterdir() if path.is_dir() and (path / "__init__.py").is_file()}
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

    def test_web_composition_root_keeps_extracted_routes_out(self) -> None:
        source = (PROJECT_ROOT / "web_app.py").read_text(encoding="utf-8")
        application = (PACKAGE_ROOT / "web" / "application.py").read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 40)
        self.assertIn("audioextender.web import application", source)
        self.assertIn("def create_app(", application)
        self.assertIn("ApplicationRuntime", application)
        for route in (
            '@app.get("/api/jobs")',
            '@app.post("/api/jobs/reorder")',
            '@app.post("/api/jobs/clear")',
            '@app.get("/api/report-feedback")',
            '@app.get("/api/key-verifications")',
            '@app.get("/api/jobs/{job_id}/audio/{kind}")',
            '@app.get("/api/jobs/{job_id}/waveform/{kind}")',
            '@app.post("/api/jobs/{job_id}/transition-score")',
            '@app.get("/api/jobs/{job_id}/cues")',
            '@app.post("/api/library/download")',
            '@app.post("/api/downloaded-library/reconcile-files")',
            '@app.post("/api/downloaded-library/integrity-scan")',
            '@app.post("/api/downloaded-library/integrity-repair")',
        ):
            self.assertNotIn(route, application)

    def test_web_feature_modules_remain_bounded(self) -> None:
        routes = PACKAGE_ROOT / "web" / "routes"
        limits = {
            "job_routes.py": 240,
            "job_media_routes.py": 400,
            "reporting_routes.py": 320,
            "library_routes.py": 280,
            "library_maintenance_routes.py": 430,
            "set_builder_routes.py": 220,
        }
        for filename, maximum in limits.items():
            lines = (routes / filename).read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), maximum, filename)

    def test_wide_namespaces_use_owned_subpackages(self) -> None:
        frontend = PROJECT_ROOT / "web"
        self.assertEqual(
            {"app.js"},
            {path.name for path in frontend.glob("*.js")},
            "Browser feature modules belong under core/, shared/, or features/",
        )
        self.assertTrue((frontend / "core").is_dir())
        self.assertTrue((frontend / "shared").is_dir())
        self.assertTrue((frontend / "features").is_dir())

        repositories = PACKAGE_ROOT / "repositories"
        allowed_repository_modules = {"__init__.py", "base.py", "capabilities.py", "facade.py"}
        self.assertEqual(
            allowed_repository_modules,
            {path.name for path in repositories.glob("*.py")},
            "Persistence implementations belong to catalog/, jobs/, migrations/, or system/",
        )

        delivery = PACKAGE_ROOT / "web"
        allowed_delivery_modules = {"__init__.py", "application.py", "composition.py"}
        self.assertEqual(
            allowed_delivery_modules,
            {path.name for path in delivery.glob("*.py")},
            "HTTP delivery code belongs to routes/, contracts/, or assets/",
        )


if __name__ == "__main__":
    unittest.main()
