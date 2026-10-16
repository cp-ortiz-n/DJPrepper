from __future__ import annotations

import unittest
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.web.recording_family_routes import (
    RecordingFamilyRouteDependencies,
    RecordingFamilyService,
    create_recording_family_router,
)


class RecordingFamilyRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Mock()
        self.service = RecordingFamilyService(
            RecordingFamilyRouteDependencies(
                repository=lambda: self.repository,
                track_payload=lambda track: {"id": track["id"], "projected": True},
            )
        )
        app = FastAPI()
        app.include_router(create_recording_family_router(self.service))
        self.client = TestClient(app)

    def test_duplicate_candidates_and_merge_use_recording_repository_capability(self) -> None:
        self.repository.duplicate_candidates.return_value = [{"reason": "same audio", "tracks": [{"id": 1}]}]
        self.repository.merge_downloaded_tracks.return_value = {"id": 1}

        candidates = self.client.get("/api/downloaded-library/duplicate-candidates")
        merged = self.client.post(
            "/api/downloaded-library/merge-duplicate",
            json={"survivor_id": 1, "duplicate_id": 2},
        )

        self.assertEqual(
            candidates.json(),
            {"candidates": [{"reason": "same audio", "tracks": [{"id": 1, "projected": True}]}], "total": 1},
        )
        self.assertEqual(merged.json(), {"merged": True, "track": {"id": 1, "projected": True}})
        self.repository.merge_downloaded_tracks.assert_called_once_with(1, 2)

    def test_family_lookup_projects_members_and_suggestions(self) -> None:
        self.repository.recording_family.return_value = [{"id": 1}, {"id": 2}]
        self.repository.recording_family_suggestions.return_value = [
            {"score": 91, "reasons": ["similar title"], "track": {"id": 3}}
        ]

        response = self.client.get("/api/downloaded-library/tracks/1/family")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([track["id"] for track in response.json()["family"]], [1, 2])
        self.assertEqual(response.json()["suggestions"][0]["track"]["id"], 3)

    def test_link_resolves_visible_identity_and_unlink_uses_keep_separate(self) -> None:
        self.repository.track_id_for_identity.return_value = 9
        self.repository.link_recording_version.return_value = {"id": 4}
        self.repository.separate_recording.return_value = {"id": 4}

        linked = self.client.post(
            "/api/downloaded-library/tracks/4/link-version",
            json={"target_identity": "HOU-000009-ORG", "relationship": "RMX"},
        )
        unlinked = self.client.post("/api/downloaded-library/tracks/4/unlink-version")

        self.assertEqual(linked.status_code, 200)
        self.repository.link_recording_version.assert_called_once_with(4, 9, "RMX")
        self.assertEqual(unlinked.json()["track"]["id"], 4)
        self.repository.separate_recording.assert_called_once_with(4)

    def test_repository_errors_preserve_status_contracts(self) -> None:
        self.repository.merge_downloaded_tracks.side_effect = ValueError("Choose two different tracks")
        invalid = self.client.post(
            "/api/downloaded-library/merge-duplicate",
            json={"survivor_id": 1, "duplicate_id": 1},
        )
        self.repository.separate_recording.side_effect = KeyError(99)
        missing = self.client.post("/api/downloaded-library/tracks/99/keep-separate")
        self.repository.track_id_for_identity.return_value = None
        unresolved = self.client.post(
            "/api/downloaded-library/tracks/4/link-version",
            json={"target_identity": "missing", "relationship": "ORG"},
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(unresolved.status_code, 404)


if __name__ == "__main__":
    unittest.main()
