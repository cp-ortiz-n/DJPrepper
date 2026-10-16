from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from audioextender.library.catalog_projection import CatalogProjectionPublisher


class RepositoryStub:
    def __init__(self) -> None:
        self.state: dict[str, str] = {}

    def library_index_source_signature(self) -> str:
        return '{"tracks":[1,"updated"]}'

    def set_system_state(self, key: str, value: str) -> None:
        self.state[key] = value


class CatalogProjectionPublisherTests(unittest.TestCase):
    def test_publish_invalidates_then_rebuilds_all_catalog_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "processing_report.json"
            catalog = root / "set_builder_catalog.json"
            report.write_text("{}", encoding="utf-8")
            catalog.write_text("stale", encoding="utf-8")
            memory = {"signature": "stale", "facets": {"genres": {"House": 1}}}
            repository = RepositoryStub()
            observations: list[tuple[dict, bool]] = []

            def rebuild() -> None:
                observations.append((dict(memory), catalog.exists()))
                catalog.write_text("current", encoding="utf-8")

            publisher = CatalogProjectionPublisher(
                repository=lambda: repository,
                rebuild=rebuild,
                report_path=lambda: report,
                catalog_path=lambda: catalog,
                memory_cache=memory,
                memory_cache_lock=threading.Lock(),
            )

            signature = publisher.publish()

            self.assertEqual(observations, [({}, False)])
            self.assertEqual(catalog.read_text(encoding="utf-8"), "current")
            self.assertEqual(memory, {"signature": signature})
            self.assertIn("library_search_index_signature", repository.state)

    def test_failed_rebuild_cannot_leave_stale_catalog_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "set_builder_catalog.json"
            catalog.write_text("stale", encoding="utf-8")
            memory = {"facets": {"genres": {"House": 1}}}

            def fail_rebuild() -> None:
                raise RuntimeError("rebuild failed")

            publisher = CatalogProjectionPublisher(
                repository=RepositoryStub,
                rebuild=fail_rebuild,
                report_path=lambda: Path(temporary) / "missing-report.json",
                catalog_path=lambda: catalog,
                memory_cache=memory,
                memory_cache_lock=threading.Lock(),
            )

            with self.assertRaisesRegex(RuntimeError, "rebuild failed"):
                publisher.publish()

            self.assertEqual(memory, {})
            self.assertFalse(catalog.exists())


if __name__ == "__main__":
    unittest.main()
