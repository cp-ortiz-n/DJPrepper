from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audioextender.set_builder.preference_learning import DJPreferenceService, JsonPreferenceStore
from audioextender.set_builder.review_service import SetReviewService
from audioextender.web.set_review_routes import create_set_review_router


def track(track_id: str, decision: str, adjustment: float = 0, rank_delta: int = 0) -> dict:
    return {
        "trackId": track_id,
        "title": track_id,
        "decision": decision,
        "reason": "wrong-energy" if decision == "reject" else "",
        "features": {"genre": ["latin house"], "energy": ["medium"]},
        "technicalScore": 70,
        "preferenceAdjustment": adjustment,
        "rankDelta": rank_delta,
        "matchTier": "direct",
    }


def transition(pair_id: str, rating: int) -> dict:
    return {
        "pairId": pair_id,
        "rating": rating,
        "features": {
            "bpmMovement": "rising",
            "keyCompatibility": "strong",
            "vocalOverlap": "spaced",
            "energyMovement": "rising",
            "bars": "16",
            "technique": "bass-swap",
        },
    }


class SetReviewServiceTests(unittest.TestCase):
    def service(self, root: Path) -> tuple[SetReviewService, DJPreferenceService]:
        preferences = DJPreferenceService(JsonPreferenceStore(root / "preferences.json"))
        reviews = SetReviewService(JsonPreferenceStore(root / "reviews.json"), preferences.profile)
        return reviews, preferences

    def test_reports_acceptance_delta_rank_changes_reasons_and_catalog_fit(self) -> None:
        with TemporaryDirectory() as temporary:
            reviews, _ = self.service(Path(temporary))
            reviews.record({
                "setId": "set-one",
                "context": "warm-up",
                "overallDecision": "accept",
                "tracks": [track("one", "accept", 4, 2), track("two", "reject")],
                "evaluation": {"tierCounts": {"direct": 1, "bridge": 1}},
            })
            report = reviews.report("warm-up")
        self.assertEqual(report["overallAccepted"], 1)
        self.assertEqual(report["tracks"]["changedByPersonalization"], 1)
        self.assertEqual(report["tracks"]["personalizedAcceptanceRate"], 1)
        self.assertEqual(report["tracks"]["neutralAcceptanceRate"], 0)
        self.assertEqual(report["tracks"]["acceptanceRateDelta"], 1)
        self.assertEqual(report["tracks"]["rejectionReasons"], {"wrong-energy": 1})
        self.assertEqual(report["catalogFit"], {"direct": 1, "expanded": 1})

    def test_transition_learning_requires_three_distinct_pairs_and_is_bounded(self) -> None:
        with TemporaryDirectory() as temporary:
            reviews, _ = self.service(Path(temporary))
            reviews.record({"setId": "one", "transitions": [transition("a-b", 5), transition("b-c", 5)]})
            self.assertFalse(reviews.report()["transitionProfile"]["activeSignals"])
            reviews.record({"setId": "two", "transitions": [transition("c-d", 5), transition("d-e", 5)]})
            profile = reviews.report()["transitionProfile"]
        signal = next(item for item in profile["activeSignals"] if item["dimension"] == "technique")
        self.assertEqual(signal["value"], "bass-swap")
        self.assertEqual(signal["evidenceCount"], 4)
        self.assertEqual(signal["adjustment"], 8)

    def test_detects_contextual_contradictions_and_persists_after_restart(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            reviews, preferences = self.service(root)
            reviews.record({"setId": "one", "context": "peak-time", "tracks": [track("same", "accept")]})
            reviews.record({"setId": "two", "context": "peak-time", "tracks": [track("same", "reject")]})
            restarted = SetReviewService(JsonPreferenceStore(root / "reviews.json"), preferences.profile)
            report = restarted.report("peak-time")
        self.assertEqual(report["reviewCount"], 2)
        self.assertEqual(report["contradictoryTrackIds"], ["same"])
        self.assertIn("contradictory-feedback", {item["code"] for item in report["recommendations"]})

    def test_route_records_review_and_updates_track_preferences(self) -> None:
        with TemporaryDirectory() as temporary:
            reviews, preferences = self.service(Path(temporary))
            app = FastAPI()
            app.include_router(create_set_review_router(reviews, preferences))
            client = TestClient(app)
            response = client.post("/api/set-builder/reviews", json={
                "setId": "set-one",
                "context": "warm-up",
                "overallDecision": "accept",
                "tracks": [track("one", "accept")],
                "transitions": [transition("one-two", 4)],
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["report"]["reviewCount"], 1)
            self.assertEqual(preferences.profile("warm-up")["eventCount"], 1)
            self.assertEqual(client.delete("/api/set-builder/reviews").json()["reviewCount"], 0)


if __name__ == "__main__":
    unittest.main()
