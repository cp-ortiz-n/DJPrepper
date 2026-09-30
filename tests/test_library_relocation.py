from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers.library_relocation import LibraryRelocationCoordinator
from helpers.web_database import JobRepository


class LibraryRelocationTests(unittest.TestCase):
    def make_library(self, root: Path, repository: JobRepository) -> tuple[int, Path]:
        track = root / "Electronic" / "House" / "Artist - Track.wav"
        track.parent.mkdir(parents=True)
        track.write_bytes(b"RIFF-test-audio")
        artwork = root / ".artwork" / "cover.jpg"
        artwork.parent.mkdir(parents=True)
        artwork.write_bytes(b"cover")
        track_id = repository.upsert_downloaded_track(
            title="Track", artist="Artist", file_path=track,
            genre="house", genre_category="Electronic / House",
            artwork_path=str(artwork), playlist_name="House Set",
        )
        return track_id, track

    def test_copy_preserves_source_without_switching_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); source = base / "Library"; destination = base / "Backup"
            repository = JobRepository(base / "catalog.sqlite3")
            track_id, source_track = self.make_library(source, repository)
            coordinator = LibraryRelocationCoordinator(repository, base / "relocation.json")
            coordinator.prepare(source, destination, "copy", "full")
            coordinator._run()
            state = coordinator.status()
            self.assertEqual(state["status"], "complete")
            self.assertTrue(source_track.is_file())
            self.assertTrue((destination / source_track.relative_to(source)).is_file())
            self.assertEqual(repository.get_downloaded_track(track_id)["file_path"], str(source_track.resolve()))

    def test_move_relinks_paths_preserves_id_and_keeps_original(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); source = base / "Library"; destination = base / "External Library"
            repository = JobRepository(base / "catalog.sqlite3")
            track_id, source_track = self.make_library(source, repository)
            job_id = repository.create("Artist - Track.wav", source_track, "auto", 0, 0, False)
            repository.update(
                job_id, status="complete", wav_path=str(source_track.resolve()),
                intro_preview_path=str((source / "previews" / "intro.wav").resolve()),
            )
            coordinator = LibraryRelocationCoordinator(repository, base / "relocation.json")
            coordinator.prepare(source, destination, "move", "fast")
            coordinator._run()
            relocated = repository.get_downloaded_track(track_id)
            self.assertEqual(coordinator.status()["status"], "complete")
            self.assertEqual(relocated["id"], track_id)
            self.assertEqual(Path(relocated["file_path"]), (destination / source_track.relative_to(source)).resolve())
            self.assertTrue(source_track.is_file())
            self.assertTrue((destination / ".audioextender" / "library.json").is_file())
            self.assertTrue(any((destination / "_Playlist").glob("*.m3u8")))
            relocated_job = repository.get(job_id)
            self.assertEqual(
                Path(relocated_job["wav_path"]).resolve(),
                (destination / source_track.relative_to(source)).resolve(),
            )
            self.assertEqual(
                Path(relocated_job["intro_preview_path"]).resolve(),
                (destination / "previews" / "intro.wav").resolve(),
            )
            self.assertEqual(
                repository.get_system_state("music_library_path"),
                str(destination.resolve()),
            )
            restarted = JobRepository(base / "catalog.sqlite3")
            self.assertEqual(
                restarted.get_system_state("music_library_path"),
                str(destination.resolve()),
            )
            self.assertTrue(coordinator.status()["database_backup"])
            rolled_back = coordinator.rollback()
            self.assertEqual(rolled_back["status"], "rolled_back")
            self.assertEqual(Path(repository.get_downloaded_track(track_id)["file_path"]), source_track.resolve())

    def test_relink_accepts_an_already_moved_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); source = base / "Missing Library"; destination = base / "Found Library"
            repository = JobRepository(base / "catalog.sqlite3")
            old_track = source / "Latin" / "Artist - Song.wav"
            track_id = repository.upsert_downloaded_track(
                title="Song", artist="Artist", file_path=old_track,
                genre="salsa", genre_category="Latin / Salsa", playlist_name="Latin Set",
            )
            new_track = destination / old_track.relative_to(source)
            new_track.parent.mkdir(parents=True); new_track.write_bytes(b"RIFF-relocated")
            coordinator = LibraryRelocationCoordinator(repository, base / "relocation.json")
            coordinator.prepare(source, destination, "relink", "fast")
            coordinator._run()
            self.assertEqual(coordinator.status()["status"], "complete")
            self.assertEqual(Path(repository.get_downloaded_track(track_id)["file_path"]), new_track.resolve())


if __name__ == "__main__":
    unittest.main()
