from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.set_builder.candidate_retriever import SetCandidateRetriever
from audioextender.set_builder.preference_learning import (
    DJPreferenceService,
    JsonPreferenceStore,
    PersonalizedCandidateRanker,
)
from audioextender.web.routes.set_preference_routes import create_set_preference_router


def event(track_id: str, action: str = "save", context: str = "warm-up") -> dict:
    return {
        "id": f"{action}-{track_id}",
        "action": action,
        "trackId": track_id,
        "context": context,
        "features": {
            "genre": ["Latin House"],
            "descriptor": ["melodic"],
            "artist": [f"Artist {track_id}"],
            "vocals": ["mixed"],
            "energy": ["medium"],
            "bpm": ["120s"],
        },
    }


class DJPreferenceServiceTests(unittest.TestCase):
    def test_requires_three_distinct_tracks_and_deduplicates_events(self) -> None:
        with TemporaryDirectory() as temporary:
            service = DJPreferenceService(JsonPreferenceStore(Path(temporary) / "preferences.json"))
            service.record([event("one"), event("two")])
            self.assertFalse(service.profile("warm-up")["activeSignals"])
            service.record([event("two"), event("three")])
            profile = service.profile("warm-up")
        genre = next(signal for signal in profile["activeSignals"] if signal["dimension"] == "genre")
        self.assertEqual(genre["value"], "latin house")
        self.assertEqual(genre["evidenceCount"], 3)
        self.assertEqual(profile["eventCount"], 3)

    def test_contexts_are_separate_and_adjustments_are_bounded(self) -> None:
        with TemporaryDirectory() as temporary:
            service = DJPreferenceService(JsonPreferenceStore(Path(temporary) / "preferences.json"))
            service.record([event(str(index), "lock", "peak-time") for index in range(10)])
            self.assertFalse(service.profile("closing")["activeSignals"])
            ranker = PersonalizedCandidateRanker(service.profile)
            adjustment, reasons = ranker.adjustment(
                {
                    "genre": "Latin House",
                    "detailedGenres": [],
                    "descriptors": [],
                    "artist": "Someone",
                    "vocals": "mixed",
                    "energy": 0.5,
                    "bpm": 124,
                },
                "peak-time",
            )
        self.assertEqual(adjustment, 8)
        self.assertTrue(any("latin house" in reason for reason in reasons))

    def test_rekordbox_rating_uses_versioned_mapping(self) -> None:
        def profile(_context: str | None) -> dict:
            return {"enabled": True, "activeSignals": []}

        ranker = PersonalizedCandidateRanker(profile)
        adjustment, reasons = ranker.adjustment(
            {
                "genre": "House",
                "detailedGenres": [],
                "descriptors": [],
                "artist": "Artist",
                "vocals": "mixed",
                "energy": 0.5,
                "bpm": 124,
                "externalRating": {"source": "rekordbox", "rating": 5, "synced_at": "2026-10-21T12:00:00Z"},
            },
            "peak-time",
        )
        self.assertEqual(adjustment, 4)
        self.assertEqual(reasons, ["Rekordbox rating: 5 stars (+4), synced 2026-10-21."])

    def test_rekordbox_rating_and_local_feedback_share_the_total_cap(self) -> None:
        def profile(_context: str | None) -> dict:
            return {
                "enabled": True,
                "activeSignals": [{"dimension": "genre", "value": "house", "adjustment": 10, "evidenceCount": 10}],
            }

        adjustment, reasons = PersonalizedCandidateRanker(profile).adjustment(
            {
                "genre": "House",
                "detailedGenres": [],
                "descriptors": [],
                "artist": "Artist",
                "vocals": "mixed",
                "energy": 0.5,
                "bpm": 124,
                "externalRating": {"source": "rekordbox", "rating": 5},
            },
            "peak-time",
        )

        self.assertEqual(adjustment, 8)
        self.assertEqual(len(reasons), 2)

    def test_pause_reset_and_disk_persistence(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            service = DJPreferenceService(JsonPreferenceStore(path))
            service.record([event(str(index)) for index in range(3)])
            service.set_enabled(False)
            restarted = DJPreferenceService(JsonPreferenceStore(path))
            self.assertFalse(restarted.profile("warm-up")["enabled"])
            self.assertEqual(restarted.profile("warm-up")["eventCount"], 3)
            reset = restarted.reset()
            self.assertTrue(reset["enabled"])
            self.assertEqual(reset["eventCount"], 0)

    def test_dismissed_signal_is_persisted_and_no_longer_affects_ranking(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            service = DJPreferenceService(JsonPreferenceStore(path))
            service.record([event(str(index)) for index in range(3)])
            dismissed = service.dismiss_signal("genre", "Latin House")
            self.assertNotIn("latin house", {signal["value"] for signal in dismissed["activeSignals"]})
            restarted = DJPreferenceService(JsonPreferenceStore(path))
            self.assertEqual(
                restarted.profile()["ignoredSignals"],
                [{"dimension": "genre", "value": "latin house"}],
            )

    def test_http_boundary_supports_record_inspect_pause_and_reset(self) -> None:
        with TemporaryDirectory() as temporary:
            service = DJPreferenceService(JsonPreferenceStore(Path(temporary) / "preferences.json"))
            app = FastAPI()
            app.include_router(create_set_preference_router(service))
            client = TestClient(app)
            recorded = client.post("/api/set-builder/preferences/events", json={"events": [event("one")]})
            self.assertEqual(recorded.status_code, 200)
            self.assertEqual(client.get("/api/set-builder/preferences?context=warm-up").json()["eventCount"], 1)
            self.assertFalse(
                client.put("/api/set-builder/preferences/enabled", json={"enabled": False}).json()["enabled"]
            )
            dismissed = client.request(
                "DELETE",
                "/api/set-builder/preferences/signals",
                json={"dimension": "genre", "value": "Electronic / Techno"},
            )
            self.assertEqual(dismissed.status_code, 200)
            self.assertIn(
                {"dimension": "genre", "value": "electronic / techno"},
                dismissed.json()["ignoredSignals"],
            )
            self.assertEqual(client.delete("/api/set-builder/preferences").json()["eventCount"], 0)

    def test_personalization_changes_soft_rank_but_never_revives_excluded_track(self) -> None:
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            preferred_path = directory / "preferred.wav"
            other_path = directory / "other.wav"
            preferred_path.touch()
            other_path.touch()
            service = DJPreferenceService(JsonPreferenceStore(directory / "preferences.json"))
            service.record([event(str(index)) for index in range(3)])
            retriever = SetCandidateRetriever(preference_ranker=PersonalizedCandidateRanker(service.profile))
            catalog = [
                {
                    "downloaded_id": 1,
                    "genre": "Latin House",
                    "descriptors": [{"value": "melodic"}],
                    "analysis": {"source_name": "Preferred.wav", "bpm": 124, "_energy": 0.5, "_vocals": "mixed"},
                    "job": {"library_path": str(preferred_path)},
                },
                {
                    "downloaded_id": 2,
                    "genre": "Latin House",
                    "analysis": {"source_name": "Other.wav", "bpm": 124, "_energy": 0.5, "_vocals": "mixed"},
                    "job": {"library_path": str(other_path)},
                },
            ]
            journey = {"sections": [{"id": "opening", "genres": ["House"], "energyStart": 5, "energyEnd": 5}]}
            result = retriever.retrieve(catalog, journey, constraints={"vibe": "warm-up"})
            candidates = result["sections"][0]["candidates"]
            self.assertEqual(candidates[0]["id"], "downloaded:1")
            self.assertEqual(candidates[0]["preferenceAdjustment"], 7.5)
            self.assertTrue(any("Learned genre preference" in reason["text"] for reason in candidates[0]["reasons"]))
            excluded = retriever.retrieve(
                catalog, journey, excluded_ids={"downloaded:1"}, constraints={"vibe": "warm-up"}
            )
            self.assertNotIn("downloaded:1", {item["id"] for item in excluded["sections"][0]["candidates"]})


if __name__ == "__main__":
    unittest.main()
