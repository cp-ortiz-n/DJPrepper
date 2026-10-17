from __future__ import annotations

import unittest

from audioextender.set_builder.plan_comparator import PlanQualityComparator


def validation(*, warnings: list[dict], genre: str = "Techno") -> dict:
    return {
        "valid": True,
        "warnings": warnings,
        "plan": [{
            "id": "one", "artist": "Artist", "genre": genre, "detailedGenres": [],
            "descriptors": [], "durationSeconds": 240, "sectionId": "main", "matchTier": "direct",
        }],
    }


class PlanQualityComparatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.journey = {"sections": [{"id": "main", "genres": ["Techno"]}]}

    def test_ai_wins_only_when_quality_improves(self) -> None:
        result = PlanQualityComparator().compare(
            validation(warnings=[]),
            validation(warnings=[{"code": "large-bpm-jump"}]),
            self.journey,
            target_duration_minutes=4,
        )
        self.assertEqual(result["winner"], "ai")
        self.assertEqual(result["scoreDelta"], 6)

    def test_baseline_wins_a_tie(self) -> None:
        result = PlanQualityComparator().compare(
            validation(warnings=[]), validation(warnings=[]), self.journey, target_duration_minutes=4
        )
        self.assertEqual(result["winner"], "deterministic")

    def test_ai_cannot_trade_away_requested_genre_coverage(self) -> None:
        result = PlanQualityComparator().compare(
            validation(warnings=[], genre="House"),
            validation(warnings=[{"code": "large-bpm-jump"}]),
            self.journey,
            target_duration_minutes=4,
        )
        self.assertEqual(result["winner"], "deterministic")
        self.assertFalse(result["coveragePreserved"])


if __name__ == "__main__":
    unittest.main()
