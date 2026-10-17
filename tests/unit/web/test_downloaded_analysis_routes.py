from unittest import TestCase
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.web.downloaded_analysis_routes import (
    DownloadedAnalysisRouteService,
    create_downloaded_analysis_router,
)


class DownloadedAnalysisRoutesTests(TestCase):
    def setUp(self) -> None:
        self.repository = Mock()
        self.queue = Mock()
        self.queue.queue.return_value = {"job_ids": [8], "skipped": [], "unavailable": []}
        service = DownloadedAnalysisRouteService(repository=lambda: self.repository, queue=lambda: self.queue)
        app = FastAPI()
        app.include_router(create_downloaded_analysis_router(service))
        self.client = TestClient(app)

    def test_selected_analysis_resolves_tracks_and_queues_without_force(self) -> None:
        self.repository.list_downloaded_tracks.return_value = [{"id": 4}, {"id": 7}]

        response = self.client.post("/api/downloaded-library/analyze", json={"track_ids": [7]})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_ids"], [8])
        self.queue.queue.assert_called_once_with([{"id": 7}], force=False)

    def test_reanalysis_uses_job_projection_and_rejects_missing_tracks(self) -> None:
        self.repository.list_downloaded_tracks_with_jobs.return_value = [{"id": 4}]

        response = self.client.post("/api/downloaded-library/reanalyze", json={"track_ids": [4, 7]})

        self.assertEqual(response.status_code, 404)
        self.queue.queue.assert_not_called()

    def test_matching_analysis_preserves_filter_contract(self) -> None:
        self.repository.page_downloaded_tracks.return_value = ([{"id": 4}, {"id": 7}], 2)

        response = self.client.post(
            "/api/downloaded-library/analyze-matching",
            json={"search": "house", "analysis": "failed", "quality": "lossless"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["matched"], 2)
        self.assertEqual(self.repository.page_downloaded_tracks.call_args.kwargs["analysis"], "failed")
        self.queue.queue.assert_called_once_with([{"id": 4}, {"id": 7}], force=False)

    def test_complete_matching_analysis_is_an_explicit_noop(self) -> None:
        response = self.client.post(
            "/api/downloaded-library/analyze-matching",
            json={"analysis": "complete"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_ids": [], "skipped": [], "unavailable": [], "matched": 0})
        self.repository.page_downloaded_tracks.assert_not_called()

    def test_matching_reanalysis_forwards_original_analysis_filter(self) -> None:
        self.repository.page_downloaded_tracks.return_value = ([{"id": 4}], 1)

        response = self.client.post(
            "/api/downloaded-library/reanalyze-matching",
            json={"analysis": "complete"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.repository.page_downloaded_tracks.call_args.kwargs["analysis"], "complete")
        self.queue.queue.assert_called_once_with([{"id": 4}], force=True)
