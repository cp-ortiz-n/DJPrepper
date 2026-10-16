"""Small, deterministic fixtures shared by unit tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_selector import SectionCandidate


def candidate(**changes: Any) -> SectionCandidate:
    """Return a healthy candidate that a test can selectively modify."""
    base = SectionCandidate(
        start=4.0,
        end=8.0,
        score=0.8,
        rhythmic_strength=0.8,
        stability=0.8,
        transition_penalty=0.0,
        instrumentalness=0.8,
        seam_compatibility=0.9,
        harmonic_compatibility=0.9,
        bass_compatibility=0.9,
        timbre_compatibility=0.9,
        structure_consistency=0.8,
        context_compatibility=0.8,
        tail_release_compatibility=0.8,
        chord_return_compatibility=0.8,
        energy_context_match=0.8,
        boundary_grid_confidence=0.9,
        local_grid_confidence=0.9,
        arrangement_fit=0.5,
        energy_shape="stable",
        section_label="intro",
        unit_bars=4,
        repetitions=1,
    )
    return replace(base, **changes)


def track_analysis(
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
    """Return a compact analysis fixture with a stable eight-bar timeline."""
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
