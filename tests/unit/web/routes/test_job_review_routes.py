import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.processing.job_workflows import JobWorkflowError
from audioextender.web.routes.job_review_routes import (
    JobReviewRouteDependencies,
    JobReviewService,
    create_job_review_router,
)


class JobReviewRoutesTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.repository = Mock()
        self.workflow = Mock()
        self.append_feedback = Mock()
        self.service = JobReviewService(
            JobReviewRouteDependencies(
                repository=lambda: self.repository,
                workflow=self.workflow,
                output_root=self.output,
                append_feedback=self.append_feedback,
            )
        )
        app = FastAPI()
        app.include_router(create_job_review_router(self.service))
        self.client = TestClient(app)

    def test_reprocess_delegates_validated_values_and_translates_workflow_errors(self) -> None:
        self.workflow.reprocess.return_value = {"job_id": 12}
        response = self.client.post("/api/jobs/3/reprocess", json={"preset": "club", "pcm_bits": 24})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_id": 12})
        self.assertEqual(self.workflow.reprocess.call_args.args[0], 3)
        self.assertEqual(self.workflow.reprocess.call_args.args[1]["preset"], "club")

        self.workflow.reprocess.side_effect = JobWorkflowError(404, "Job not found")
        response = self.client.post("/api/jobs/99/reprocess")
        self.assertEqual(response.status_code, 404)

    def test_reject_requires_a_pending_review(self) -> None:
        self.repository.get.return_value = {"review_status": "pending"}
        response = self.client.post("/api/jobs/3/review/reject")
        self.assertEqual(response.json(), {"ok": True})
        self.repository.update.assert_called_once_with(3, review_status="rejected")

        self.repository.get.return_value = {"review_status": "resolved"}
        self.assertEqual(self.client.post("/api/jobs/3/review/reject").status_code, 409)

    def test_candidates_and_feedback_keep_the_existing_payload_contract(self) -> None:
        self.repository.get.return_value = {
            "source_name": "Song.wav",
            "candidates_json": json.dumps({"intro": [{"rank": 1}]}),
        }
        self.repository.add_feedback.return_value = 22
        self.repository.feedback.return_value = [{"id": 22}]

        self.assertEqual(self.client.get("/api/jobs/3/candidates").json(), {"intro": [{"rank": 1}]})
        response = self.client.post(
            "/api/jobs/3/feedback",
            json={"position": "intro", "candidate_rank": 1, "accepted": True, "tags": " clean ", "notes": " good "},
        )
        self.assertEqual(response.json(), {"id": 22})
        self.repository.add_feedback.assert_called_once_with(3, "intro", 1, True, "clean", "good")
        self.append_feedback.assert_called_once_with(self.output, "Song.wav", "intro", 1, True, "clean", "good")
        self.assertEqual(self.client.get("/api/jobs/3/feedback").json(), [{"id": 22}])

    def test_feedback_rejects_an_unknown_position(self) -> None:
        self.repository.get.return_value = {"source_name": "Song.wav"}
        response = self.client.post(
            "/api/jobs/3/feedback",
            json={"position": "middle", "accepted": False},
        )
        self.assertEqual(response.status_code, 400)
        self.repository.add_feedback.assert_not_called()

    def test_candidate_audio_prefers_archived_preview_and_validates_coordinates(self) -> None:
        self.repository.get.return_value = {"source_name": "Song.wav"}
        preview = self.output / "versions" / "Song" / "job-3" / "previews" / "Intro Candidate 1.wav"
        preview.parent.mkdir(parents=True)
        preview.write_bytes(b"RIFF-test")

        response = self.client.get("/api/jobs/3/candidate/intro/1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"RIFF-test")
        self.assertEqual(self.client.get("/api/jobs/3/candidate/middle/1").status_code, 404)
        self.assertEqual(self.client.get("/api/jobs/3/candidate/intro/4").status_code, 404)

    def test_candidate_audio_finds_case_insensitive_legacy_preview_folder(self) -> None:
        self.repository.get.return_value = {"source_name": "Song.wav"}
        preview = self.output / "previews" / "song" / "Outro Candidate 2.wav"
        preview.parent.mkdir(parents=True)
        preview.write_bytes(b"RIFF-legacy")

        response = self.client.get("/api/jobs/3/candidate/outro/2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"RIFF-legacy")
