from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from helpers.repository_views import (
    BackupsRelocationRepository,
    FeedbackKeyVerificationRepository,
    JobsAndQueuesRepository,
    RecordingFamilyRepository,
    SettingsSystemRepository,
    TrackCatalogRepository,
)
from helpers.web_database import JobRepository, SQLiteApplicationStore


class RepositoryViewTests(unittest.TestCase):
    def test_aggregate_exposes_six_focused_repositories(self):
        with TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "catalog.sqlite3")

            self.assertIsInstance(repository, SQLiteApplicationStore)
            self.assertIsInstance(repository.track_catalog, TrackCatalogRepository)
            self.assertIsInstance(repository.jobs_and_queues, JobsAndQueuesRepository)
            self.assertIsInstance(repository.settings_system, SettingsSystemRepository)
            self.assertIsInstance(repository.recording_families, RecordingFamilyRepository)
            self.assertIsInstance(
                repository.feedback_key_verification,
                FeedbackKeyVerificationRepository,
            )
            self.assertIsInstance(
                repository.backups_relocation,
                BackupsRelocationRepository,
            )

    def test_views_share_storage_but_reject_other_domain_operations(self):
        with TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "catalog.sqlite3")

            repository.settings_system.set_system_state("scan", "ready")
            self.assertEqual(repository.settings_system.get_system_state("scan"), "ready")
            self.assertEqual(repository.get_system_state("scan"), "ready")
            with self.assertRaises(AttributeError):
                repository.settings_system.list_downloaded_tracks()

    def test_job_view_supports_worker_lifecycle_without_catalog_access(self):
        with TemporaryDirectory() as temporary:
            repository = JobRepository(Path(temporary) / "catalog.sqlite3")
            job_id = repository.jobs_and_queues.create(
                "Track.wav", Path(temporary) / "Track.wav", "auto", 16, 16, False
            )

            repository.jobs_and_queues.update(job_id, status="processing")
            self.assertEqual(repository.jobs_and_queues.get(job_id)["status"], "processing")
            with self.assertRaises(AttributeError):
                repository.jobs_and_queues.recording_family(1)


if __name__ == "__main__":
    unittest.main()
