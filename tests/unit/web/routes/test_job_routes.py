from __future__ import annotations

import unittest
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.processing.job_workflows import JobWorkflowError, JobWorkflowService
from audioextender.web.routes.job_routes import JobQueueService, create_job_router


class JobRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Mock()
        self.processor = Mock()
        self.workflow = Mock(spec=JobWorkflowService)
        app = FastAPI()
        app.include_router(
            create_job_router(
                JobQueueService(repository=lambda: self.repository, processor=lambda: self.processor),
                self.workflow,
            )
        )
        self.client = TestClient(app)

    def test_create_maps_multipart_fields_to_workflow_command(self) -> None:
        self.workflow.create.return_value = {"job_ids": [42]}

        response = self.client.post(
            "/api/jobs",
            data={
                "preset": "auto",
                "intro_bars": "8",
                "outro_bars": "auto",
                "review_candidates": "true",
                "candidate_count": "4",
            },
            files={"files": ("Track.wav", b"audio", "audio/wav")},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_ids": [42]})
        uploads, command = self.workflow.create.call_args.args
        self.assertEqual(uploads[0].filename, "Track.wav")
        self.assertEqual(command.intro_bars, "8")
        self.assertTrue(command.review_candidates)
        self.assertEqual(command.overrides["candidate_count"], 4)

    def test_create_maps_workflow_errors_to_http(self) -> None:
        self.workflow.create.side_effect = JobWorkflowError(400, "Unsupported audio file: Track.txt")
        response = self.client.post(
            "/api/jobs",
            files={"files": ("Track.txt", b"text", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Unsupported audio file: Track.txt"})


if __name__ == "__main__":
    unittest.main()
