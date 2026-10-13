from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from audioextender.library.catalog_query_service import DownloadedCatalogQuery, DownloadedCatalogQueryService
from audioextender.library.descriptor_service import DescriptorService, DescriptorTrackNotFound
from audioextender.processing.job_workflows import (
    JobCreationCommand,
    JobWorkflowError,
    JobWorkflowService,
    UploadedAudio,
)


class DescriptorServiceTests(unittest.TestCase):
    def test_missing_track_is_a_domain_error(self) -> None:
        repository = Mock()
        repository.get_downloaded_track.return_value = None
        with self.assertRaises(DescriptorTrackNotFound):
            DescriptorService(lambda: repository, Mock()).get(42)

    def test_manual_update_persists_protection_and_invalidates_catalog(self) -> None:
        repository = Mock()
        repository.update_track_descriptors.return_value = {"updated": 1, "missing": []}
        repository.track_descriptors.return_value = []
        repository.track_identity_inference_status.return_value = {"protected": True}
        invalidate = Mock()
        result = DescriptorService(lambda: repository, invalidate).update(
            7,
            [{"category": "context", "value": "party", "provenance": "manual"}],
            mode="replace",
            protect_from_inference=None,
        )
        self.assertEqual(result["updated"], 1)
        repository.set_track_identity_inference_protection.assert_called_once_with([7], True)
        invalidate.assert_called_once_with()


class CatalogQueryServiceTests(unittest.TestCase):
    def test_unpaged_query_builds_review_facets_without_http_state(self) -> None:
        repository = Mock()
        repository.list_downloaded_tracks_with_jobs.return_value = [
            {"id": 1, "title": "", "artist": "Artist", "genre": "", "genre_category": "Other", "playlists": []}
        ]
        service = DownloadedCatalogQueryService(
            lambda: repository,
            Mock(),
            lambda value: value,
            lambda track: {"id": track["id"]},
        )
        result = service.execute(DownloadedCatalogQuery())
        self.assertEqual(result["review_states"]["missing_title"], 1)
        self.assertEqual(result["pagination"]["catalog_total"], 1)


class JobWorkflowServiceTests(unittest.TestCase):
    def service(self, root: Path, repository: Mock, processor: Mock) -> JobWorkflowService:
        return JobWorkflowService(
            repository,
            processor,
            root,
            frozenset({".wav"}),
            (0, 4, 8),
            lambda: {},
            lambda: {"intro_bars": 4, "outro_bars": 4},
            lambda _preset: {},
        )

    def test_create_rejects_unsupported_upload_before_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Mock()
            with self.assertRaisesRegex(JobWorkflowError, "Unsupported audio file"):
                self.service(Path(temporary), repository, Mock()).create(
                    [UploadedAudio("track.txt", io.BytesIO(b"no"))],
                    JobCreationCommand("auto", "auto", "auto", False, False, False, {}),
                )
            repository.create.assert_not_called()

    def test_reprocess_preserves_parent_and_enqueues_new_job(self) -> None:
        repository = Mock()
        repository.get.return_value = {
            "source_name": "track.wav",
            "source_path": "/tmp/track.wav",
            "preset": "auto",
            "intro_bars": 4,
            "outro_bars": 4,
            "use_stems": 0,
            "config_json": "{}",
        }
        repository.create.return_value = 99
        processor = Mock()
        result = self.service(Path("/tmp"), repository, processor).reprocess(12)
        self.assertEqual(result, {"job_id": 99})
        self.assertEqual(repository.create.call_args.kwargs["parent_job_id"], 12)
        processor.enqueue.assert_called_once_with(99)


if __name__ == "__main__":
    unittest.main()
