from __future__ import annotations

import unittest

import numpy as np

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.transition_scorer import assess_custom_insertion


def analysis_fixture() -> TrackAnalysis:
    times = np.linspace(0.0, 32.0, 321)
    pulse = 0.42 + 0.08 * np.sin(2 * np.pi * times / 2.0)
    chroma = np.zeros((12, len(times)))
    chroma[[0, 4, 7]] = 1.0
    return TrackAnalysis(
        bpm=120.0,
        tempo_drift_percent=1.0,
        beat_grid_confidence=90.0,
        key_label="C major",
        key_confidence=85.0,
        key_root=0,
        key_mode="major",
        groove_label="straight",
        swing_ratio=0.5,
        timing_label="stable",
        downbeat_continuity=0.9,
        bar_grid_confidence=np.full(17, 0.9),
        bar_section_labels=np.asarray(["verse"] * 16),
        bar_section_confidence=np.full(16, 0.8),
        beat_times=np.arange(0.0, 32.0, 0.5),
        downbeat_indices=np.arange(0, 64, 4),
        bar_boundaries=np.arange(0.0, 34.0, 2.0),
        frame_times=times,
        rms=pulse,
        onset=pulse,
        percussion_rms=pulse,
        harmonic_rms=pulse,
        bass_rms=pulse,
        spectral_centroid=pulse,
        spectral_flux=pulse,
        chroma=chroma,
        spectral_profile=np.tile(pulse, (8, 1)),
    )


class TransitionScorerTests(unittest.TestCase):
    def test_bar_aligned_compatible_insertion_scores_strongly(self) -> None:
        result = assess_custom_insertion(analysis_fixture(), 4.0, 8.0, 12.0, 2)
        self.assertGreaterEqual(result.score, 75)
        self.assertEqual(result.verdict, "Strong placement")
        self.assertEqual(result.grid, 100)

    def test_off_grid_insertion_reports_grid_warning(self) -> None:
        result = assess_custom_insertion(analysis_fixture(), 4.3, 8.3, 12.3, 2)
        self.assertLess(result.grid, 68)
        self.assertTrue(any("bar boundary" in item for item in result.warnings))

    def test_vocal_boundary_activity_is_reported(self) -> None:
        analysis = analysis_fixture()
        vocals = np.zeros_like(analysis.frame_times)
        vocals[(analysis.frame_times >= 11.5) & (analysis.frame_times <= 12.5)] = 1.0
        result = assess_custom_insertion(analysis, 4.0, 8.0, 12.0, 1, vocals)
        self.assertIsNotNone(result.vocals)
        self.assertTrue(any("vocal phrase" in item for item in result.warnings))

    def test_invalid_bounds_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            assess_custom_insertion(analysis_fixture(), 8.0, 4.0, 12.0, 1)


if __name__ == "__main__":
    unittest.main()
