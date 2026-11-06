"""Provider-neutral artwork resolution and fallback contracts."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from audioextender.imports.source_artwork import ArtworkSyncResult, SourceArtworkService


class SourceArtworkServiceTests(unittest.TestCase):
    def service(self, metadata: Mock, cache: Mock | None = None) -> SourceArtworkService:
        return SourceArtworkService(metadata, cache or Mock(return_value="/library/.artwork/cover.jpg"))

    def test_spotify_cover_has_priority_over_provider_artwork(self) -> None:
        metadata = Mock()
        metadata.spotify_metadata.return_value = {"thumbnail_url": "https://i.scdn.co/spotify.jpg"}
        metadata.soundcloud_metadata.return_value = {"thumbnail_url": "https://i1.sndcdn.com/soundcloud.jpg"}
        service = self.service(metadata)

        candidates = service.import_candidates(
            source_url="https://soundcloud.com/dj/track",
            spotify_uri="spotify:track:abc123",
            supplied_url="https://i1.sndcdn.com/supplied.jpg",
        )

        self.assertEqual(candidates[0].source, "spotify")
        self.assertEqual(candidates[0].url, "https://i.scdn.co/spotify.jpg")

    def test_bulk_soundcloud_import_resolves_artwork_without_browser_metadata(self) -> None:
        metadata = Mock()
        metadata.soundcloud_metadata.return_value = {"thumbnail_url": "https://i1.sndcdn.com/art.jpg"}
        cache = Mock(return_value="/library/.artwork/art.jpg")
        service = self.service(metadata, cache)

        result = service.sync_import(
            source_url="https://soundcloud.com/dj/track",
            destination=Path("/library/Track.wav"),
        )

        self.assertEqual(
            result, ArtworkSyncResult("https://i1.sndcdn.com/art.jpg", "/library/.artwork/art.jpg", "soundcloud")
        )
        metadata.soundcloud_metadata.assert_called_once_with("https://soundcloud.com/dj/track")

    def test_youtube_tries_best_available_thumbnail_then_deterministic_fallback(self) -> None:
        metadata = Mock()
        cache = Mock(side_effect=["", "", "/library/.artwork/fallback.jpg"])
        service = self.service(metadata, cache)

        result = service.sync_import(
            source_url="https://www.youtube.com/watch?v=abcDEF12345",
            destination=Path("/library/Track.wav"),
            provider_info={
                "thumbnail": "https://i.ytimg.com/default.jpg",
                "thumbnails": [
                    {"url": "https://i.ytimg.com/small.jpg", "width": 120, "height": 90},
                    {"url": "https://i.ytimg.com/large.jpg", "width": 1280, "height": 720},
                ],
            },
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.source, "youtube")
        self.assertEqual(result.url, "https://i.ytimg.com/small.jpg")
        self.assertEqual(cache.call_count, 3)

    def test_repair_uses_soundcloud_source_instead_of_invalid_youtube_fallback(self) -> None:
        metadata = Mock()
        metadata.soundcloud_metadata.return_value = {"thumbnail_url": "https://i1.sndcdn.com/repaired.jpg"}
        service = self.service(metadata)

        candidates = service.track_candidates(
            {
                "youtube_id": "soundcloud:deadbeef",
                "youtube_url": "https://soundcloud.com/dj/track",
                "artwork_url": "",
                "spotify_uri": "",
            }
        )

        self.assertEqual(
            [(item.source, item.url) for item in candidates], [("soundcloud", "https://i1.sndcdn.com/repaired.jpg")]
        )
        self.assertNotIn("i.ytimg.com", candidates[0].url)

    def test_legacy_youtube_id_without_source_url_can_still_repair_artwork(self) -> None:
        candidates = self.service(Mock()).track_candidates(
            {"youtube_id": "abcDEF12345", "youtube_url": "", "artwork_url": "", "spotify_uri": ""}
        )

        self.assertEqual(
            [(item.source, item.url) for item in candidates],
            [("youtube", "https://i.ytimg.com/vi/abcDEF12345/hqdefault.jpg")],
        )

    def test_metadata_failure_falls_back_without_failing_the_audio_import(self) -> None:
        metadata = Mock()
        metadata.spotify_metadata.side_effect = RuntimeError("offline")
        cache = Mock(return_value="/library/.artwork/youtube.jpg")
        service = self.service(metadata, cache)

        result = service.sync_import(
            source_url="https://youtu.be/abcDEF12345",
            destination=Path("/library/Track.wav"),
            spotify_uri="spotify:track:abc123",
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.url, "https://i.ytimg.com/vi/abcDEF12345/hqdefault.jpg")

    def test_duplicate_candidates_are_removed_and_complete_cache_failure_returns_none(self) -> None:
        metadata = Mock()
        metadata.soundcloud_metadata.return_value = {"thumbnail_url": "https://i1.sndcdn.com/art.jpg"}
        service = self.service(metadata, Mock(return_value=""))

        candidates = service.import_candidates(
            source_url="https://soundcloud.com/dj/track",
            supplied_url="https://i1.sndcdn.com/art.jpg",
        )
        result = service.sync_import(
            source_url="https://soundcloud.com/dj/track",
            supplied_url="https://i1.sndcdn.com/art.jpg",
            destination=Path("/library/Track.wav"),
        )

        self.assertEqual(len(candidates), 1)
        self.assertIsNone(result)

    def test_cache_exception_falls_through_to_next_candidate(self) -> None:
        metadata = Mock()
        cache = Mock(side_effect=[OSError("disk unavailable"), "/library/.artwork/fallback.jpg"])
        service = self.service(metadata, cache)

        result = service.sync_import(
            source_url="https://www.youtube.com/watch?v=abcDEF12345",
            destination=Path("/library/Track.wav"),
            provider_info={"thumbnail": "https://i.ytimg.com/preferred.jpg"},
        )

        self.assertEqual(
            result,
            ArtworkSyncResult(
                "https://i.ytimg.com/vi/abcDEF12345/hqdefault.jpg",
                "/library/.artwork/fallback.jpg",
                "youtube",
            ),
        )


if __name__ == "__main__":
    unittest.main()
