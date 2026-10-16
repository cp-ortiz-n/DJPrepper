from __future__ import annotations

import unittest

import numpy as np

from audioextender.analysis.style_detector import classify_track_sections, detect_editing_style
from audioextender.processing.track_processor import _arrangement_sections
from tests.factories import track_analysis as analysis


class StyleDetectorTests(unittest.TestCase):
    def test_adjacent_arrangement_bars_are_merged_for_timeline(self) -> None:
        track = analysis()
        track.bar_section_labels = np.asarray(
            ["intro", "intro", "verse", "verse", "buildup", "chorus", "closing", "closing"]
        )
        track.bar_section_confidence = np.asarray([0.7, 0.8, 0.6, 0.7, 0.65, 0.75, 0.8, 0.9])
        sections = _arrangement_sections(track)
        self.assertEqual(
            [section.label for section in sections],
            ["intro", "verse", "buildup", "chorus", "closing"],
        )
        self.assertAlmostEqual(sections[0].confidence, 0.75)

    def test_section_classifier_returns_arrangement_regions(self) -> None:
        profiles = classify_track_sections(analysis())
        self.assertEqual([profile.name for profile in profiles], ["Opening", "Main body", "Ending"])
        self.assertTrue(all(0.55 <= profile.confidence <= 0.93 for profile in profiles))
        self.assertLess(profiles[0].start, profiles[0].end)
        self.assertEqual(profiles[0].end, profiles[1].start)

    def test_section_classifier_uses_vocals_when_available(self) -> None:
        track = analysis(percussion=0.15, harmonic=0.25, onset=0.15)
        profiles = classify_track_sections(track, np.full(32, 0.9))
        self.assertTrue(all(profile.style == "vocal-forward" for profile in profiles))

    def test_detects_peak_energy(self) -> None:
        decision = detect_editing_style(analysis(bpm=132, percussion=0.60, onset=0.40, grid=78))
        self.assertEqual((decision.style, decision.preset), ("peak-energy", "peak-time"))

    def test_detects_breakbeat(self) -> None:
        decision = detect_editing_style(analysis(percussion=0.42, grid=58, groove="loose/syncopated"))
        self.assertEqual(decision.preset, "breakbeat")

    def test_detects_ambient_material(self) -> None:
        decision = detect_editing_style(analysis(percussion=0.10, harmonic=0.35, onset=0.12, grid=55))
        self.assertEqual(decision.preset, "ambient")

    def test_detects_live_timing(self) -> None:
        decision = detect_editing_style(analysis(percussion=0.30, drift=12, grid=58, timing="variable/live"))
        self.assertEqual(decision.preset, "live-acoustic")

    def test_detects_melodic_steady_material(self) -> None:
        decision = detect_editing_style(analysis(percussion=0.24, harmonic=0.48, onset=0.25, grid=72))
        self.assertEqual(decision.preset, "melodic")

    def test_vocal_density_takes_priority(self) -> None:
        vocal = np.full(32, 0.5)
        decision = detect_editing_style(analysis(), vocal)
        self.assertEqual(decision.preset, "vocal-safe")


if __name__ == "__main__":
    unittest.main()
