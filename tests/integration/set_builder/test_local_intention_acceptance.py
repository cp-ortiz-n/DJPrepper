"""Optional live acceptance tests for the in-house Ollama intention planner."""

from __future__ import annotations

import os
import unittest

from audioextender.set_builder.brief_preparation import BriefPreparationService
from audioextender.set_builder.intention_planner import IntentionPlanner
from audioextender.set_builder.plan_validator import SetPlanValidator
from audioextender.set_builder.track_planner import AITrackPlanner, SetPlanningModelClient


@unittest.skipUnless(os.getenv("AUDIOEXTENDER_RUN_LOCAL_LLM_TESTS") == "1", "local LLM acceptance tests are opt-in")
class LocalIntentionAcceptanceTests(unittest.TestCase):
    planner: IntentionPlanner

    @classmethod
    def setUpClass(cls) -> None:
        cls.planner = IntentionPlanner(provider="ollama", ollama_model="qwen3.5:4b")

    def interpret(self, brief: str) -> dict:
        return self.planner.interpret(
            brief,
            [
                "Reggaeton",
                "Dembow",
                "R&B",
                "Latin House",
                "Latin Techno",
                "Schranz",
                "Afro House",
                "Bachata",
                "Cumbia",
                "Merengue",
                "Salsa",
                "House",
                "Techno",
                {"canonical": "Disco & Funk", "aliases": ["Disco", "Funk"]},
                {"canonical": "Hip-Hop & Rap", "aliases": ["Hip Hop", "Rap"]},
                {"canonical": "Indian / South Asian", "aliases": ["Indian", "South Asian"]},
            ],
        )

    def prepare(self, brief: str) -> dict:
        return BriefPreparationService(self.planner).prepare(
            brief,
            [
                "Reggaeton",
                "Dembow",
                "R&B",
                "Latin House",
                "Latin Techno",
                "Schranz",
                "Afro House",
                "Bachata",
                "Cumbia",
                "Merengue",
                "Salsa",
                "House",
                "Techno",
                {"canonical": "Disco & Funk", "aliases": ["Disco", "Funk"]},
                {"canonical": "Hip-Hop & Rap", "aliases": ["Hip Hop", "Rap"]},
                {"canonical": "Indian / South Asian", "aliases": ["Indian", "South Asian"]},
            ],
            60,
        )

    def test_prompt_matrix_preserves_positive_negative_positional_and_energy_intent(self) -> None:
        cases = [
            ("Create a latin disco set, high energy.", ["disco & funk"], []),
            ("Create a latin techno set, latin house to warmup", ["latin house", "latin techno"], []),
            (
                "Create an indian party song set, high energy all around. No rap",
                ["indian south asian"],
                ["hip hop & rap"],
            ),
            ("Create a disco set without techno", ["disco & funk"], ["techno"]),
            ("Start with Afro House, then Techno", ["afro house", "techno"], []),
            ("Build a Latin House set, no Schranz", ["latin house"], ["schranz"]),
        ]
        for brief, sequence, excluded in cases:
            with self.subTest(brief=brief):
                result = self.prepare(brief)
                interpretation = result["interpretation"]
                self.assertEqual(interpretation["genreSequence"], sequence)
                self.assertEqual(interpretation["excludedGenres"], excluded)
                planned = [genre for section in result["journey"]["sections"] for genre in section["genres"]]
                cursor = 0
                for genre in planned:
                    if cursor < len(sequence) and genre == sequence[cursor]:
                        cursor += 1
                self.assertEqual(cursor, len(sequence))
                self.assertFalse(set(planned).intersection(excluded))
                if "high energy all around" in brief.casefold():
                    self.assertTrue(
                        all(
                            section["energyStart"] >= 8 and section["energyEnd"] >= 8
                            for section in result["journey"]["sections"]
                        )
                    )

    def test_chill_latin_kickback_with_melodic_beginning(self) -> None:
        result = self.interpret(
            "Build a reggaeton and dembow mix with some R&B and hip hop for a chill kickback where people will dance. "
            "Put something melodic in the beginning and keep it from getting too crazy."
        )
        self.assertIn("melodic", result["opening"])
        self.assertTrue({"reggaeton", "dembow"}.issubset(set(result["requestedGenres"])))
        self.assertTrue({"r&b", "hip hop"}.intersection(result["requestedGenres"] + result["optionalGenres"]))
        self.assertIn(result["vibe"], {"balanced", "dance-party", "warm-up"})

    def test_latin_techno_waves_and_optional_schranz(self) -> None:
        result = self.interpret(
            "Make a Latin Techno and Latin House journey. Start melodic to warm up, use varying energy waves, "
            "and add a little Schranz if available."
        )
        self.assertEqual(result["opening"], "melodic")
        self.assertEqual(result["curve"], "waves")
        self.assertIn("schranz", result["optionalGenres"])
        self.assertTrue({"latin techno", "latin house"}.issubset(set(result["requestedGenres"])))

    def test_lounge_warmup_with_explicit_smooth_ending(self) -> None:
        result = self.interpret(
            "Create a relaxed House and Afro House lounge warm-up. Begin organic and melodic, build gently in the "
            "middle, and close smoothly without turning into peak-time music."
        )
        self.assertIn("melodic", result["opening"])
        self.assertIsNotNone(result["ending"])
        self.assertEqual(result["vibe"], "warm-up")
        self.assertIn("peak time", " ".join(result["avoided"]).replace("-", " "))

    def test_peak_time_request_is_not_mistaken_for_warmup(self) -> None:
        result = self.interpret(
            "Build a peak-time Techno set with a strong rise, a hard central peak, and a euphoric close."
        )
        self.assertEqual(result["vibe"], "peak-time")
        self.assertIn(result["curve"], {"rise", "peak-release"})
        self.assertIsNotNone(result["ending"])
        self.assertIn("techno", result["requestedGenres"])

    def test_latin_party_sections_remain_in_performance_order(self) -> None:
        result = self.interpret(
            "Start with some melodic Latin songs to bring up the mood. From there add Cumbia and Merengue to get "
            "people dancing, then Bachata and Salsa. End with fun Latin Techno and Schranz for a Latin party."
        )
        expected = ["cumbia", "merengue", "bachata", "salsa", "latin techno", "schranz"]
        self.assertEqual(result["genreSequence"], expected)
        self.assertIn("melodic", result["opening"])

    def test_local_model_selects_only_supplied_track_ids(self) -> None:
        def candidate(identifier: str, section: str, genre: str) -> dict:
            return {
                "id": identifier,
                "title": identifier,
                "artist": "Test Artist",
                "genre": genre,
                "detailedGenres": [genre],
                "descriptors": [],
                "bpm": 122,
                "key": "8A",
                "camelot": "8A",
                "energy": 0.6,
                "durationSeconds": 240,
                "vocals": "mixed",
                "timing": "steady",
                "roles": [],
                "available": True,
                "matchTier": "direct",
                "relevanceScore": 90,
                "required": False,
                "locked": False,
                "eligibleSectionIds": [section],
                "reasons": [],
            }

        journey = {
            "sections": [
                {"id": "opening", "name": "Opening", "durationPercent": 50, "genres": ["Reggaeton"]},
                {"id": "peak", "name": "Peak", "durationPercent": 50, "genres": ["Latin Techno"]},
            ]
        }
        pool = {
            "sections": [
                {"sectionId": "opening", "candidates": [candidate("downloaded:1", "opening", "Reggaeton")]},
                {"sectionId": "peak", "candidates": [candidate("downloaded:2", "peak", "Latin Techno")]},
            ]
        }
        result = AITrackPlanner(
            SetPlanningModelClient(self.planner), SetPlanValidator(duration_tolerance=0.5), timeout_seconds=90
        ).plan(
            brief={"identity": {"text": "Open with Reggaeton and finish with Latin Techno."}},
            journey=journey,
            candidate_pool=pool,
            target_track_count=2,
            target_duration_minutes=8,
            required_ids=set(),
            excluded_ids=set(),
            locked_ids=set(),
        )
        self.assertIn(result["mode"], {"ai-planned", "deterministic-fallback"})
        self.assertIsNotNone(result["comparison"])
        self.assertEqual({track["id"] for track in result["plan"]}, {"downloaded:1", "downloaded:2"})
