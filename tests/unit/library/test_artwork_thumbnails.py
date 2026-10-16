from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from audioextender.library.artwork_thumbnails import ArtworkThumbnailService


class DeferredThread:
    created: list[DeferredThread] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started = False
        self.created.append(self)

    def start(self) -> None:
        self.started = True


class ArtworkThumbnailServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        DeferredThread.created.clear()

    def test_repeated_cache_miss_starts_only_one_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "cover.jpg"
            source.write_bytes(b"image")
            observations: list[tuple[str, bool]] = []
            service = ArtworkThumbnailService(
                thumbnail_root=lambda: root / "thumbnails",
                record_cache_result=lambda name, hit: observations.append((name, hit)),
                thread_factory=DeferredThread,
            )

            self.assertEqual(source, service.get_or_queue(source))
            self.assertEqual(source, service.get_or_queue(source))

        self.assertEqual([("artwork_thumbnail", False)] * 2, observations)
        self.assertEqual(1, len(DeferredThread.created))
        self.assertTrue(DeferredThread.created[0].started)


if __name__ == "__main__":
    unittest.main()
