from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.repositories.facade import JobRepository
from audioextender.web.descriptor_routes import DescriptorRouteDependencies, create_descriptor_router


def _wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\0\0" * 80)


class TrackDescriptorTests(unittest.TestCase):
    def test_descriptor_api_reports_durability_and_returns_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "Track.wav"
            _wav(path)
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(title="Track", artist="Artist", file_path=path)
            invalidations = []
            app = FastAPI()
            app.include_router(create_descriptor_router(DescriptorRouteDependencies(
                repository=lambda: repository,
                invalidate_set_catalog=lambda: invalidations.append(True),
            )))
            response = TestClient(app).put(
                f"/api/downloaded-library/tracks/{track_id}/descriptors",
                json={"descriptors": [{"category": "vocal", "value": "Spanish vocals"}]},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["survives_restart"])
            self.assertEqual(payload["values"][0]["value"], "spanish vocals")
            self.assertEqual(invalidations, [True])

    def test_descriptors_survive_restart_and_appear_in_catalogs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "Artist - Track.wav"
            _wav(path)
            database = root / "catalog.sqlite3"
            repository = JobRepository(database)
            track_id = repository.upsert_downloaded_track(
                title="Track", artist="Artist", file_path=path,
                genre="techno", genre_category="Electronic / Techno",
            )
            result = repository.update_track_descriptors(track_ids=[track_id], descriptors=[
                {"category": "cultural", "value": "Ecuadorian party", "provenance": "manual", "confidence": 1},
                {"category": "rhythm", "value": "Dembow", "provenance": "inferred", "confidence": .72},
            ])
            self.assertEqual(result["updated"], 1)
            restarted = JobRepository(database)
            values = restarted.track_descriptors(track_id)
            self.assertEqual({item["value"] for item in values}, {"ecuadorian party", "dembow"})
            rows, total = restarted.page_downloaded_tracks(page=1, page_size=10, search="ecuadorian")
            self.assertEqual(total, 1)
            self.assertIn("ecuadorian party", rows[0]["descriptors_json"])

    def test_bulk_add_remove_and_missing_tracks_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = JobRepository(root / "catalog.sqlite3")
            ids = []
            for index in range(2):
                path = root / f"Track {index}.wav"
                _wav(path)
                ids.append(repository.upsert_downloaded_track(
                    title=f"Track {index}", artist="Artist", file_path=path,
                ))
            descriptor = [{"category": "context", "value": "peak-time", "provenance": "manual", "confidence": 1}]
            result = repository.update_track_descriptors([*ids, 999999], descriptor, mode="add")
            self.assertEqual(result["updated"], 2)
            self.assertEqual(result["missing"], [999999])
            repository.update_track_descriptors(ids, descriptor, mode="remove")
            self.assertTrue(all(repository.track_descriptors(track_id) == [] for track_id in ids))


if __name__ == "__main__":
    unittest.main()
