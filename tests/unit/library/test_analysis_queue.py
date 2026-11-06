from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any

from audioextender.library.analysis_queue import DownloadedTrackAnalysisQueue
from audioextender.persistence.facade import JobRepository


class FakeRepository:
    def __init__(self, jobs: list[dict[str, Any]] | None = None) -> None:
        self.jobs = jobs or []
        self.created: list[dict[str, Any]] = []
        self.reassessed: list[int] = []

    def list_jobs(self, *, limit: int) -> list[dict[str, Any]]:
        self.limit = limit
        return self.jobs

    def create(self, *args: Any, **kwargs: Any) -> int:
        self.created.append({"args": args, "kwargs": kwargs})
        return 100 + len(self.created)

    def reassess_recording_family(self, track_id: int) -> dict[str, Any]:
        self.reassessed.append(track_id)
        return {"id": track_id}


class FakeProcessor:
    def __init__(self) -> None:
        self.enqueued: list[int] = []

    def enqueue_many(self, job_ids: list[int]) -> None:
        self.enqueued.extend(job_ids)


class DownloadedTrackAnalysisQueueTests(unittest.TestCase):
    def test_queue_reports_created_duplicate_and_unavailable_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            available = root / "available.wav"
            duplicate = root / "duplicate.wav"
            available.write_bytes(b"RIFF")
            duplicate.write_bytes(b"RIFF")
            repository = FakeRepository([{"source_path": duplicate, "status": "complete"}])
            processor = FakeProcessor()
            queue = DownloadedTrackAnalysisQueue(
                repository=repository,
                processor=processor,
                effective_settings=lambda: {"candidate_count": 4},
            )

            result = queue.queue(
                [
                    {"id": 1, "file_path": available},
                    {"id": 2, "file_path": duplicate},
                    {"id": 3, "file_path": root / "missing.wav"},
                ]
            )

        self.assertEqual({"job_ids": [101], "skipped": [2], "unavailable": [3]}, result)
        self.assertEqual([101], processor.enqueued)
        config = repository.created[0]["args"][6]
        self.assertTrue(config["analysis_only"])
        self.assertFalse(config["reanalyze"])
        self.assertEqual(repository.reassessed, [])

    def test_force_reanalysis_allows_completed_path_and_links_parent_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "track.wav"
            source.write_bytes(b"RIFF")
            repository = FakeRepository([{"source_path": source, "status": "complete"}])
            processor = FakeProcessor()
            queue = DownloadedTrackAnalysisQueue(
                repository=repository,
                processor=processor,
                effective_settings=dict,
            )

            result = queue.queue(
                [{"id": 7, "file_path": source, "completed_library_job_id": 42}],
                force=True,
            )

        self.assertEqual([101], result["job_ids"])
        self.assertEqual(42, repository.created[0]["kwargs"]["parent_job_id"])
        config = repository.created[0]["args"][6]
        self.assertTrue(config["refresh_cache"])
        self.assertTrue(config["reanalyze"])
        self.assertEqual(repository.reassessed, [7])

    def test_force_reanalysis_repairs_original_and_remix_recording_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.wav"
            remix = root / "remix.wav"
            original.write_bytes(b"RIFF-original")
            remix.write_bytes(b"RIFF-remix")
            database = root / "catalog.sqlite3"
            repository = JobRepository(database)
            original_id = repository.upsert_downloaded_track(
                title="Yes Sir, I Can Boogie",
                artist="Baccara",
                file_path=original,
            )
            remix_id = repository.upsert_downloaded_track(
                title="Yes Sir, I Can Boogie (Paul Keenan Remix)",
                artist="GBX, Baccara",
                file_path=remix,
            )
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    """UPDATE downloaded_tracks SET recording_code='OTH-999999',
                    version_code='RMX01',identity_confidence='migrated',
                    identity_reason='Legacy catalog assignment' WHERE id=?""",
                    (remix_id,),
                )
            before_original = repository.get_downloaded_track(original_id)
            before_remix = repository.get_downloaded_track(remix_id)
            assert before_original is not None and before_remix is not None
            self.assertNotEqual(before_original["recording_code"], before_remix["recording_code"])
            processor = FakeProcessor()
            queue = DownloadedTrackAnalysisQueue(
                repository=repository,
                processor=processor,
                effective_settings=dict,
            )

            queue.queue([before_remix], force=True)

            after_remix = repository.get_downloaded_track(remix_id)
            assert after_remix is not None
            self.assertEqual(after_remix["recording_code"], before_original["recording_code"])
            self.assertEqual(after_remix["version_code"], "RMX01")
            self.assertEqual(processor.enqueued, [1])


if __name__ == "__main__":
    unittest.main()
