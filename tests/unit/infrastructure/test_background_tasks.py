from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audioextender.infrastructure.background_tasks import BackgroundTaskRegistry


class BackgroundTaskRegistryTests(unittest.TestCase):
    def test_nested_updates_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tasks.json"
            registry = BackgroundTaskRegistry(path)
            registry["one"] = {"status": "processing", "progress": 0}
            registry["one"].update(progress=45)
            restored = BackgroundTaskRegistry(path)
            self.assertEqual(restored["one"]["progress"], 45)

    def test_processing_tasks_become_retryable_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tasks.json"
            registry = BackgroundTaskRegistry(path)
            registry["one"] = {"status": "processing", "stage": "Downloading"}
            restored = BackgroundTaskRegistry(path)
            self.assertEqual(restored["one"]["status"], "failed")
            self.assertTrue(restored["one"]["retryable"])
            self.assertIn("restart", restored["one"]["stage"])


if __name__ == "__main__":
    unittest.main()
