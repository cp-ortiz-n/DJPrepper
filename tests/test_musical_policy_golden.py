from __future__ import annotations

import json
import unittest
from pathlib import Path

from audioextender.set_builder.transition_optimizer import transition_cost
from audioextender.web.application import _CAMELOT_KEYS, _library_energy, _library_roles

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "musical_policy_golden.json").read_text(encoding="utf-8"))


class MusicalPolicyGoldenTests(unittest.TestCase):
    def test_backend_catalog_profiles_match_golden_fixture(self) -> None:
        for case in FIXTURE["profiles"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(_library_roles(case["song"]), case["roles"])
                self.assertAlmostEqual(_library_energy(case["song"]), case["energy"])

    def test_backend_camelot_mapping_matches_golden_fixture(self) -> None:
        for case in FIXTURE["keys"]:
            with self.subTest(key=case["input"]):
                expected = None if case["camelot"] == "—" else case["camelot"]
                self.assertEqual(_CAMELOT_KEYS.get(case["normalized"]), expected)

    def test_set_transition_cost_matches_golden_fixture(self) -> None:
        for case in FIXTURE["set_transitions"]:
            with self.subTest(case=case["name"]):
                self.assertAlmostEqual(transition_cost(case["left"], case["right"]), case["cost"])


if __name__ == "__main__":
    unittest.main()
