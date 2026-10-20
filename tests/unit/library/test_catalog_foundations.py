from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from audioextender.library.catalog_migration import DownloadedCatalogMigrator
from audioextender.library.catalog_presenter import downloaded_track_payload
from audioextender.library.genre_taxonomy import (
    catalog_genre_category,
    generalized_genre,
    normalize_genre_category,
)
from audioextender.library.job_catalog import LibraryJobCatalogService, LibraryTrackRemovalError
from audioextender.library.local_media import LocalMediaService
from audioextender.persistence.facade import JobRepository


class DownloadedCatalogMigratorTests(unittest.TestCase):
    def test_checkpoint_runs_migration_once_and_survives_new_service_instance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3")
            migrator = DownloadedCatalogMigrator(
                repository=lambda: repository,
                output_root=root / "output",
                music_library_root=lambda: root / "library",
                catalog_genre_category=lambda _path, _stored, _detailed: "Other",
                write_source_metadata=Mock(),
            )
            with patch.object(migrator, "migrate", return_value={}) as migrate:
                migrator.ensure_current()
                migrator.ensure_current()
                migrate.assert_called_once_with()
            self.assertEqual(repository.get_system_state("downloaded_catalog_migration"), migrator.version)

            restarted = DownloadedCatalogMigrator(
                repository=lambda: repository,
                output_root=root / "output",
                music_library_root=lambda: root / "library",
                catalog_genre_category=lambda _path, _stored, _detailed: "Other",
                write_source_metadata=Mock(),
            )
            with patch.object(restarted, "migrate", return_value={}) as migrate_after_restart:
                restarted.ensure_current()
                migrate_after_restart.assert_not_called()

    def test_reconciles_valid_sidecar_and_records_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "library"
            source = library / "House" / "Track.source.json"
            wav = source.with_name("Track.wav")
            source.parent.mkdir(parents=True)
            wav.touch()
            source.write_text(
                json.dumps({"title": "Track", "artist": "Artist", "genre": "house"}),
                encoding="utf-8",
            )
            repository = JobRepository(root / "catalog.sqlite3")
            migrator = DownloadedCatalogMigrator(
                repository=lambda: repository,
                output_root=root / "output",
                music_library_root=lambda: library,
                catalog_genre_category=lambda _path, _stored, _detailed: "Electronic / House / House",
                write_source_metadata=Mock(),
            )

            result = migrator.migrate()

            self.assertEqual(result["updated"], 1)
            self.assertEqual(repository.list_downloaded_tracks()[0]["title"], "Track")
            self.assertIn(str(source.resolve()), repository.catalog_source_signatures())


class LibraryFoundationTests(unittest.TestCase):
    def test_catalog_genre_prefers_explicit_folder_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = root / "Electronic" / "House" / "Afro House" / "Song.wav"
            wav.parent.mkdir(parents=True)
            wav.touch()
            self.assertEqual(
                catalog_genre_category(wav, "Electronic / General", "house", library_root=root),
                "Electronic / House / Afro House",
            )

    def test_local_media_sidecar_is_atomic_and_hides_next_to_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "House" / "Track.wav"
            audio.parent.mkdir(parents=True)
            audio.touch()
            service = LocalMediaService(lambda: root, lambda: root, Mock())

            sidecar = service.write_source_metadata(audio, {"title": "Track"})

            self.assertEqual(sidecar.parent, root / ".audioextender" / "sources")
            self.assertEqual(json.loads(sidecar.read_text())["file_path"], str(audio.resolve()))
            self.assertFalse(sidecar.with_suffix(".tmp").exists())

    def test_catalog_payload_hides_storage_fields_and_reports_availability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Track.wav"
            path.touch()
            payload = downloaded_track_payload(
                {
                    "id": 1,
                    "file_path": str(path),
                    "artwork_path": "",
                    "genre": "house",
                    "genre_category": "House",
                },
                generalized_genre=generalized_genre,
                normalize_genre_category=normalize_genre_category,
            )
            self.assertNotIn("file_path", payload)
            self.assertEqual(payload["absolute_path"], str(path.resolve()))
            self.assertTrue(payload["available"])


class LibraryJobCatalogTests(unittest.TestCase):
    def test_removal_rejects_active_generation(self) -> None:
        repository = Mock()
        repository.list_jobs.return_value = [{"id": 3, "source_name": "Track.wav", "status": "processing"}]
        service = LibraryJobCatalogService(lambda: repository, Path("/missing/report.json"))
        with self.assertRaisesRegex(LibraryTrackRemovalError, "Cancel or finish"):
            service.remove("Track.wav")
        repository.delete.assert_not_called()

    def test_removal_updates_report_but_preserves_export_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "processing_report.json"
            report.write_text(json.dumps({"songs": {"track.wav": {"status": "complete"}}}), encoding="utf-8")
            repository = Mock()
            repository.list_jobs.return_value = [{"id": 3, "source_name": "Track.wav", "status": "complete"}]
            repository.delete.return_value = True
            result = LibraryJobCatalogService(lambda: repository, report).remove("Track.wav")
            self.assertEqual(result, {"removed_generations": 1, "files_preserved": True})
            self.assertEqual(json.loads(report.read_text())["songs"]["track.wav"]["status"], "removed")


if __name__ == "__main__":
    unittest.main()
