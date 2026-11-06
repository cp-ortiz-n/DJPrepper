"""Tests for deterministic process runtime identity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audioextender.infrastructure.runtime_revision import RuntimeRevision


class RuntimeRevisionTests(unittest.TestCase):
    def test_revision_changes_for_backend_frontend_content_and_source_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            backend = project / "audioextender" / "service.py"
            frontend = project / "frontend" / "app.js"
            backend.parent.mkdir()
            frontend.parent.mkdir()
            backend.write_text("VALUE = 1\n", encoding="utf-8")
            frontend.write_text("export const value = 1;\n", encoding="utf-8")
            initial = RuntimeRevision.capture(project)

            backend.write_text("VALUE = 2\n", encoding="utf-8")
            backend_change = RuntimeRevision.capture(project)
            frontend.write_text("export const value = 2;\n", encoding="utf-8")
            frontend_change = RuntimeRevision.capture(project)
            backend.rename(backend.with_name("renamed.py"))
            path_change = RuntimeRevision.capture(project)

        self.assertEqual(initial.file_count, 2)
        self.assertEqual(len({initial.value, backend_change.value, frontend_change.value, path_change.value}), 4)

    def test_revision_ignores_generated_and_runtime_data_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "audioextender" / "service.py"
            source.parent.mkdir()
            source.write_text("VALUE = 1\n", encoding="utf-8")
            initial = RuntimeRevision.capture(project)

            (source.parent / "service.pyc").write_bytes(b"generated")
            workspace = project / "workspace" / "output"
            workspace.mkdir(parents=True)
            (workspace / "catalog.json").write_text("{}", encoding="utf-8")
            after_runtime_writes = RuntimeRevision.capture(project)

        self.assertEqual(initial, after_runtime_writes)

    def test_captured_revision_remains_immutable_after_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "audioextender" / "service.py"
            source.parent.mkdir()
            source.write_text("VALUE = 1\n", encoding="utf-8")
            running_process_revision = RuntimeRevision.capture(project)

            source.write_text("VALUE = 2\n", encoding="utf-8")
            checkout_revision = RuntimeRevision.capture(project)

        self.assertNotEqual(running_process_revision.value, checkout_revision.value)
        self.assertEqual(running_process_revision.file_count, checkout_revision.file_count)


if __name__ == "__main__":
    unittest.main()
