from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from audioextender.imports.source_artwork import ArtworkSyncResult
from audioextender.infrastructure.batch_operations import BatchOperationRegistry
from audioextender.library.metadata_mutations import (
    TrackMetadataMutationDependencies,
    TrackMetadataMutationService,
    TrackMetadataUpdate,
)
from audioextender.persistence.facade import JobRepository
from audioextender.web.routes.metadata_batch_routes import MetadataBatchDependencies, MetadataBatchService


class TrackMetadataMutationTests(unittest.TestCase):
    def test_metadata_update_owns_move_tags_sidecar_catalog_and_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "Library"
            source = library / "Other" / "Track.wav"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"audio")
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(
                title="Track",
                artist="",
                file_path=source,
                genre="",
                genre_category="Other",
                playlist_name="Inbox",
            )
            tagged: list[tuple[Path, dict]] = []
            sidecars: list[tuple[Path, dict]] = []
            publications: list[bool] = []
            service = TrackMetadataMutationService(
                TrackMetadataMutationDependencies(
                    repository=repository,
                    normalize_genre=lambda value: value,
                    genre_directory=lambda value: library / value.replace(" / ", "/"),
                    music_library_root=lambda: library,
                    source_metadata_path=lambda path: path.with_suffix(".json"),
                    write_wav_metadata=lambda path, **values: tagged.append((path, values)),
                    write_source_metadata=lambda path, values: sidecars.append((path, values)),
                    cache_track_artwork=lambda *_args: "",
                    safe_audio_name=lambda value: value,
                    publish_catalog=lambda: publications.append(True),
                )
            )

            result = service.update_metadata(
                track_id,
                TrackMetadataUpdate(
                    title="Song",
                    artist="Artist",
                    genre="salsa, timba",
                    genre_category="Latin / Salsa",
                    playlist_name="Latin Set",
                    rename_file=True,
                ),
            )

            destination = library / "Latin" / "Salsa" / "Artist - Song.wav"
            track = repository.get_downloaded_track(track_id)
            assert track is not None
            self.assertTrue(destination.is_file())
            self.assertFalse(source.exists())
            self.assertEqual(track["file_path"], str(destination.resolve()))
            self.assertEqual(track["genre"], "salsa, timba")
            self.assertEqual(tagged[0][0], destination)
            self.assertEqual(sidecars[0][0], destination)
            self.assertEqual(publications, [True])
            self.assertEqual(result["file_path"], str(destination.resolve()))

    def test_existing_unavailable_artwork_does_not_block_unrelated_metadata_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Library" / "Latin" / "Reggaeton" / "Dr. Doctor.wav"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"audio")
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(
                title="Dr. Doctor",
                artist="Emi Blue and 2 more",
                file_path=source,
                genre="",
                genre_category="Latin / Reggaeton",
                playlist_name="Imported Singles",
            )
            artwork_url = "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e02dcb887304895f39e60f1fd6c"
            repository.update_downloaded_track_artwork(track_id, artwork_url=artwork_url, artwork_path="")
            service = TrackMetadataMutationService(
                TrackMetadataMutationDependencies(
                    repository=repository,
                    normalize_genre=lambda value: value,
                    genre_directory=lambda value: root / "Library" / value.replace(" / ", "/"),
                    music_library_root=lambda: root / "Library",
                    source_metadata_path=lambda path: path.with_suffix(".json"),
                    write_wav_metadata=lambda *_args, **_kwargs: None,
                    write_source_metadata=lambda *_args, **_kwargs: None,
                    cache_track_artwork=lambda *_args: "",
                    safe_audio_name=lambda value: value,
                    publish_catalog=lambda: None,
                )
            )

            result = service.update_metadata(
                track_id,
                TrackMetadataUpdate(
                    title="Dr. Doctor",
                    artist="Emi Blue and 2 more",
                    genre="reggaeton, latin pop",
                    genre_category="Latin / Reggaeton",
                    playlist_name="Imported Singles",
                    artwork_url=artwork_url,
                ),
            )

            self.assertTrue(result["updated"])
            self.assertEqual(result["artwork_url"], artwork_url)
            self.assertFalse(result["artwork_available"])
            stored = repository.get_downloaded_track(track_id)
            assert stored is not None
            self.assertEqual(stored["genre"], "reggaeton, latin pop")

    def test_new_unavailable_artwork_url_still_rejects_the_metadata_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Track.wav"
            source.write_bytes(b"audio")
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(
                title="Track", artist="Artist", file_path=source, genre="", genre_category="Other"
            )
            service = TrackMetadataMutationService(
                TrackMetadataMutationDependencies(
                    repository=repository,
                    normalize_genre=lambda value: value,
                    genre_directory=lambda _value: root,
                    music_library_root=lambda: root,
                    source_metadata_path=lambda path: path.with_suffix(".json"),
                    write_wav_metadata=lambda *_args, **_kwargs: None,
                    write_source_metadata=lambda *_args, **_kwargs: None,
                    cache_track_artwork=lambda *_args: "",
                    safe_audio_name=lambda value: value,
                    publish_catalog=lambda: None,
                )
            )

            with self.assertRaisesRegex(ValueError, "Artwork could not be downloaded"):
                service.update_metadata(
                    track_id,
                    TrackMetadataUpdate(title="Track", artwork_url="https://example.com/new.jpg"),
                )

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
                    cache_track_artwork=lambda *_args: "",
                    safe_audio_name=lambda value: value,
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
                    cache_track_artwork=lambda *_args: "",
                    safe_audio_name=lambda value: value,
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
                    source_artwork=Mock(),
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

    def test_artwork_batch_repairs_catalog_through_provider_independent_service(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "Track.wav"
            audio.write_bytes(b"audio")
            repository = Mock()
            source_artwork = Mock()
            source_artwork.sync_track.return_value = ArtworkSyncResult(
                "https://i1.sndcdn.com/art.jpg",
                str(root / ".artwork" / "art.jpg"),
                "soundcloud",
            )
            publications: list[bool] = []
            service = MetadataBatchService(
                MetadataBatchDependencies(
                    repository=lambda: repository,
                    require_library_online=Mock(),
                    sync_wav_metadata=Mock(),
                    read_wav_artwork=Mock(return_value=None),
                    embed_wav_artwork=Mock(),
                    source_artwork=source_artwork,
                    generalized_genre=Mock(),
                    normalize_genre=Mock(),
                    genre_directory=Mock(),
                    change_genre=Mock(),
                    publish_catalog=lambda: publications.append(True),
                    refresh_wav_tag_audit=Mock(),
                    schedule_wav_tag_audit_refresh=Mock(),
                    music_library_root=lambda: root,
                    registry=BatchOperationRegistry(),
                )
            )
            track = {
                "id": 7,
                "title": "SoundCloud Track",
                "filename": audio.name,
                "file_path": str(audio),
                "youtube_url": "https://soundcloud.com/dj/track",
                "youtube_id": "soundcloud:abc123",
                "artwork_path": "",
            }

            result = service._sync_artwork(Mock(), [track])

            self.assertEqual(result["updated"], 1)
            source_artwork.sync_track.assert_called_once_with(track, audio)
            repository.update_downloaded_track_artwork.assert_called_once_with(
                7,
                artwork_url="https://i1.sndcdn.com/art.jpg",
                artwork_path=str(root / ".artwork" / "art.jpg"),
            )
            self.assertEqual(publications, [True])


if __name__ == "__main__":
    unittest.main()
