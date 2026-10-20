# mypy: disable-error-code="attr-defined"
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_app as web_module
from audioextender.persistence.facade import JobRepository


class EndToEndBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(web_module.app)

    def test_settings_survive_save_refresh_and_repository_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "state.sqlite3"
            library = root / "External Drive" / "AudioExtenderLibrary"
            repository = JobRepository(database)
            payload = {
                "music_library_path": str(library),
                "preset": "auto",
                "intro_bars": 4,
                "outro_bars": 16,
                "intro_search_seconds": 39,
                "outro_search_seconds": 30,
            }
            with patch.object(web_module, "repository", repository):
                saved = self.client.put("/api/settings", json=payload)
                refreshed = self.client.get("/api/config")
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(refreshed.json()["effective"]["intro_search_seconds"], 39)
            self.assertEqual(refreshed.json()["effective"]["outro_search_seconds"], 30)

            restarted = JobRepository(database)
            with patch.object(web_module, "repository", restarted):
                after_restart = self.client.get("/api/config").json()["effective"]
            self.assertEqual(after_restart["music_library_path"], str(library.resolve()))
            self.assertEqual(after_restart["intro_bars"], 4)
            self.assertEqual(after_restart["outro_bars"], 16)
            self.assertEqual(after_restart["intro_search_seconds"], 39)
            self.assertEqual(after_restart["outro_search_seconds"], 30)

    def test_external_drive_reconnect_invalidates_offline_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "YOTUO" / "AudioExtenderLibrary"
            track = library / "House" / "Track.wav"
            repository = JobRepository(root / "state.sqlite3")
            repository.upsert_downloaded_track(
                title="Track",
                artist="Artist",
                file_path=track,
                genre="house",
                genre_category="Electronic / House / House",
            )
            web_module.library_status_cache.update(payload=None, expires_at=0.0)
            with (
                patch.object(web_module, "repository", repository),
                patch.object(web_module, "_music_library_root", return_value=library),
            ):
                offline = self.client.get("/api/settings/library-status").json()
                self.assertFalse(offline["online"])
                self.assertEqual(offline["offline_tracks"], 1)

                track.parent.mkdir(parents=True)
                track.write_bytes(b"RIFF-test")
                online = self.client.get("/api/settings/library-status").json()
                health = self.client.get("/api/settings/library-health").json()
                verified = self.client.post("/api/settings/library-health/verify").json()
            self.assertTrue(online["online"])
            self.assertEqual(online["available_tracks"], 1)
            self.assertEqual(online["offline_tracks"], 0)
            self.assertEqual(Path(online["path"]).resolve(), library.resolve())
            self.assertEqual(health["connection"], "connected")
            self.assertEqual(health["missing_files"], 0)
            self.assertEqual(health["pending_metadata_writes"], 0)
            self.assertIn("storage", health)
            self.assertIn("audio_quality", health)
            self.assertTrue(verified["verified"])
            self.assertIn("verified_at", verified)


if __name__ == "__main__":
    unittest.main()
