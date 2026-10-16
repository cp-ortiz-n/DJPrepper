from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.repositories.facade import JobRepository
from audioextender.web.reporting_routes import ReportingRouteDependencies, create_reporting_router


class ReportingRouteTests(unittest.TestCase):
    def test_verified_bpm_validates_persists_refreshes_and_clears(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "catalog.sqlite3"
            repository = JobRepository(database)
            refreshes: list[str] = []
            app = FastAPI()
            app.include_router(
                create_reporting_router(
                    ReportingRouteDependencies(
                        repository=lambda: repository,
                        output_root=root,
                        append_feedback=lambda *_args: None,
                        refresh_library_index=lambda: refreshes.append("refresh"),
                        valid_keys=frozenset({"A minor"}),
                    )
                )
            )
            client = TestClient(app)

            rejected = client.put(
                "/api/bpm-verifications/Track.wav",
                json={"source_name": "Track.wav", "verified_bpm": 301, "detected_bpm": 124},
            )
            self.assertEqual(rejected.status_code, 422)
            saved = client.put(
                "/api/bpm-verifications/Track.wav",
                json={
                    "source_name": "Track.wav",
                    "verified_bpm": 126.25,
                    "detected_bpm": 124,
                    "notes": "Checked against the grid",
                },
            )
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json()["verified_bpm"], 126.25)
            self.assertEqual(refreshes, ["refresh"])
            self.assertEqual(client.get("/api/bpm-verifications").json()["total"], 1)

            restarted = JobRepository(database)
            verification = restarted.bpm_verification("track.wav")
            self.assertIsNotNone(verification)
            assert verification is not None
            self.assertEqual(verification["detected_bpm"], 124)
            removed = client.delete("/api/bpm-verifications/TRACK.WAV")
            self.assertEqual(removed.json(), {"removed": True})
            self.assertEqual(refreshes, ["refresh", "refresh"])
            self.assertIsNone(restarted.bpm_verification("Track.wav"))


if __name__ == "__main__":
    unittest.main()
