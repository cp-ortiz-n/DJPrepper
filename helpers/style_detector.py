"""Heuristic song-style classification for automatic preset selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from helpers.analysis import TrackAnalysis


@dataclass(frozen=True)
class StyleDecision:
    style: str
    preset: str
    reason: str


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

    if vocal_energy is not None:
        vocal_density = float(np.mean(vocal_energy >= 0.20))
        if vocal_density >= 0.34:
            return StyleDecision(
                "vocal-forward",
                "vocal-safe",
                f"vocals occupy {vocal_density:.0%} of analyzed frames",
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

    return StyleDecision(
        "mixed/subtle",
        "subtle",
        f"percussion {percussion:.2f}, grid {grid:.0f}%, dynamics {dynamic_range:.2f}",
    )
