from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from audioextender.library.backup import LibraryBackupService
from audioextender.repositories.facade import JobRepository
from audioextender.set_builder.saved_sets import SavedSetService


class LibraryBackupServiceTests(unittest.TestCase):
    def make_workspace(self, root: Path) -> tuple[JobRepository, LibraryBackupService]:
        project = root / "project"
        library = root / "library"
        database = project / "output/reports/audioextender.sqlite3"
        database.parent.mkdir(parents=True)
        library.mkdir()
        repository = JobRepository(database)
        service = LibraryBackupService(database, project, library)
        return repository, service

    def test_backup_validates_and_restores_catalog_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, service = self.make_workspace(root)
            project, library = service.project, service.library_root
            wav = library / "Electronic/Track.wav"
            wav.parent.mkdir(parents=True)
            wav.write_bytes(b"not duplicated by backup")
            repository.upsert_downloaded_track(
                title="Protected track",
                artist="DJ",
                file_path=wav,
                genre="house",
                genre_category="Electronic / House / House",
            )
            repository.replace_settings({"preset": "club"})
            SavedSetService(repository).upsert(
                {"id": "friday", "name": "Friday Set", "tracks": ["track-1"], "planningReceipt": {"mode": "ai"}}
            )
            overrides = project / "track_overrides.json"
            overrides.write_text(json.dumps({"Track.wav": {"intro_before": 8}}))
            playlist = library / "_Playlist/Test.m3u8"
            playlist.parent.mkdir()
            playlist.write_text("#EXTM3U\nElectronic/Track.wav\n")

            created = service.create(root / "backups", include_cache=False, retention=5)
            inspected = service.inspect(Path(created["path"]))
            self.assertTrue(inspected["valid"])
            self.assertEqual(inspected["track_count"], 1)
            with zipfile.ZipFile(created["path"]) as bundle:
                self.assertNotIn("Electronic/Track.wav", bundle.namelist())

            repository.replace_settings({"preset": "subtle"})
            SavedSetService(repository).delete("friday")
            overrides.write_text("{}")
            playlist.unlink()
            result = service.restore(Path(created["path"]), root / "backups")

            self.assertTrue(result["restored"])
            self.assertEqual(repository.get_settings()["preset"], "club")
            self.assertEqual(SavedSetService(repository).list_sets()["sets"][0]["id"], "friday")
            self.assertIn("Track.wav", overrides.read_text())
            self.assertTrue(playlist.is_file())
            self.assertTrue(Path(result["pre_restore_backup"]["path"]).is_file())

    def test_modified_archive_fails_integrity_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, service = self.make_workspace(root)
            created = service.create(root / "backups", include_cache=False, retention=5)
            archive = Path(created["path"])
            corrupted = root / "corrupted.aexbackup"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupted, "w") as target:
                for name in source.namelist():
                    target.writestr(
                        name,
                        b"tampered" if name == "state/audioextender.sqlite3" else source.read(name),
                    )
            with self.assertRaisesRegex(ValueError, "validation"):
                service.inspect(corrupted)

    def test_retention_keeps_requested_number_of_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, service = self.make_workspace(root)
            destination = root / "backups"
            for _ in range(4):
                service.create(destination, include_cache=False, retention=2)
            self.assertEqual(len(list(destination.glob("*.aexbackup"))), 2)


if __name__ == "__main__":
    unittest.main()
