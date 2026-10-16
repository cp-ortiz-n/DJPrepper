from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from audioextender.infrastructure.batch_operations import BatchOperationRegistry
from audioextender.library.metadata_mutations import (
    TrackMetadataMutationDependencies,
    TrackMetadataMutationService,
)
from audioextender.repositories.facade import JobRepository
from audioextender.web.metadata_batch_routes import MetadataBatchDependencies, MetadataBatchService


class TrackMetadataMutationTests(unittest.TestCase):
    def test_genre_change_publishes_after_catalog_and_files_are_updated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "Library"
            source = library / "Other" / "Track.wav"
            source.parent.mkdir(parents=True)
            source.touch()
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(
                title="Track", artist="Artist", file_path=source, genre="", genre_category="Other"
            )
            published: list[dict] = []

            def publish() -> None:
                published.append(repository.get_downloaded_track(track_id) or {})

            service = TrackMetadataMutationService(
                TrackMetadataMutationDependencies(
                    repository=repository,
                    normalize_genre=lambda value: value,
                    genre_directory=lambda value: library / value,
                    music_library_root=lambda: library,
                    source_metadata_path=lambda path: path.with_suffix(".json"),
                    write_wav_metadata=lambda *_args, **_kwargs: None,
                    write_source_metadata=lambda *_args, **_kwargs: None,
                    publish_catalog=publish,
                )
            )

            result = service.change_genre([track_id], "Latin")

            destination = library / "Latin" / source.name
            self.assertEqual(result, {"updated": 1, "genre_category": "Latin"})
            self.assertTrue(destination.is_file())
            self.assertEqual(published[0]["file_path"], str(destination.resolve()))
            self.assertEqual(published[0]["genre_category"], "Latin")

    def test_batch_owned_genre_change_can_defer_one_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Track.wav"
            source.touch()
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(
                title="Track", artist="Artist", file_path=source, genre="", genre_category="Other"
            )
            publications: list[bool] = []
            service = TrackMetadataMutationService(
                TrackMetadataMutationDependencies(
                    repository=repository,
                    normalize_genre=lambda value: value,
                    genre_directory=lambda value: root / value,
                    music_library_root=lambda: root,
                    source_metadata_path=lambda path: path.with_suffix(".json"),
                    write_wav_metadata=lambda *_args, **_kwargs: None,
                    write_source_metadata=lambda *_args, **_kwargs: None,
                    publish_catalog=lambda: publications.append(True),
                )
            )

            service.change_genre([track_id], "Latin", publish=False)

            self.assertEqual(publications, [])

    def test_genre_batch_defers_changes_and_publishes_once_at_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publications: list[bool] = []
            changes: list[tuple[list[int], str]] = []

            def change_genre(ids: list[int], genre: str) -> dict:
                changes.append((ids, genre))
                return {"updated": len(ids)}

            service = MetadataBatchService(
                MetadataBatchDependencies(
                    repository=Mock,
                    require_library_online=Mock(),
                    sync_wav_metadata=Mock(),
                    read_wav_artwork=Mock(),
                    embed_wav_artwork=Mock(),
                    cache_track_artwork=Mock(),
                    spotify_source_metadata=Mock(),
                    generalized_genre=lambda _value: "Latin",
                    normalize_genre=lambda value: str(value),
                    genre_directory=lambda value: root / value,
                    change_genre=change_genre,
                    publish_catalog=lambda: publications.append(True),
                    refresh_wav_tag_audit=Mock(),
                    schedule_wav_tag_audit_refresh=Mock(),
                    music_library_root=lambda: root,
                    registry=BatchOperationRegistry(),
                )
            )
            context = Mock()
            tracks = [
                {"id": 1, "file_path": str(root / "One.wav"), "filename": "One.wav", "genre": "latin"},
                {"id": 2, "file_path": str(root / "Two.wav"), "filename": "Two.wav", "genre": "latin"},
            ]

            result = service._rescan_genres(context, tracks)

            self.assertEqual(result["updated"], 2)
            self.assertEqual(changes, [([1], "Latin"), ([2], "Latin")])
            self.assertEqual(publications, [True])


if __name__ == "__main__":
    unittest.main()
