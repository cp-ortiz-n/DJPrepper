"""Optional live acceptance tests for the in-house Ollama intention planner."""

from __future__ import annotations

import os
import unittest

from audioextender.set_builder.intention_planner import IntentionPlanner


@unittest.skipUnless(os.getenv("AUDIOEXTENDER_RUN_LOCAL_LLM_TESTS") == "1", "local LLM acceptance tests are opt-in")
class LocalIntentionAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.planner = IntentionPlanner(provider="ollama", ollama_model="qwen3.5:4b")

    def interpret(self, brief: str) -> dict:
        return self.planner.interpret(
            brief,
            ["Reggaeton", "Dembow", "R&B", "Hip Hop", "Latin House", "Latin Techno", "Schranz",
             "Afro House", "Bachata", "Cumbia", "Merengue", "Salsa", "House", "Techno"],
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
