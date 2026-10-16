from __future__ import annotations

import unittest

import numpy as np

from audioextender.audio.loading import AudioData
from audioextender.audio.redrum import create_redrum_intro, redrum_added_seconds
from audioextender.library.cue_export import build_cue_points
from audioextender.processing.extended_edit import (
    _smooth_join,
    adaptive_crossfade_ms,
    create_extended_edit,
    insert_audio_region,
    optimize_candidate_boundaries,
)
from tests.support.factories import candidate


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

    def test_regional_boundary_risk_reduces_musical_scores(self) -> None:
        compatible = candidate(regional_compatibility=0.95, regional_boundary_risk=0.0)
        conflicting = candidate(regional_compatibility=0.25, regional_boundary_risk=0.8)
        self.assertGreater(compatible.phrase_suitability, conflicting.phrase_suitability)
        self.assertGreater(compatible.transition_quality, conflicting.transition_quality)

    def test_crossfade_is_bounded_and_adapts_to_bass_risk(self) -> None:
        clean = candidate(splice_mode="zero-crossing")
        risky = candidate(splice_mode="bass-preserving", bass_compatibility=0.3)
        self.assertEqual(adaptive_crossfade_ms(clean, 6.0), 10.0)
        self.assertGreater(adaptive_crossfade_ms(risky, 6.0), 20.0)
        self.assertLessEqual(adaptive_crossfade_ms(risky, 6.0), 30.0)


class SpliceTests(unittest.TestCase):
    def test_redrum_cues_use_generated_output_timeline(self) -> None:
        analysis = type(
            "Analysis",
            (),
            {
                "bar_grid_confidence": np.asarray([], dtype=float),
                "bar_boundaries": np.asarray([], dtype=float),
            },
        )()
        redrum = candidate(
            start=57.0,
            end=65.0,
            repetitions=2,
            splice_mode="redrum",
        )
        cues = build_cue_points(analysis, redrum, None, 10.0, 250.0)
        extended = next(cue for cue in cues if cue.name == "Extended Intro")
        original = next(cue for cue in cues if cue.name == "Original Song Starts")
        self.assertEqual((extended.start, extended.end), (0.0, 16.0))
        self.assertEqual(original.start, 16.0)

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

    def test_audio_region_can_be_inserted_at_an_arrangement_destination(self) -> None:
        sample_rate = 1000
        time = np.arange(10 * sample_rate, dtype=np.float32) / sample_rate
        samples = np.column_stack((np.sin(2 * np.pi * time), np.sin(2 * np.pi * time))).astype(np.float32)
        audio = AudioData(samples, sample_rate)
        result = insert_audio_region(
            audio,
            audio,
            source_start=2.0,
            source_end=4.0,
            destination=7.0,
            copies=2,
            crossfade_ms=10.0,
        )
        self.assertEqual(result.samples.shape[1], 2)
        self.assertGreater(result.duration, 13.9)
        self.assertLess(result.duration, 14.0)
        self.assertLessEqual(float(np.max(np.abs(result.samples))), 1.000001)

    def test_boundary_optimization_only_micro_adjusts_phrase_duration(self) -> None:
        time = np.linspace(0, 12, 1200, endpoint=False)
        samples = np.column_stack((np.sin(2 * np.pi * time), np.sin(2 * np.pi * time))).astype(np.float32)
        optimized = optimize_candidate_boundaries(AudioData(samples, 100), candidate())
        self.assertLessEqual(abs((optimized.end - optimized.start) - 4.0), 0.0081)
        self.assertLessEqual(abs(optimized.boundary_adjustment_ms), 40.0)
        self.assertLessEqual(abs(optimized.duration_adjustment_ms), 8.1)

    def test_low_grid_sustained_material_gets_a_longer_fade(self) -> None:
        uncertain = candidate(
            boundary_grid_confidence=0.4,
            rhythmic_strength=0.3,
            splice_mode="adaptive",
        )
        self.assertGreater(adaptive_crossfade_ms(uncertain, 10.0), 30.0)
        self.assertLessEqual(adaptive_crossfade_ms(uncertain, 10.0), 80.0)

    def test_redrum_prepends_requested_phrase_without_repeating_melody(self) -> None:
        samples = np.zeros((1200, 2), dtype=np.float32)
        samples[400:800:25] = 0.5
        audio = AudioData(samples, 100)
        redrum = candidate(
            start=4.0,
            end=8.0,
            repetitions=2,
            splice_mode="redrum",
        )
        drums = AudioData(np.zeros_like(samples), 100)
        edited = create_redrum_intro(audio, audio, redrum, drums)
        self.assertEqual(len(edited.samples), len(samples) + 800)
        self.assertEqual(redrum_added_seconds(redrum), 8.0)
        self.assertTrue(np.array_equal(edited.samples[-400:], samples[-400:]))

    def test_redrum_fades_the_original_opening_in_beneath_the_drums(self) -> None:
        samples = np.full((1200, 2), 0.25, dtype=np.float32)
        samples[400:800:25] += 0.25
        audio = AudioData(samples, 100)
        redrum = candidate(
            start=4.0,
            end=8.0,
            unit_bars=4,
            repetitions=1,
            splice_mode="redrum",
        )
        drums = AudioData(np.zeros_like(samples), 100)
        edited = create_redrum_intro(audio, audio, redrum, drums)
        original_entry = 400
        # The master begins silent beneath the continuing drum bed, then reaches
        # its untouched level after the configured two-bar fade.
        self.assertLess(
            float(np.mean(np.abs(edited.samples[original_entry]))),
            float(np.mean(np.abs(samples[0]))),
        )
        self.assertAlmostEqual(
            float(np.mean(edited.samples[original_entry + 250])),
            float(np.mean(samples[250])),
            delta=0.12,
        )


if __name__ == "__main__":
    unittest.main()
