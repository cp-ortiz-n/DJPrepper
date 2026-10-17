from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from audioextender.library.analysis_queue import DownloadedTrackAnalysisQueue


class FakeRepository:
    def __init__(self, jobs: list[dict[str, Any]] | None = None) -> None:
        self.jobs = jobs or []
        self.created: list[dict[str, Any]] = []

    def list_jobs(self, *, limit: int) -> list[dict[str, Any]]:
        self.limit = limit
        return self.jobs

    def create(self, *args: Any, **kwargs: Any) -> int:
        self.created.append({"args": args, "kwargs": kwargs})
        return 100 + len(self.created)


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


if __name__ == "__main__":
    unittest.main()
