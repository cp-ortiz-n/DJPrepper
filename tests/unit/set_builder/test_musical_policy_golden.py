from __future__ import annotations

import json
import unittest

from audioextender.library.musical_profile import CAMELOT_KEYS, MUSICAL_PROFILE_VERSION, musical_profile, normalize_key
from audioextender.set_builder.transition_optimizer import transition_cost
from tests.support.paths import FIXTURES

FIXTURE = json.loads((FIXTURES / "musical_policy_golden.json").read_text(encoding="utf-8"))


class MusicalPolicyGoldenTests(unittest.TestCase):
    def test_backend_catalog_profiles_match_golden_fixture(self) -> None:
        for case in FIXTURE["profiles"]:
            with self.subTest(case=case["name"]):
                profile = musical_profile(case["song"])
                self.assertEqual(profile["version"], MUSICAL_PROFILE_VERSION)
                self.assertEqual(profile["roles"], case["roles"])
                self.assertAlmostEqual(profile["energy"], case["energy"])
                self.assertEqual(profile["energy_band"], case["energy_band"])
                self.assertEqual(profile["vocals"], case["vocals"])
                self.assertEqual(profile["timing"], case["timing"])
                self.assertEqual(set(profile["confidence"]), {"key", "energy", "roles", "vocals", "timing"})
                self.assertEqual(set(profile["provenance"]), {"key", "energy", "roles", "vocals", "timing"})

    def test_backend_camelot_mapping_matches_golden_fixture(self) -> None:
        for case in FIXTURE["keys"]:
            with self.subTest(key=case["input"]):
                self.assertEqual(normalize_key(case["input"]), case["normalized"])
                expected = None if case["camelot"] == "—" else case["camelot"]
                self.assertEqual(CAMELOT_KEYS.get(case["normalized"]), expected)

    def test_set_transition_cost_matches_golden_fixture(self) -> None:
        for case in FIXTURE["set_transitions"]:
            with self.subTest(case=case["name"]):
                self.assertAlmostEqual(transition_cost(case["left"], case["right"]), case["cost"])


if __name__ == "__main__":
    unittest.main()
