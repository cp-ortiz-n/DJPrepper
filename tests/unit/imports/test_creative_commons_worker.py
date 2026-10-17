from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audioextender.imports.creative_commons_worker import CreativeCommonsBatchWorker
from audioextender.infrastructure.background_tasks import BackgroundTaskRegistry


class CreativeCommonsBatchWorkerTests(unittest.TestCase):
    def test_offline_library_finishes_batch_with_actionable_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = BackgroundTaskRegistry(root / "tasks.json")
            registry["batch"] = {"id": "batch", "status": "processing"}

            def offline() -> Path:
                raise RuntimeError("Connect the configured drive")

            worker = CreativeCommonsBatchWorker(
                registry=registry,
                repository=object(),
                output=root,
                require_library_online=offline,
                safe_folder_name=str,
                generalized_genre=str,
                normalize_genre_category=str,
                safe_audio_name=str,
                duplicate_lookup=lambda _value: None,
                genre_path_parts=lambda value: [value],
                source_metadata_path=lambda path: path,
                cache_track_artwork=lambda _url, _path: "",
                write_wav_metadata=lambda *_args, **_kwargs: None,
                write_source_metadata=lambda _path, _metadata: None,
                best_youtube_match=lambda *_args: ({}, 0, ""),
                spotify_source_metadata=lambda _url: {},
                original_import_metadata=lambda *_args: {"genre": "", "genre_category": "Other"},
                match_factory=lambda **values: values,
            )

            worker.run("batch", [], "Offline playlist")
            state = registry["batch"]

        self.assertEqual("failed", state["status"])
        self.assertEqual("Music library disconnected", state["stage"])
        self.assertEqual("Connect the configured drive", state["error"])


if __name__ == "__main__":
    unittest.main()
