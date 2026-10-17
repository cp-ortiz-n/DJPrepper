from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from audioextender.repositories.facade import JobRepository
from audioextender.repositories.schema import RepositorySchemaInitializer


class RepositorySchemaTests(unittest.TestCase):
    def test_schema_steps_are_explicit_and_dependency_ordered(self) -> None:
        initializer = RepositorySchemaInitializer(lambda connection: None)

        self.assertEqual(
            [step.name for step in initializer.steps],
            [
                "jobs",
                "settings-and-feedback",
                "catalog-core",
                "recording-identities",
                "catalog-relations",
                "library-search",
                "system-state",
            ],
        )

    def test_initialization_is_idempotent_and_preserves_existing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "catalog.sqlite3"
            repository = JobRepository(database)
            track = Path(temporary) / "Track.wav"
            track.write_bytes(b"RIFF")
            track_id = repository.upsert_downloaded_track(
                title="Preserved",
                artist="DJ",
                file_path=track,
                genre="House",
                genre_category="Electronic / House / House",
            )

            reopened = JobRepository(database)

            reopened_track = reopened.get_downloaded_track(track_id)
            self.assertIsNotNone(reopened_track)
            assert reopened_track is not None
            self.assertEqual(reopened_track["title"], "Preserved")
            with closing(sqlite3.connect(database)) as connection:
                tables = {
                    row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
            self.assertTrue(
                {
                    "jobs",
                    "downloaded_tracks",
                    "downloaded_track_descriptors",
                    "library_search_index",
                    "system_state",
                }.issubset(tables)
            )

    def test_legacy_database_is_upgraded_without_replacing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "legacy.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(
                    """CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY, source_name TEXT NOT NULL, source_path TEXT NOT NULL,
                    status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL DEFAULT 'Queued', preset TEXT NOT NULL DEFAULT 'auto',
                    intro_bars INTEGER NOT NULL, outro_bars INTEGER NOT NULL,
                    use_stems INTEGER NOT NULL DEFAULT 0, error TEXT, extended_path TEXT,
                    wav_path TEXT, bpm REAL, intro_quality REAL, outro_quality REAL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    INSERT INTO jobs VALUES (
                    7, 'Legacy.wav', '/legacy.wav', 'complete', 100, 'Complete', 'auto',
                    8, 8, 0, NULL, NULL, '/legacy.wav', 124, 80, 80, 'then', 'then');
                    CREATE TABLE downloaded_tracks (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                    genre TEXT NOT NULL DEFAULT '', genre_category TEXT NOT NULL DEFAULT 'Other',
                    spotify_uri TEXT NOT NULL DEFAULT '', youtube_id TEXT NOT NULL DEFAULT '',
                    youtube_url TEXT NOT NULL DEFAULT '', duration_seconds REAL,
                    imported_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    INSERT INTO downloaded_tracks VALUES (
                    3, 'Legacy track', 'DJ', '/legacy.wav', 'Legacy.wav', 'House',
                    'Electronic / House / House', '', '', '', 180, 'then', 'then');"""
                )
                connection.commit()

            repository = JobRepository(database)

            job = repository.get(7)
            self.assertIsNotNone(job)
            assert job is not None
            self.assertEqual(job["source_name"], "Legacy.wav")
            track = repository.get_downloaded_track(3)
            self.assertIsNotNone(track)
            assert track is not None
            self.assertEqual(track["title"], "Legacy track")
            self.assertTrue(track["recording_code"].startswith("HOU-"))
            with closing(sqlite3.connect(database)) as connection:
                job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
                track_columns = {row[1] for row in connection.execute("PRAGMA table_info(downloaded_tracks)")}
                bpm_verification_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(bpm_verifications)").fetchall()
                }
            self.assertIn("review_status", job_columns)
            self.assertIn("identity_inference_locked", track_columns)
            self.assertEqual(
                bpm_verification_columns,
                {"source_name", "verified_bpm", "detected_bpm", "notes", "created_at", "updated_at"},
            )
            self.assertIn("audio_quality_json", track_columns)

    def test_sqlite_backup_opens_through_the_same_initializer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source.sqlite3"
            backup_path = root / "backup.sqlite3"
            source = JobRepository(source_path)
            source.replace_settings({"preset": "club"})
            with (
                closing(sqlite3.connect(source_path)) as source_connection,
                closing(sqlite3.connect(backup_path)) as backup_connection,
            ):
                source_connection.backup(backup_connection)

            restored = JobRepository(backup_path)

            self.assertEqual(restored.get_settings()["preset"], "club")


if __name__ == "__main__":
    unittest.main()
