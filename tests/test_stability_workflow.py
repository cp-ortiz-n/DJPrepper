from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import web_app as web_module
from helpers.library_relocation import LibraryRelocationCoordinator
from helpers.web_database import JobRepository
from web_app import SetExportPreflightRequest, SetPlaylistSaveRequest, SetPlaylistTrack


def _write_silent_wav(path: Path, *, seconds: float = 0.05) -> None:
    """Create a small valid WAV so the workflow fixture uses real audio files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 8_000
    frames = round(sample_rate * seconds)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00\x00\x00" * frames)


class StabilityWorkflowTests(unittest.TestCase):
    """Regression gate for user-owned data that must survive the full workflow."""

    def test_catalog_data_survives_reimport_relocation_restart_reanalysis_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "state" / "audioextender.sqlite3"
            source_library = root / "Music"
            external_library = root / "External Drive" / "Music"
            source_track = source_library / "Electronic" / "House" / "Artist - Track.wav"
            source_artwork = source_library / ".artwork" / "artist-track.jpg"
            _write_silent_wav(source_track)
            source_artwork.parent.mkdir(parents=True)
            source_artwork.write_bytes(b"test-cover")

            repository = JobRepository(database)
            track_id = repository.upsert_downloaded_track(
                title="Track", artist="Artist", file_path=source_track,
                genre="deep house",
                genre_category="Electronic / House / Deep House",
                spotify_uri="spotify:track:stable-recording",
                artwork_url="https://example.test/cover.jpg",
                artwork_path=str(source_artwork), duration_seconds=184.0,
                playlist_name="House Night",
            )

            # A repeat import adds its source playlist to the existing recording.
            duplicate_id = repository.upsert_downloaded_track(
                title="Track", artist="Artist", file_path=source_track,
                genre="deep house",
                genre_category="Electronic / House / Deep House",
                spotify_uri="spotify:track:stable-recording",
                playlist_name="Favorites",
            )
            self.assertEqual(duplicate_id, track_id)
            self.assertEqual(len(repository.list_downloaded_tracks()), 1)

            completed_job = repository.create(
                source_track.name, source_track, "auto", 0, 0, False,
                {"analysis_only": True},
            )
            repository.update(
                completed_job, status="complete", progress=100, stage="Complete",
                wav_path=str(source_track), bpm=124.0,
                cues_json=json.dumps([{"name": "Mix in", "start": 16.0}]),
            )
            repository.set_key_verification(
                source_track.name, "A minor", "C major",
                [{"key": "A minor", "detectors": "manual"}], "Checked by ear",
            )
            repository.add_track_feedback(
                source_track.name, "whole-track", True, "clean-grid", "Mixes cleanly",
            )

            relocation = LibraryRelocationCoordinator(
                repository, root / "state" / "library-relocation.json"
            )
            relocation.prepare(source_library, external_library, "move", "full")
            relocation._run()
            self.assertEqual(relocation.status()["status"], "complete")

            # Reopening the repository represents an application restart.
            restarted = JobRepository(database)
            track = restarted.get_downloaded_track(track_id)
            assert track is not None
            relocated_track = external_library / source_track.relative_to(source_library)
            relocated_artwork = external_library / source_artwork.relative_to(source_library)
            self.assertEqual(Path(track["file_path"]), relocated_track.resolve())
            self.assertEqual(Path(track["artwork_path"]), relocated_artwork.resolve())
            self.assertTrue(relocated_track.is_file())
            self.assertTrue(relocated_artwork.is_file())
            self.assertEqual(track["genre"], "deep house")
            self.assertEqual(track["genre_category"], "Electronic / House / Deep House")
            self.assertRegex(track["recording_code"], r"^AE-\d{4,}$")
            self.assertEqual(track["version_code"], "ORG")
            self.assertEqual(set(track["playlists"]), {"House Night", "Favorites"})
            self.assertEqual(
                restarted.key_verification(source_track.name)["verified_key"], "A minor"
            )
            self.assertEqual(
                restarted.track_feedback(source_track.name)[0]["notes"], "Mixes cleanly"
            )

            # Reanalysis links a new generation without replacing user-owned data.
            service = Mock()
            with patch.object(web_module, "repository", restarted), patch.object(
                web_module, "service", service
            ), patch.object(web_module, "_effective_settings", return_value={}):
                queued = web_module._queue_downloaded_analysis(
                    restarted.list_downloaded_tracks_with_jobs(), force=True
                )
            self.assertEqual(len(queued["job_ids"]), 1)
            reanalysis = restarted.get(queued["job_ids"][0])
            assert reanalysis is not None
            self.assertEqual(reanalysis["parent_job_id"], completed_job)
            self.assertTrue(json.loads(reanalysis["config_json"])["refresh_cache"])
            service.enqueue_many.assert_called_once_with(queued["job_ids"])
            self.assertEqual(
                restarted.key_verification(source_track.name)["verified_key"], "A minor"
            )
            self.assertEqual(len(restarted.track_feedback(source_track.name)), 1)

            preflight = web_module.set_builder_export_preflight(
                SetExportPreflightRequest(paths=[str(relocated_track)])
            )
            self.assertTrue(preflight["ready"])
            with patch.object(
                web_module, "_music_library_root", return_value=external_library
            ):
                saved = web_module.set_builder_save_playlist(
                    SetPlaylistSaveRequest(
                        name="Regression Set",
                        tracks=[SetPlaylistTrack(
                            path=str(relocated_track), title="Artist - Track",
                            duration_seconds=184.0,
                        )],
                    )
                )
            playlist = Path(saved["path"])
            self.assertTrue(playlist.is_file())
            self.assertIn(
                str(relocated_track.resolve()), playlist.read_text(encoding="utf-8")
            )


if __name__ == "__main__":
    unittest.main()
