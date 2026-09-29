"""Heuristic song-style classification for automatic preset selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from helpers.analysis import TrackAnalysis
from helpers.models import TrackSectionProfile
from helpers.section_context import broad_section_bounds, classify_interval


@dataclass(frozen=True)
class StyleDecision:
    style: str
    preset: str
    reason: str


def classify_track_sections(
    analysis: TrackAnalysis, vocal_energy: np.ndarray | None = None
) -> tuple[TrackSectionProfile, ...]:
    """Describe broad track regions using locally measured musical behavior."""
    profiles: list[TrackSectionProfile] = []
    for name, start, end in broad_section_bounds(analysis):
        behavior = classify_interval(analysis, start, end, vocal_energy)
        if behavior is not None:
            profiles.append(TrackSectionProfile(name, start, end, behavior.style, behavior.confidence, behavior.reason))
    return tuple(profiles)


def detect_editing_style(
    analysis: TrackAnalysis, vocal_energy: np.ndarray | None = None
) -> StyleDecision:
    """Choose a conservative preset from normalized whole-track features."""
    percussion = float(np.clip(np.mean(analysis.percussion_rms), 0.0, 1.0))
    low, high = np.percentile(analysis.rms, [10, 90])
    dynamic_range = float(np.clip(high - low, 0.0, 1.5))
    onset_mean = max(float(np.mean(analysis.onset)), 1e-6)
    onset_variation = float(np.std(analysis.onset) / onset_mean)
    grid = analysis.beat_grid_confidence
    harmonic = float(np.clip(np.mean(analysis.harmonic_rms), 0.0, 1.0))
    harmonic_dominance = harmonic / max(percussion, 0.08)

    if vocal_energy is not None:
        vocal_density = float(np.mean(vocal_energy >= 0.20))
        if vocal_density >= 0.34:
            return StyleDecision(
                "vocal-forward",
                "vocal-safe",
                f"vocals occupy {vocal_density:.0%} of analyzed frames",
            )

    if percussion < 0.18 and onset_mean < 0.22 and harmonic >= 0.16:
        return StyleDecision(
            "ambient/sparse",
            "ambient",
            f"percussion {percussion:.2f}, onset activity {onset_mean:.2f}, harmonic bed {harmonic:.2f}",
        )

    if (
        analysis.tempo_drift_percent >= 8.0
        and percussion < 0.46
        and (grid < 68.0 or analysis.timing_label == "variable/live")
    ):
        return StyleDecision(
            "live/acoustic",
            "live-acoustic",
            f"tempo drift {analysis.tempo_drift_percent:.1f}%, percussion {percussion:.2f}, grid {grid:.0f}%",
        )

    if (
        percussion < 0.24
        or grid < 48.0
        or (dynamic_range > 0.72 and percussion < 0.40)
    ):
        return StyleDecision(
            "slow/dynamic",
            "slow-song",
            f"percussion {percussion:.2f}, grid {grid:.0f}%, dynamics {dynamic_range:.2f}",
        )

    if (
        analysis.bpm >= 128.0
        and percussion >= 0.48
        and grid >= 65.0
        and dynamic_range <= 0.75
        and onset_mean >= 0.28
    ):
        return StyleDecision(
            "peak-energy",
            "peak-time",
            f"{analysis.bpm:.1f} BPM, percussion {percussion:.2f}, onset activity {onset_mean:.2f}",
        )

    if (
        "syncopated" in analysis.groove_label
        and percussion >= 0.32
        and grid >= 48.0
    ):
        return StyleDecision(
            "breakbeat/syncopated",
            "breakbeat",
            f"{analysis.groove_label}, percussion {percussion:.2f}, grid {grid:.0f}%",
        )

    if (
        analysis.bpm >= 105.0
        and percussion >= 0.40
        and grid >= 60.0
        and dynamic_range <= 0.68
        and onset_variation <= 1.75
    ):
        return StyleDecision(
            "rhythm-forward",
            "club",
            f"{analysis.bpm:.1f} BPM, percussion {percussion:.2f}, grid {grid:.0f}%",
        )

    if harmonic_dominance >= 1.35 and percussion >= 0.20 and grid >= 52.0:
        return StyleDecision(
            "melodic-steady",
            "melodic",
            f"harmonic/percussion ratio {harmonic_dominance:.2f}, grid {grid:.0f}%, dynamics {dynamic_range:.2f}",
        )

    return StyleDecision(
        "mixed/subtle",
        "subtle",
        f"percussion {percussion:.2f}, grid {grid:.0f}%, dynamics {dynamic_range:.2f}",
    )
