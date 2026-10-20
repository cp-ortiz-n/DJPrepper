from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.maintenance.clean_workspace import discover_cleanup_targets, remove_cleanup_targets, validate_project_root


class WorkspaceCleanupTests(unittest.TestCase):
    def make_repository(self, root: Path) -> None:
        (root / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
        (root / "audioextender").mkdir()

    def test_discovery_finds_only_known_generated_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            self.make_repository(root)
            generated = {
                root / ".coverage",
                root / ".DS_Store",
                root / "audioextender" / "__pycache__",
                root / "audioextender" / "module.pyc",
                root / "coverage",
            }
            for path in generated:
                if path.suffix or path.name.startswith("."):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("generated", encoding="utf-8")
                else:
                    path.mkdir()
            source = root / "audioextender" / "module.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")

            self.assertEqual(set(discover_cleanup_targets(root)), generated)
            self.assertTrue(source.exists())

    def test_removal_preserves_dependencies_inputs_outputs_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            self.make_repository(root)
            generated = root / "audioextender" / "__pycache__"
            generated.mkdir()
            (generated / "module.pyc").write_text("generated", encoding="utf-8")
            preserved = [
                root / ".venv" / "lib" / "__pycache__" / "dependency.pyc",
                root / "node_modules" / "package" / ".DS_Store",
                root / "workspace" / "input" / ".DS_Store",
                root / "workspace" / "output" / "render.pyc",
                root / "audioextender" / "module.py",
            ]
            for path in preserved:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("preserve", encoding="utf-8")

            remove_cleanup_targets(discover_cleanup_targets(root))

            self.assertFalse(generated.exists())
            for path in preserved:
                self.assertTrue(path.exists(), path)

    def test_analysis_cache_requires_explicit_opt_in_and_preserves_gitkeep(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            self.make_repository(root)
            cache_root = root / "workspace" / "cache"
            cache_root.mkdir(parents=True)
            gitkeep = cache_root / ".gitkeep"
            payload = cache_root / "analysis.json"
            nested = cache_root / "waveforms"
            gitkeep.touch()
            payload.write_text("{}", encoding="utf-8")
            nested.mkdir()

            self.assertNotIn(payload, discover_cleanup_targets(root))
            targets = discover_cleanup_targets(root, include_analysis_cache=True)
            self.assertIn(payload, targets)
            self.assertIn(nested, targets)
            self.assertNotIn(gitkeep, targets)

            remove_cleanup_targets(targets)
            self.assertTrue(gitkeep.exists())
            self.assertFalse(payload.exists())
            self.assertFalse(nested.exists())

    def test_invalid_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "Refusing cleanup"):
                validate_project_root(Path(temporary_directory))


if __name__ == "__main__":
    unittest.main()
