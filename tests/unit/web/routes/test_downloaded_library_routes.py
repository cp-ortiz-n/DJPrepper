from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.web.routes.downloaded_library_routes import (
    DownloadedLibraryDeliveryService,
    DownloadedLibraryRouteDependencies,
    create_downloaded_library_router,
)


class DownloadedLibraryRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.audio = root / "Song.wav"
        self.audio.write_bytes(b"RIFF-audio")
        self.artwork = root / "Cover.png"
        self.artwork.write_bytes(b"png")
        self.track = {
            "id": 7,
            "file_path": str(self.audio),
            "artwork_path": str(self.artwork),
            "genre_category": "House",
            "playlists": ["Night Set"],
        }
        self.repository = Mock()
        self.repository.get_downloaded_track.side_effect = lambda track_id: self.track if track_id == 7 else None
        self.repository.list_downloaded_tracks.return_value = [self.track]
        self.catalog_query = Mock()
        self.catalog_query.execute.return_value = {"tracks": [], "pagination": {"page": 1}}
        self.thumbnails = Mock()
        self.thumbnails.get_or_queue.return_value = self.artwork
        self.revealed: list[Path] = []
        service = DownloadedLibraryDeliveryService(
            DownloadedLibraryRouteDependencies(
                repository=lambda: self.repository,
                catalog_query=self.catalog_query,
                artwork_thumbnails=self.thumbnails,
                safe_folder_name=lambda value: value.replace("/", "-"),
                genre_path_parts=lambda value: tuple(value.split(" / ")),
                reveal=self.revealed.append,
            )
        )
        app = FastAPI()
        app.include_router(create_downloaded_library_router(service))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_catalog_query_is_delegated_with_all_filters(self) -> None:
        response = self.client.get(
            "/api/downloaded-library",
            params={"paged": "true", "page": 2, "search": "song", "genre": "House", "artwork": "available"},
        )
        self.assertEqual(response.status_code, 200)
        query = self.catalog_query.execute.call_args.args[0]
        self.assertTrue(query.paged)
        self.assertEqual((query.page, query.search, query.genre, query.artwork), (2, "song", "House", "available"))

    def test_audio_download_artwork_thumbnail_and_reveal_share_track_resolution(self) -> None:
        audio = self.client.get("/api/downloaded-library/tracks/7/audio")
        download = self.client.get("/api/downloaded-library/tracks/7/download")
        artwork = self.client.get("/api/downloaded-library/tracks/7/artwork?thumbnail=true")
        reveal = self.client.post("/api/downloaded-library/tracks/7/reveal")
        self.assertEqual(audio.content, b"RIFF-audio")
        self.assertEqual(download.content, b"RIFF-audio")
        self.assertEqual(artwork.headers["cache-control"], "public, max-age=31536000, immutable")
        self.thumbnails.get_or_queue.assert_called_once_with(self.artwork)
        self.assertEqual(reveal.json(), {"revealed": True, "absolute_path": str(self.audio.resolve())})
        self.assertEqual(self.revealed, [self.audio])

    def test_missing_media_preserves_not_found_responses(self) -> None:
        self.assertEqual(self.client.get("/api/downloaded-library/tracks/99/audio").status_code, 404)
        self.assertEqual(self.client.get("/api/downloaded-library/tracks/99/artwork").status_code, 404)
        self.assertEqual(self.client.post("/api/downloaded-library/tracks/99/reveal").status_code, 404)

    def test_selected_genre_and_playlist_archives_use_transient_consistent_layout(self) -> None:
        responses = (
            self.client.post("/api/downloaded-library/download", json={"track_ids": [7]}),
            self.client.get("/api/downloaded-library/genres/House/download"),
            self.client.get("/api/downloaded-library/playlists/Night%20Set/download"),
        )
        expected = (
            "Selected Downloaded Tracks/House/Song.wav",
            "House/House/Song.wav",
            "Night Set/House/Song.wav",
        )
        for response, member in zip(responses, expected, strict=True):
            self.assertEqual(response.status_code, 200)
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                self.assertEqual(archive.namelist(), [member])

    def test_archive_rejects_unknown_or_unavailable_selection(self) -> None:
        self.assertEqual(
            self.client.post("/api/downloaded-library/download", json={"track_ids": [99]}).status_code,
            404,
        )
        self.audio.unlink()
        self.assertEqual(
            self.client.post("/api/downloaded-library/download", json={"track_ids": [7]}).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
