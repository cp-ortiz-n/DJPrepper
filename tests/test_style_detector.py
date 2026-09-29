from __future__ import annotations

import unittest

import numpy as np

from helpers.analysis import TrackAnalysis
from helpers.style_detector import classify_track_sections, detect_editing_style
from helpers.track_processor import _arrangement_sections


def analysis(
    *,
    bpm: float = 120.0,
    percussion: float = 0.35,
    harmonic: float = 0.35,
    onset: float = 0.30,
    grid: float = 70.0,
    drift: float = 2.0,
    groove: str = "straight",
    timing: str = "steady",
    dynamic_low: float = 0.3,
    dynamic_high: float = 0.6,
) -> TrackAnalysis:
    frames = np.linspace(0.0, 10.0, 32)
    rms = np.linspace(dynamic_low, dynamic_high, 32)
    values = np.full(32, onset)
    return TrackAnalysis(
        bpm=bpm,
        tempo_drift_percent=drift,
        beat_grid_confidence=grid,
        key_label="C major",
        key_confidence=70.0,
        key_root=0,
        key_mode="major",
        groove_label=groove,
        swing_ratio=1.0,
        timing_label=timing,
        downbeat_continuity=0.8,
        bar_grid_confidence=np.ones(8),
        bar_section_labels=np.asarray(["groove"] * 8),
        bar_section_confidence=np.ones(8),
        beat_times=np.arange(32, dtype=float),
        downbeat_indices=np.arange(0, 32, 4),
        bar_boundaries=np.arange(9, dtype=float),
        frame_times=frames,
        rms=rms,
        onset=values,
        percussion_rms=np.full(32, percussion),
        harmonic_rms=np.full(32, harmonic),
        bass_rms=np.full(32, 0.3),
        spectral_centroid=np.full(32, 0.4),
        spectral_flux=np.full(32, 0.2),
        chroma=np.ones((12, 32)),
        spectral_profile=np.ones((8, 32)),
    )


class StyleDetectorTests(unittest.TestCase):
    def test_adjacent_arrangement_bars_are_merged_for_timeline(self) -> None:
        track = analysis()
        track.bar_section_labels = np.asarray(
            ["intro", "intro", "verse", "verse", "buildup", "chorus", "closing", "closing"]
        )
        track.bar_section_confidence = np.asarray([.7, .8, .6, .7, .65, .75, .8, .9])
        sections = _arrangement_sections(track)
        self.assertEqual(
            [section.label for section in sections],
            ["intro", "verse", "buildup", "chorus", "closing"],
        )
        self.assertAlmostEqual(sections[0].confidence, .75)

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
        decision = detect_editing_style(
            analysis(bpm=132, percussion=0.60, onset=0.40, grid=78)
        )
        self.assertEqual((decision.style, decision.preset), ("peak-energy", "peak-time"))

    def test_detects_breakbeat(self) -> None:
        decision = detect_editing_style(
            analysis(percussion=0.42, grid=58, groove="loose/syncopated")
        )
        self.assertEqual(decision.preset, "breakbeat")

    def test_detects_ambient_material(self) -> None:
        decision = detect_editing_style(
            analysis(percussion=0.10, harmonic=0.35, onset=0.12, grid=55)
        )
        self.assertEqual(decision.preset, "ambient")

    def test_detects_live_timing(self) -> None:
        decision = detect_editing_style(
            analysis(percussion=0.30, drift=12, grid=58, timing="variable/live")
        )
        self.assertEqual(decision.preset, "live-acoustic")

    def test_detects_melodic_steady_material(self) -> None:
        decision = detect_editing_style(
            analysis(percussion=0.24, harmonic=0.48, onset=0.25, grid=72)
        )
        self.assertEqual(decision.preset, "melodic")

    def test_vocal_density_takes_priority(self) -> None:
        vocal = np.full(32, 0.5)
        decision = detect_editing_style(analysis(), vocal)
        self.assertEqual(decision.preset, "vocal-safe")


if __name__ == "__main__":
    unittest.main()
