"""Detect existing mixable intros/outros that should be preserved."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.core.defaults import (
    DJ_READY_GRID_THRESHOLD,
    DJ_READY_MINIMUM_LOUDNESS,
    DJ_READY_MINIMUM_PERCUSSION,
    DJ_READY_MINIMUM_PERCUSSIVE_RATIO,
)


@dataclass(frozen=True)
class SideReadiness:
    """Readiness summary for a single side of a track."""

    mixable_bars: int
    confidence: float


@dataclass(frozen=True)
class DJReadiness:
    """Readiness scores for the intro and outro edges of a track."""

    intro: SideReadiness
    outro: SideReadiness


def detect_dj_readiness(analysis: TrackAnalysis) -> DJReadiness:
    """Count consecutive mixable bars already present at each edge."""
    boundaries = analysis.bar_boundaries
    bar_count = min(len(boundaries) - 1, len(analysis.bar_grid_confidence))
    qualities: list[float] = []
    safe: list[bool] = []
    for index in range(max(0, bar_count)):
        start, end = float(boundaries[index]), float(boundaries[index + 1])
        mask = (analysis.frame_times >= start) & (analysis.frame_times < end)
        if np.count_nonzero(mask) < 4:
            qualities.append(0.0)
            safe.append(False)
            continue
        loudness = float(np.mean(analysis.rms[mask]))
        percussion = float(np.mean(analysis.percussion_rms[mask]))
        ratio = float(np.mean(analysis.percussion_rms[mask] / (analysis.rms[mask] + 1e-5)))
        grid = float(analysis.bar_grid_confidence[index])
        quality = float(
            np.clip(
                0.35 * grid
                + 0.30 * min(1.0, percussion / DJ_READY_MINIMUM_PERCUSSION)
                + 0.20 * min(1.0, ratio / DJ_READY_MINIMUM_PERCUSSIVE_RATIO)
                + 0.15 * min(1.0, loudness / DJ_READY_MINIMUM_LOUDNESS),
                0.0,
                1.0,
            )
        )
        qualities.append(quality)
        safe.append(
            grid >= DJ_READY_GRID_THRESHOLD
            and loudness >= DJ_READY_MINIMUM_LOUDNESS
            and percussion >= DJ_READY_MINIMUM_PERCUSSION
            and ratio >= DJ_READY_MINIMUM_PERCUSSIVE_RATIO
        )

    labels = analysis.bar_section_labels

    def consecutive(indices: range, accepted_roles: set[str]) -> SideReadiness:
        selected: list[float] = []
        for index in indices:
            role = str(labels[index]) if index < len(labels) else "unknown"
            if not safe[index] or role not in accepted_roles:
                break
            selected.append(qualities[index])
        return SideReadiness(len(selected), float(np.mean(selected)) if selected else 0.0)

    return DJReadiness(
        consecutive(range(min(bar_count, 16)), {"intro"}),
        consecutive(
            range(bar_count - 1, max(-1, bar_count - 17), -1),
            {"closing", "fade"},
        ),
    )
