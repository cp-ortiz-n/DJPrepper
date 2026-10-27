from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from audioextender.library.catalog_projection_builder import CatalogProjectionBuilder


class ProjectionRepository:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def list_set_builder_tracks(self) -> list[dict]:
        return [
            {
                "job_id": 9,
                "source_name": "Artist - Track.wav",
                "source_path": "/music/track.wav",
                "wav_path": "/music/track.wav",
                "library_path": "/music/track.wav",
                "extended_path": "",
                "config_json": "{}",
                "category": "Electronic / House",
                "detail_genre": "Deep House",
                "downloaded_id": 3,
                "recording_code": "HOU-000003",
                "version_code": "ORG",
                "descriptors_json": "not-json",
                "playlists_json": '["Deep_House_Late_Night"]',
                "set_analysis_json": '{"bpm":124}',
                "title": "Track",
                "artist": "Artist",
                "camelot": "8A",
            }
        ]


class CatalogProjectionBuilderTests(unittest.TestCase):
    def test_catalog_payload_preserves_compatibility_shape_and_bad_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            builder = CatalogProjectionBuilder(
                repository=lambda: ProjectionRepository(),
                load_processing_report=lambda: {"songs": {}},
                normalize_genre_category=lambda value: value,
                catalog_path=lambda: path,
                camelot_keys={},
            )

            builder.write_catalog_cache()
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(9, payload["version"])
        self.assertEqual(1, payload["total"])
        self.assertEqual([], payload["tracks"][0]["descriptors"])
        self.assertEqual("8A", payload["tracks"][0]["analysis"]["_camelot"])
        self.assertEqual(9, payload["tracks"][0]["job"]["id"])
        self.assertEqual("HOU-000003", payload["tracks"][0]["recording_code"])
        self.assertEqual("ORG", payload["tracks"][0]["version_code"])
        self.assertIsNone(payload["tracks"][0]["external_rating"])
        self.assertEqual(["Deep_House_Late_Night"], payload["tracks"][0]["playlists"])
        self.assertIn(
            {
                "value": "deep house",
                "source": "Deep_House_Late_Night",
                "provenance": "playlist",
                "confidence": 0.78,
            },
            payload["tracks"][0]["playlist_identity"],
        )


if __name__ == "__main__":
    unittest.main()
