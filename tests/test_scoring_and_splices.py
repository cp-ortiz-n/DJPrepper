from __future__ import annotations

import unittest

import numpy as np

from helpers.audio_loader import AudioData
from helpers.extended_edit import (
    _smooth_join,
    adaptive_crossfade_ms,
    create_extended_edit,
    optimize_candidate_boundaries,
)
from tests.factories import candidate


class CandidateScoringTests(unittest.TestCase):
    def test_clean_candidate_scores_higher_than_risky_candidate(self) -> None:
        clean = candidate()
        risky = candidate(
            buildup_risk=0.9,
            bass_reset_risk=0.9,
            vocal_boundary_risk=0.8,
            harmonic_resolution_risk=0.8,
        )
        self.assertGreater(clean.loop_quality, risky.loop_quality)

    def test_instrumental_quality_removes_vocal_only_penalty(self) -> None:
        vocal = candidate(vocal_phrase_penalty=0.8, vocal_boundary_risk=0.7)
        self.assertGreater(vocal.instrumental_loop_quality, vocal.loop_quality)

    def test_crossfade_is_bounded_and_adapts_to_bass_risk(self) -> None:
        clean = candidate(splice_mode="zero-crossing")
        risky = candidate(splice_mode="bass-preserving", bass_compatibility=0.3)
        self.assertEqual(adaptive_crossfade_ms(clean, 6.0), 10.0)
        self.assertGreater(adaptive_crossfade_ms(risky, 6.0), 20.0)
        self.assertLessEqual(adaptive_crossfade_ms(risky, 6.0), 30.0)


class SpliceTests(unittest.TestCase):
    def test_smooth_join_has_expected_length_and_no_gain_bump(self) -> None:
        left = np.ones((100, 2), dtype=np.float32)
        right = np.ones((100, 2), dtype=np.float32)
        joined = _smooth_join(left, right, 20)
        self.assertEqual(joined.shape, (180, 2))
        self.assertLessEqual(float(np.max(np.abs(joined))), 1.000001)

    def test_no_candidates_returns_an_independent_copy(self) -> None:
        samples = np.zeros((100, 2), dtype=np.float32)
        source = AudioData(samples, 100)
        result = create_extended_edit(source, None, None, 10.0)
        self.assertTrue(np.array_equal(result.samples, source.samples))
        self.assertIsNot(result.samples, source.samples)

    def test_boundary_optimization_preserves_phrase_duration(self) -> None:
        time = np.linspace(0, 12, 1200, endpoint=False)
        samples = np.column_stack((np.sin(2 * np.pi * time), np.sin(2 * np.pi * time))).astype(np.float32)
        optimized = optimize_candidate_boundaries(AudioData(samples, 100), candidate())
        self.assertAlmostEqual(optimized.end - optimized.start, 4.0, places=8)
        self.assertLessEqual(abs(optimized.boundary_adjustment_ms), 20.0)


if __name__ == "__main__":
    unittest.main()
