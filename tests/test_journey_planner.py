from __future__ import annotations

import unittest
from unittest.mock import patch

from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.journey_planner import JourneyPlanner, offline_journey, sanitize_journey


class JourneyPlannerTests(unittest.TestCase):
    def test_sanitizer_rebalances_sections_and_rejects_unknown_genres(self) -> None:
        result = sanitize_journey(
            {
                "summary": "Warm up, dance, then peak.",
                "sections": [
                    {"name": "Open", "purpose": "Warm up", "durationPercent": 20,
                     "genres": ["Cumbia", "Invented Genre"], "characteristics": ["Melodic"],
                     "energyStart": 3, "energyEnd": 5},
                    {"name": "Peak", "purpose": "Finish", "durationPercent": 60,
                     "genres": ["Latin Techno"], "characteristics": ["Peak Time"],
                     "energyStart": 7, "energyEnd": 9},
                ],
            },
            ["Cumbia", "Latin Techno"],
            90,
        )
        self.assertEqual(sum(section["durationPercent"] for section in result["sections"]), 100)
        self.assertEqual(result["sections"][0]["genres"], ["cumbia"])
        self.assertEqual(result["sections"][-1]["endMinute"], 90)

    def test_offline_journey_preserves_order_and_optional_genre(self) -> None:
        journey = offline_journey(
            {"genreSequence": ["Cumbia", "Salsa", "Schranz"], "requestedGenres": [],
             "optionalGenres": ["Schranz"], "opening": "melodic", "ending": "hard",
             "curve": "waves"},
            ["Cumbia", "Salsa", "Schranz"],
            60,
        )
        self.assertEqual([section["genres"][0] for section in journey["sections"]],
                         ["cumbia", "salsa", "schranz"])
        self.assertIn("melodic", journey["sections"][0]["characteristics"])
        self.assertEqual(sum(section["durationPercent"] for section in journey["sections"]), 100)

    def test_invalid_ai_sequence_falls_back_without_losing_requested_genres(self) -> None:
        planner = JourneyPlanner(IntentionPlanner(provider="offline"))
        interpreted = {"genreSequence": ["Cumbia", "Salsa", "Latin Techno"],
                       "requestedGenres": ["Cumbia", "Salsa", "Latin Techno"], "optionalGenres": [],
                       "opening": "melodic", "ending": None, "curve": "rise"}
        invalid = {"summary": "Wrong order", "sections": [
            {"name": "Peak", "purpose": "Peak", "durationPercent": 100,
             "genres": ["Latin Techno"], "characteristics": [], "energyStart": 7, "energyEnd": 9},
        ]}
        with patch.object(JourneyPlanner, "_plan_with_provider", return_value=invalid):
            journey = planner.plan("brief", interpreted, ["Cumbia", "Salsa", "Latin Techno"], 60)
        self.assertEqual(journey["evidence"], "deterministic-fallback")
        self.assertEqual([section["genres"][0] for section in journey["sections"]],
                         ["cumbia", "salsa", "latin techno"])


if __name__ == "__main__":
    unittest.main()
