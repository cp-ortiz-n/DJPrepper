"""Domain model for ranked intro and outro sections."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SectionCandidate:
    start: float
    end: float
    score: float
    rhythmic_strength: float
    stability: float
    transition_penalty: float
    vocal_energy: float | None = None
    instrumentalness: float = 0.0
    seam_compatibility: float = 0.0
    harmonic_compatibility: float = 0.0
    fill_penalty: float = 0.0
    pickup_penalty: float = 0.0
    boundary_adjustment_ms: float = 0.0
    bass_compatibility: float = 0.0
    energy_trend_penalty: float = 0.0
    timbre_compatibility: float = 0.0
    boundary_transition_penalty: float = 0.0
    structure_consistency: float = 0.0
    buildup_penalty: float = 0.0
    context_compatibility: float = 0.0
    unit_bars: int = 0
    repetitions: int = 1
    tail_release_compatibility: float = 0.0
    vocal_coverage: float = 0.0
    vocal_boundary_risk: float = 0.0
    vocal_phrase_penalty: float = 0.0
    energy_shape: str = "unknown"
    buildup_risk: float = 0.0
    bass_reset_risk: float = 0.0
    energy_context_match: float = 0.0
    splice_mode: str = "adaptive"
    chord_return_compatibility: float = 0.0
    harmonic_resolution_risk: float = 0.0
    section_label: str = "unknown"
    section_confidence: float = 0.0
    arrangement_fit: float = 0.0
    local_grid_confidence: float = 0.0
    boundary_grid_confidence: float = 0.0

    @property
    def loop_quality(self) -> float:
        """Estimated 0–100 quality of looping end back to start."""
        # Calibrated around qualities listeners actually notice at a loop seam.
        # Stable, compatible phrases normally land in the 70–90 range; fills,
        # pickups, or harmonic discontinuities pull the result down clearly.
        value = 100.0 * (
            0.17 * np.clip(self.seam_compatibility, 0.0, 1.0)
            + 0.10 * np.clip(self.harmonic_compatibility, 0.0, 1.0)
            + 0.05 * np.clip(self.chord_return_compatibility, 0.0, 1.0)
            + 0.15 * np.clip(self.timbre_compatibility, 0.0, 1.0)
            + 0.15 * np.clip(self.bass_compatibility, 0.0, 1.0)
            + 0.10 * np.clip(self.stability, 0.0, 1.0)
            + 0.05 * np.clip(self.rhythmic_strength, 0.0, 1.0)
            + 0.10 * np.clip(self.structure_consistency, 0.0, 1.0)
            + 0.05 * np.clip(self.context_compatibility, 0.0, 1.0)
            + 0.03 * np.clip(self.tail_release_compatibility, 0.0, 1.0)
            + 0.05 * (1.0 - np.clip(self.fill_penalty, 0.0, 1.0))
            + 0.03 * (1.0 - np.clip(self.pickup_penalty, 0.0, 1.0))
            + 0.01 * (1.0 - np.clip(self.energy_trend_penalty, 0.0, 1.0))
            + 0.01 * (1.0 - np.clip(self.boundary_transition_penalty, 0.0, 1.0))
        )
        # Do not let excellent rhythm/stability hide one clearly weak seam
        # dimension. A timbral or bass mismatch is exactly the "build resets"
        # sensation that broad weighted averages previously overrated.
        weakest_seam = min(
            np.clip(self.seam_compatibility, 0.0, 1.0),
            np.clip(self.timbre_compatibility, 0.0, 1.0),
            np.clip(self.bass_compatibility, 0.0, 1.0),
        )
        value *= 0.60 + 0.40 * weakest_seam
        # A technically smooth waveform is not a good DJ loop when it repeats
        # sustained lyrics or cuts a vocal phrase at either edge.
        value *= 1.0 - 0.55 * np.clip(self.vocal_phrase_penalty, 0.0, 1.0)
        value *= 1.0 - 0.45 * np.clip(self.vocal_boundary_risk, 0.0, 1.0)
        value *= 1.0 - 0.35 * np.clip(self.buildup_risk, 0.0, 1.0)
        value *= 1.0 - 0.35 * np.clip(self.bass_reset_risk, 0.0, 1.0)
        value *= 1.0 - 0.40 * np.clip(self.harmonic_resolution_risk, 0.0, 1.0)
        value *= 0.75 + 0.25 * np.clip(self.boundary_grid_confidence, 0.0, 1.0)
        return float(np.clip(value, 0.0, 100.0))

    @property
    def instrumental_loop_quality(self) -> float:
        """Loop quality after removing penalties caused only by vocal content."""
        vocal_factor = (
            (1.0 - 0.55 * np.clip(self.vocal_phrase_penalty, 0.0, 1.0))
            * (1.0 - 0.45 * np.clip(self.vocal_boundary_risk, 0.0, 1.0))
        )
        return float(np.clip(self.loop_quality / max(float(vocal_factor), 0.10), 0.0, 100.0))
