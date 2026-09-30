from __future__ import annotations

import unittest

import numpy as np

from helpers.analysis import _ensemble_key_estimate, _estimate_key

MAJOR_PROFILE = np.asarray(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.asarray(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)


class KeyAnalysisTests(unittest.TestCase):
    def test_major_profile_selects_the_expected_key(self) -> None:
        chroma = np.tile(MAJOR_PROFILE[:, None], (1, 240))

        label, confidence, root, mode = _estimate_key(chroma)

        self.assertEqual((label, root, mode), ("C major", 0, "major"))
        self.assertGreater(confidence, 60.0)

    def test_minor_profile_selects_the_expected_key(self) -> None:
        chroma = np.tile(np.roll(MINOR_PROFILE, 9)[:, None], (1, 240))

        label, _confidence, root, mode = _estimate_key(chroma)

        self.assertEqual((label, root, mode), ("A minor", 9, "minor"))

    def test_result_is_deterministic_for_ambiguous_input(self) -> None:
        chroma = np.ones((12, 240), dtype=float)

        first = _estimate_key(chroma)
        second = _estimate_key(chroma)

        self.assertEqual(first, second)

    def test_consensus_detectors_can_safely_override_primary(self) -> None:
        primary = np.tile(MINOR_PROFILE[:, None], (1, 120))
        consensus = np.tile(np.roll(MAJOR_PROFILE, 7)[:, None], (1, 120))

        label, _confidence, root, mode, candidates = _ensemble_key_estimate(
            primary, consensus, consensus
        )

        self.assertEqual((label, root, mode), ("G major", 7, "major"))
        self.assertEqual(candidates[0]["reason"], "harmonic+CQT consensus")

    def test_disagreement_preserves_primary_and_reduces_confidence(self) -> None:
        primary = np.tile(MAJOR_PROFILE[:, None], (1, 120))
        harmonic = np.tile(np.roll(MAJOR_PROFILE, 7)[:, None], (1, 120))
        cqt = np.tile(np.roll(MINOR_PROFILE, 9)[:, None], (1, 120))
        primary_confidence = _estimate_key(primary)[1]

        label, confidence, root, mode, candidates = _ensemble_key_estimate(
            primary, harmonic, cqt
        )

        self.assertEqual((label, root, mode), ("C major", 0, "major"))
        self.assertLess(confidence, primary_confidence)
        self.assertEqual(len(candidates), 3)


if __name__ == "__main__":
    unittest.main()
