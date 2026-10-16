from __future__ import annotations

import unittest

from audioextender.set_builder.transition_optimizer import (
    DeterministicTransitionOptimizer,
    bpm_distance_ratio,
    weak_harmonic_transition,
)


def track(identifier: str, bpm: float, *, energy: float = 0.5, camelot: str = "8A") -> dict:
    return {
        "id": identifier,
        "bpm": bpm,
        "energy": energy,
        "camelot": camelot,
        "vocals": "mixed",
    }


class TransitionPolicyTests(unittest.TestCase):
    def test_half_and_double_time_are_compatible(self) -> None:
        self.assertEqual(bpm_distance_ratio(track("slow", 75), track("fast", 150)), 0)

    def test_camelot_neighbors_are_compatible_but_distant_keys_are_not(self) -> None:
        self.assertFalse(weak_harmonic_transition(track("one", 120, camelot="8A"), track("two", 121, camelot="9A")))
        self.assertTrue(weak_harmonic_transition(track("one", 120, camelot="8A"), track("two", 121, camelot="2B")))

    def test_optimizer_preserves_sections_and_reduces_bpm_discontinuity(self) -> None:
        first = {"id": "opening", "energyStart": 4, "energyEnd": 6}
        second = {"id": "peak", "energyStart": 6, "energyEnd": 8}
        ordered = DeterministicTransitionOptimizer().optimize([
            (first, [
                track("c", 120, energy=0.6), track("a", 100, energy=0.4), track("b", 110, energy=0.5),
            ]),
            (second, [
                track("f", 150, energy=0.8), track("d", 130, energy=0.6), track("e", 140, energy=0.7),
            ]),
        ])
        self.assertEqual(
            [section for section, _ in ordered],
            ["opening", "opening", "opening", "peak", "peak", "peak"],
        )
        self.assertEqual({value["id"] for _, value in ordered}, {"a", "b", "c", "d", "e", "f"})
        self.assertEqual([value["id"] for _, value in ordered], ["a", "b", "c", "d", "e", "f"])


if __name__ == "__main__":
    unittest.main()
