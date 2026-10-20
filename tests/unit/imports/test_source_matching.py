from __future__ import annotations

import unittest
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.imports.playlist_csv import parse_playlist_csv
from audioextender.imports.source_matching import (
    SourceMatchError,
    SourceMatchingService,
    best_youtube_match,
)
from audioextender.library.genre_taxonomy import generalized_genre
from audioextender.web.routes.imports import create_import_router


class SourceMatchingTests(unittest.TestCase):
    def test_rejects_unknown_source_before_provider_io(self) -> None:
        http_get = Mock()
        with self.assertRaisesRegex(SourceMatchError, "Spotify or SoundCloud"):
            SourceMatchingService(http_get=http_get).match("https://example.com/track/123")
        http_get.assert_not_called()

    def test_soundcloud_metadata_preserves_public_contract(self) -> None:
        response = Mock()
        response.json.return_value = {
            "title": "Authorized Mix",
            "author_name": "DJ Example",
            "thumbnail_url": "https://i1.sndcdn.com/art.jpg",
        }
        service = SourceMatchingService(http_get=Mock(return_value=response))

        payload = service.match("https://soundcloud.com/example/authorized-mix")

        self.assertEqual(payload["source_type"], "soundcloud")
        self.assertEqual(payload["title"], "Authorized Mix")
        self.assertEqual(payload["artist"], "DJ Example")
        self.assertIsNone(payload["duration"])

    def test_youtube_ranking_rejects_wrong_version_and_long_upload(self) -> None:
        match, _, warnings = best_youtube_match(
            {"title": "Fiesta", "artist": "Artist", "duration_ms": 180_000},
            [
                {
                    "id": "wrong",
                    "title": "Artist Fiesta extended remix tutorial",
                    "duration": 900,
                    "channel": "Artist",
                }
            ],
        )
        self.assertEqual(match, {})
        self.assertIn("no reliable match selected", warnings)

    def test_source_match_route_maps_domain_errors_without_changing_shape(self) -> None:
        service = Mock(spec=SourceMatchingService)
        service.match.side_effect = SourceMatchError(502, "provider unavailable")
        app = FastAPI()
        app.include_router(create_import_router(Mock(), source_matching=service))

        response = TestClient(app).post(
            "/api/imports/source-match",
            json={"url": "https://open.spotify.com/track/123456"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "provider unavailable"})


class PlaylistCsvTests(unittest.TestCase):
    def test_parses_spotify_columns_and_applies_library_taxonomy(self) -> None:
        tracks = parse_playlist_csv(
            b"Track URI,Track Name,Artist Name(s),Duration (ms),Genres,Tempo\n"
            b"spotify:track:123,Freestyler,FAULHABER,179612,slap house,155.002\n",
            generalized_genre,
        )
        self.assertEqual(
            tracks,
            [
                {
                    "title": "Freestyler",
                    "artist": "FAULHABER",
                    "duration_ms": 179612,
                    "genre": "slap house",
                    "genre_category": "Electronic / House / House",
                    "tempo": "155.002",
                    "spotify_uri": "spotify:track:123",
                }
            ],
        )

    def test_requires_title_and_artist_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "Track Name"):
            parse_playlist_csv(b"Album,Year\nExample,2026\n", generalized_genre)


if __name__ == "__main__":
    unittest.main()
