"""Pure policy decisions for choosing a splice treatment."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from audioextender.analysis.section_selector import SectionCandidate
from audioextender.core.defaults import (
    BASS_PRESERVING_RISK_THRESHOLD,
    HARMONIC_TAIL_COMPATIBILITY_THRESHOLD,
    LOW_GRID_BOUNDARY_THRESHOLD,
    LOW_GRID_MAXIMUM_CROSSFADE_MS,
    PERCUSSION_PRIORITY_THRESHOLD,
)


@dataclass(frozen=True)
class SplicePlan:
    """Signal-processing parameters chosen for one loop boundary."""

    mode: str
    crossfade_ms: float
    tail_ms: float


def choose_splice_mode(candidate: SectionCandidate) -> str:
    if (
        candidate.rhythmic_strength >= PERCUSSION_PRIORITY_THRESHOLD
        and candidate.vocal_boundary_risk < 0.25
        and candidate.bass_reset_risk < BASS_PRESERVING_RISK_THRESHOLD
    ):
        return "percussion-priority"
    if candidate.bass_reset_risk >= BASS_PRESERVING_RISK_THRESHOLD:
        return "bass-preserving"
    if (
        candidate.timbre_compatibility < HARMONIC_TAIL_COMPATIBILITY_THRESHOLD
        or candidate.tail_release_compatibility < HARMONIC_TAIL_COMPATIBILITY_THRESHOLD
    ):
        return "harmonic-tail"
    if candidate.loop_quality >= 80.0:
        return "zero-crossing"
    return "adaptive"


def crossfade_duration_ms(candidate: SectionCandidate, minimum_ms: float) -> float:
    effective_quality = min(
        candidate.loop_quality,
        100.0 * candidate.timbre_compatibility,
        100.0 * candidate.bass_compatibility,
    )
    fade_ms = 10.0 + 20.0 * float(np.clip((80.0 - effective_quality) / 50.0, 0, 1))
    maximum_ms = 30.0
    if (
        candidate.boundary_grid_confidence < LOW_GRID_BOUNDARY_THRESHOLD
        and candidate.rhythmic_strength < PERCUSSION_PRIORITY_THRESHOLD
    ):
        # Loose/acoustic openings need enough overlap to carry sustained notes
        # and room tone across an imperfect inferred downbeat.  Keep this away
        # from drum-forward material, where a long fade would soften attacks.
        uncertainty = 1.0 - candidate.boundary_grid_confidence
        fade_ms = max(fade_ms, 30.0 + 70.0 * uncertainty)
        maximum_ms = LOW_GRID_MAXIMUM_CROSSFADE_MS
    if candidate.splice_mode == "percussion-priority":
        fade_ms = min(fade_ms, 14.0)
    elif candidate.splice_mode == "bass-preserving":
        fade_ms = max(fade_ms, 22.0)
    elif candidate.splice_mode == "harmonic-tail":
        fade_ms = max(fade_ms, 18.0)
    elif candidate.splice_mode == "zero-crossing":
        fade_ms = 10.0
    return max(minimum_ms, min(maximum_ms, fade_ms))


def tail_duration_ms(candidate: SectionCandidate) -> float:
    mismatch = 1.0 - float(np.clip(candidate.timbre_compatibility, 0.0, 1.0))
    duration_ms = 250.0 + 500.0 * mismatch
    if candidate.splice_mode == "percussion-priority":
        duration_ms = min(duration_ms, 300.0)
    elif candidate.splice_mode == "bass-preserving":
        duration_ms = max(duration_ms, 650.0)
    elif candidate.splice_mode == "harmonic-tail":
        duration_ms = max(duration_ms, 750.0)
    elif candidate.splice_mode == "zero-crossing":
        duration_ms = min(duration_ms, 350.0)
    if candidate.boundary_grid_confidence < LOW_GRID_BOUNDARY_THRESHOLD:
        duration_ms = max(
            duration_ms,
            750.0
            + 750.0 * (LOW_GRID_BOUNDARY_THRESHOLD - candidate.boundary_grid_confidence) / LOW_GRID_BOUNDARY_THRESHOLD,
        )
    return duration_ms


def build_splice_plan(candidate: SectionCandidate, minimum_ms: float) -> SplicePlan:
    mode = choose_splice_mode(candidate)
    planned = candidate if candidate.splice_mode == mode else replace(candidate, splice_mode=mode)
    return SplicePlan(
        mode=mode,
        crossfade_ms=crossfade_duration_ms(planned, minimum_ms),
        tail_ms=tail_duration_ms(planned),
    )
