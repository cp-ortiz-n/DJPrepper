from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.web.downloaded_track_mutation_routes import (
    DownloadedTrackMutationDependencies,
    DownloadedTrackMutationService,
    create_downloaded_track_mutation_router,
)


class DownloadedTrackMutationRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = Mock()
        self.metadata = Mock()
        self.batches = Mock()
        self.original_metadata = Mock(return_value={"genre": "Salsa", "genre_category": "Latin / Salsa"})
        self.service = DownloadedTrackMutationService(
            DownloadedTrackMutationDependencies(
                repository=lambda: self.repository,
                metadata=self.metadata,
                metadata_batches=self.batches,
                genre_directory=lambda genre: self.root / genre,
                original_import_metadata=self.original_metadata,
                database_path=lambda: self.root / "catalog.sqlite3",
            )
        )
        app = FastAPI()
        app.include_router(create_downloaded_track_mutation_router(self.service))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_delete_single_and_bulk_preserve_result_contracts(self) -> None:
        self.repository.delete_downloaded_track.side_effect = lambda track_id: track_id != 2
        single = self.client.delete("/api/downloaded-library/tracks/1")
        bulk = self.client.request("DELETE", "/api/downloaded-library/tracks", json={"track_ids": [1, 2, 2]})
        missing = self.client.delete("/api/downloaded-library/tracks/2")
        self.assertEqual(single.json(), {"removed": True, "track_id": 1})
        self.assertEqual(bulk.json(), {"removed": 1, "requested": 2})
        self.assertEqual(missing.status_code, 404)

    def test_genre_and_metadata_routes_delegate_to_atomic_mutation_service(self) -> None:
        self.metadata.change_genre.return_value = {"updated": 2, "genre_category": "Latin / Salsa"}
        self.metadata.update_metadata.return_value = {
            "updated": True,
            "track_id": 4,
            "title": "Song",
            "artist": "Artist",
            "genre": "Salsa",
            "genre_category": "Latin / Salsa",
            "playlist_name": "Party",
            "filename": "Artist - Song.wav",
            "artwork_url": "",
            "artwork_available": False,
            "file_path": str(self.root / "Artist - Song.wav"),
            "sidecar_path": str(self.root / "Artist - Song.json"),
        }
        genre = self.client.patch(
            "/api/downloaded-library/genre",
            json={"track_ids": [4, 5], "genre_category": "Latin / Salsa"},
        )
        metadata = self.client.patch(
            "/api/downloaded-library/tracks/4/metadata",
            json={
                "title": "Song",
                "artist": "Artist",
                "genre": "Salsa",
                "genre_category": "Latin / Salsa",
                "playlist_name": "Party",
            },
        )
        self.assertEqual(genre.status_code, 200)
        self.assertTrue(genre.json()["receipt"]["survives_restart"])
        self.assertEqual(metadata.status_code, 200)
        self.assertNotIn("file_path", metadata.json())
        self.assertEqual(self.metadata.update_metadata.call_args.args[0], 4)

    def test_playlist_genre_repair_uses_injected_source_metadata_and_atomic_update(self) -> None:
        wav = self.root / "Song.wav"
        wav.touch()
        self.repository.list_downloaded_tracks.return_value = [
            {
                "id": 7,
                "title": "Song",
                "artist": "Artist",
                "genre": "Latin Party",
                "genre_category": "Other",
                "playlists": ["latin_party"],
                "file_path": str(wav),
            }
        ]
        self.metadata.update_metadata.return_value = {
            "updated": True,
            "track_id": 7,
            "title": "Song",
            "artist": "Artist",
            "genre": "Salsa",
            "genre_category": "Latin / Salsa",
            "playlist_name": "Latin Party",
            "filename": "Song.wav",
            "artwork_url": "",
            "artwork_available": False,
            "file_path": str(wav),
            "sidecar_path": str(wav.with_suffix(".json")),
        }

        response = self.client.post("/api/downloaded-library/repair-playlist-derived-genres")

        self.assertEqual(response.json()["repaired"], 1)
        self.assertEqual(response.json()["restored_from_source"], 1)
        self.original_metadata.assert_called_once_with("latin_party", "Song", "Artist")
        self.metadata.update_metadata.assert_called_once()

    def test_retag_delegates_to_shared_batch_tag_rules(self) -> None:
        wav = self.root / "Song.wav"
        self.batches.sync_selected_wav_tags.return_value = {
            "tracks": [{"id": 3, "file_path": str(wav)}],
            "tagged": [3],
            "skipped": [],
            "failed": [],
        }
        response = self.client.post("/api/downloaded-library/retag", json={"track_ids": [3]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tagged"], [3])
        self.assertEqual(response.json()["receipt"]["changed"]["count"], 1)
        self.batches.sync_selected_wav_tags.assert_called_once_with([3])


if __name__ == "__main__":
    unittest.main()
