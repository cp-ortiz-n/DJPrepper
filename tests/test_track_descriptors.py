from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.repositories.facade import JobRepository
from audioextender.library.identity_inference import infer_identity_descriptors
from audioextender.web.descriptor_routes import DescriptorRouteDependencies, create_descriptor_router


def _wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\0\0" * 80)


class TrackDescriptorTests(unittest.TestCase):
    def test_inference_uses_meaningful_playlist_names_and_ignores_import_buckets(self) -> None:
        suggestions = infer_identity_descriptors({
            "title": "Techno Edit", "genre_category": "Electronic / Techno",
            "playlists": ["Ecuadorian Party", "SoundCloud Imports"],
            "library_roles": "|peak-time|", "vocals": "mixed", "timing": "steady",
        })
        values = {(item["category"], item["value"]) for item in suggestions}
        self.assertIn(("cultural", "ecuadorian"), values)
        self.assertIn(("context", "ecuadorian party"), values)
        self.assertIn(("role", "peak-time"), values)
        self.assertNotIn(("context", "soundcloud imports"), values)

    def test_playlist_names_are_interpreted_instead_of_copied_verbatim(self) -> None:
        indian = infer_identity_descriptors({
            "genre": "Bollywood, Indian Pop", "playlists": ["INDIAN_PARTY_HITS"]
        })
        indian_values = {(item["category"], item["value"]) for item in indian}
        self.assertIn(("cultural", "indian / south asian"), indian_values)
        self.assertIn(("sound", "bollywood pop"), indian_values)
        self.assertIn(("role", "party-ready"), indian_values)
        self.assertIn(("familiarity", "crowd-recognizable"), indian_values)
        self.assertIn(("context", "indian party"), indian_values)
        self.assertNotIn(("context", "indian_party_hits"), indian_values)

        artists = infer_identity_descriptors({"playlists": ["skrillex_and_fred_again"]})
        artist_values = {(item["category"], item["value"]) for item in artists}
        self.assertIn(("sound", "bass-forward"), artist_values)
        self.assertIn(("sound", "emotive electronic"), artist_values)
        self.assertIn(("sound", "vocal-sample driven"), artist_values)
        self.assertIn(("context", "contemporary electronic crossover"), artist_values)
        self.assertNotIn(("context", "skrillex + fred again"), artist_values)

    def test_promotional_playlist_names_are_decomposed_into_controlled_signals(self) -> None:
        suggestions = infer_identity_descriptors({
            "playlists": [
                "best spotify mix party transitions 🎛️",
                "🔥GUARACHA 💊 LAS MEJORES 2026 ⭐🤩 🇨🇴",
                "Afro House Remix of Popular TikTok 2026 🔥 Workout & Gym House Mix",
                "DEMBOW 2026 🍑 LO MÁS ESCUCHADO",
            ]
        })
        values = {(item["category"], item["value"]) for item in suggestions}
        self.assertIn(("context", "party"), values)
        self.assertIn(("context", "workout / gym"), values)
        self.assertIn(("sound", "tribal"), values)
        self.assertIn(("rhythm", "dembow"), values)
        self.assertIn(("cultural", "afro-influenced"), values)
        self.assertIn(("familiarity", "crowd-recognizable"), values)
        self.assertFalse(any("spotify" in value or "2026" in value or "🎛" in value for _, value in values))

    def test_remix_or_edit_alone_does_not_claim_familiarity(self) -> None:
        suggestions = infer_identity_descriptors({"title": "Unknown Original (Club Remix Edit)"})
        self.assertFalse(any(item["category"] == "familiarity" for item in suggestions))

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

    def test_inferred_update_does_not_replace_manual_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root / "Track.wav"; _wav(path)
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(title="Track", artist="Artist", file_path=path)
            repository.update_track_descriptors([track_id], [{"category":"role","value":"peak-time","provenance":"manual","confidence":1}], mode="add")
            repository.update_track_descriptors([track_id], [{"category":"role","value":"peak-time","provenance":"inferred","confidence":.6}], mode="add")
            saved = repository.track_descriptors(track_id)[0]
            self.assertEqual(saved["provenance"], "manual")
            self.assertEqual(saved["confidence"], 1)

    def test_missing_inferred_identity_query_keeps_manual_only_tracks_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); first = root / "First.wav"; second = root / "Second.wav"
            _wav(first); _wav(second)
            repository = JobRepository(root / "catalog.sqlite3")
            first_id = repository.upsert_downloaded_track(title="First", artist="Artist", file_path=first)
            second_id = repository.upsert_downloaded_track(title="Second", artist="Artist", file_path=second)
            repository.update_track_descriptors([first_id], [{"category":"context","value":"my crate","provenance":"manual"}], mode="add")
            repository.update_track_descriptors([second_id], [{"category":"role","value":"warm-up","provenance":"inferred"}], mode="add")
            self.assertEqual(repository.track_ids_missing_inferred_identity(), [first_id])


if __name__ == "__main__":
    unittest.main()
