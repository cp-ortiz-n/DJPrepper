"""Shared section-behavior measurements used by reporting and candidate ranking."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from audioextender.analysis.key_detection import TrackAnalysis


@dataclass(frozen=True)
class BehaviorSnapshot:
    style: str
    confidence: float
    reason: str
    features: tuple[float, float, float, float, float]


def broad_section_bounds(analysis: TrackAnalysis) -> list[tuple[str, float, float]]:
    boundaries = analysis.bar_boundaries
    if len(boundaries) < 4:
        end = float(analysis.frame_times[-1]) if len(analysis.frame_times) else 0.0
        third = end / 3.0
        return [("Opening", 0.0, third), ("Main body", third, 2 * third), ("Ending", 2 * third, end)]
    bar_count = len(boundaries) - 1
    edge_bars = min(12, max(4, round(bar_count * 0.18)))
    intro_end = float(boundaries[min(edge_bars, len(boundaries) - 1)])
    outro_start = float(boundaries[max(0, len(boundaries) - edge_bars - 1)])
    end = max(float(boundaries[-1]), float(analysis.frame_times[-1]))
    if intro_end >= outro_start:
        intro_end, outro_start = end / 3.0, 2.0 * end / 3.0
    return [("Opening", 0.0, intro_end), ("Main body", intro_end, outro_start), ("Ending", outro_start, end)]


def classify_interval(
    analysis: TrackAnalysis,
    start: float,
    end: float,
    vocal_energy: np.ndarray | None = None,
) -> BehaviorSnapshot | None:
    mask = (analysis.frame_times >= start) & (analysis.frame_times < end)
    if not np.any(mask):
        return None
    energy = float(np.clip(np.mean(analysis.rms[mask]), 0.0, 1.0))
    percussion = float(np.clip(np.mean(analysis.percussion_rms[mask]), 0.0, 1.0))
    harmonic = float(np.clip(np.mean(analysis.harmonic_rms[mask]), 0.0, 1.0))
    onset = float(np.clip(np.mean(analysis.onset[mask]), 0.0, 1.0))
    vocal = (
        float(np.clip(np.mean(vocal_energy[mask]), 0.0, 1.0))
        if vocal_energy is not None and len(vocal_energy) == len(mask)
        else 0.0
    )
    global_energy = max(float(np.mean(analysis.rms)), 1e-6)
    relative_energy = float(np.clip(energy / global_energy, 0.0, 1.5))
    scores = {
        "sparse/ambient": 0.45 * (1 - percussion) + 0.30 * (1 - onset) + 0.25 * harmonic,
        "melodic/harmonic": 0.55 * harmonic + 0.25 * (1 - percussion) + 0.20 * relative_energy / 1.5,
        "rhythm-forward": 0.50 * percussion + 0.30 * onset + 0.20 * min(relative_energy, 1.0),
        "high-energy": 0.38 * min(relative_energy, 1.0) + 0.34 * percussion + 0.28 * onset,
        "dynamic/transition": 0.45 * abs(relative_energy - 1.0)
        + 0.30 * onset
        + 0.25 * (1 - analysis.beat_grid_confidence / 100.0),
    }
    if vocal_energy is not None:
        scores["vocal-forward"] = 0.70 * vocal + 0.15 * harmonic + 0.15 * energy
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    style, best = ordered[0]
    confidence = float(np.clip(0.55 + 0.85 * (best - ordered[1][1]), 0.55, 0.93))
    reason = f"energy {energy:.2f}, percussion {percussion:.2f}, harmonic {harmonic:.2f}, onset {onset:.2f}"
    if vocal_energy is not None:
        reason += f", vocals {vocal:.2f}"
    return BehaviorSnapshot(style, confidence, reason, (energy, percussion, harmonic, onset, vocal))


def behavior_compatibility(first: BehaviorSnapshot, second: BehaviorSnapshot) -> float:
    distance = float(np.mean(np.abs(np.asarray(first.features) - np.asarray(second.features))))
    feature_match = float(np.exp(-distance / 0.22))
    label_match = 1.0 if first.style == second.style else 0.0
    return float(np.clip(0.82 * feature_match + 0.18 * label_match, 0.0, 1.0))
