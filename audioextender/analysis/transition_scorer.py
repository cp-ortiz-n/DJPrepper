"""Fast, cache-backed preflight scoring for manual arrangement insertions."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from audioextender.analysis.key_detection import TrackAnalysis


@dataclass(frozen=True)
class TransitionAssessment:
    score: int
    verdict: str
    grid: int
    harmony: int
    energy: int
    bass: int
    rhythm: int
    vocals: int | None
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _window_mask(times: np.ndarray, center: float, radius: float = 0.45) -> np.ndarray:
    return (times >= max(0.0, center - radius)) & (times <= center + radius)


def _mean(values: np.ndarray, mask: np.ndarray) -> float:
    return float(np.mean(values[mask])) if np.any(mask) else 0.0


def _similarity(left: float, right: float, scale: float = 1.0) -> float:
    floor = 0.035
    return float(np.exp(-scale * abs(np.log((left + floor) / (right + floor)))))


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator < 1e-8:
        return 0.55
    return float(np.clip(np.dot(left, right) / denominator, 0.0, 1.0))


def _chroma_at(analysis: TrackAnalysis, time: float) -> np.ndarray:
    mask = _window_mask(analysis.frame_times, time, 0.55)
    if not np.any(mask):
        return np.zeros(12)
    return np.mean(analysis.chroma[:, mask], axis=1)


def _grid_fit(analysis: TrackAnalysis, time: float) -> float:
    boundaries = analysis.bar_boundaries
    if not len(boundaries):
        return analysis.beat_grid_confidence / 100.0
    beat = 60.0 / max(analysis.bpm, 1.0)
    distance = float(np.min(np.abs(boundaries - time)))
    return float(np.clip(1.0 - distance / max(beat * 0.55, 0.12), 0.0, 1.0))


def _slope(analysis: TrackAnalysis, end: float, seconds: float = 3.0) -> float:
    mask = (analysis.frame_times >= max(0.0, end - seconds)) & (
        analysis.frame_times <= end
    )
    values = analysis.rms[mask]
    if len(values) < 3:
        return 0.0
    return float(
        np.polyfit(np.linspace(0.0, 1.0, len(values)), values, 1)[0]
        / max(float(np.mean(values)), 0.08)
    )


def assess_custom_insertion(
    analysis: TrackAnalysis,
    source_start: float,
    source_end: float,
    destination: float,
    copies: int,
    vocal_energy: np.ndarray | None = None,
) -> TransitionAssessment:
    """Score entry, repeats, and exit against the surrounding song context."""
    if source_end <= source_start or copies < 1:
        raise ValueError("Invalid custom insertion bounds")
    duration = float(analysis.frame_times[-1]) if len(analysis.frame_times) else 0.0
    if min(source_start, destination) < 0 or source_end > duration or destination > duration:
        raise ValueError("Custom insertion falls outside the analyzed track")

    times = (source_start, source_end, destination)
    masks = tuple(_window_mask(analysis.frame_times, time) for time in times)
    start_mask, end_mask, destination_mask = masks
    grid = np.mean([_grid_fit(analysis, time) for time in times])

    source_start_chroma = _chroma_at(analysis, source_start)
    source_end_chroma = _chroma_at(analysis, source_end)
    destination_chroma = _chroma_at(analysis, destination)
    harmonic_seams = [
        _cosine(destination_chroma, source_start_chroma),
        _cosine(source_end_chroma, destination_chroma),
    ]
    if copies > 1:
        harmonic_seams.append(_cosine(source_end_chroma, source_start_chroma))
    harmony = float(np.mean(harmonic_seams))

    def seam_score(values: np.ndarray) -> float:
        start_value = _mean(values, start_mask)
        end_value = _mean(values, end_mask)
        destination_value = _mean(values, destination_mask)
        seams = [
            _similarity(destination_value, start_value),
            _similarity(end_value, destination_value),
        ]
        if copies > 1:
            seams.append(_similarity(end_value, start_value))
        return float(np.mean(seams))

    energy = seam_score(analysis.rms)
    bass = seam_score(analysis.bass_rms)
    rhythm = float(np.mean([
        seam_score(analysis.percussion_rms),
        seam_score(analysis.onset),
    ]))

    vocal_score: float | None = None
    if vocal_energy is not None and len(vocal_energy) == len(analysis.frame_times):
        boundary_activity = np.mean([
            _mean(vocal_energy, start_mask),
            _mean(vocal_energy, end_mask),
            _mean(vocal_energy, destination_mask),
        ])
        vocal_score = float(np.clip(1.0 - boundary_activity / 0.55, 0.0, 1.0))

    buildup = max(0.0, _slope(analysis, source_end))
    structure = float(np.clip(1.0 - buildup * (0.60 if copies > 1 else 0.35), 0.0, 1.0))
    weighted = (
        0.20 * grid + 0.23 * harmony + 0.18 * energy + 0.13 * bass
        + 0.13 * rhythm + 0.08 * (vocal_score if vocal_score is not None else 0.72)
        + 0.05 * structure
    )
    score = int(round(100.0 * np.clip(weighted, 0.0, 1.0)))

    warnings: list[str] = []
    if grid < 0.68:
        warnings.append("source or destination is not close to a detected bar boundary")
    if harmony < 0.64:
        warnings.append("chord color changes noticeably at a splice")
    if energy < 0.64:
        warnings.append("energy changes abruptly around the insertion")
    if bass < 0.58:
        warnings.append("bass may disappear or reset at a boundary")
    if rhythm < 0.60:
        warnings.append("drum or onset pattern may feel discontinuous")
    if vocal_score is not None and vocal_score < 0.62:
        warnings.append("a vocal phrase may cross the selected boundary")
    if buildup > 0.24 and copies > 1:
        warnings.append("the selected phrase is building and may reset on repetition")

    # A score labeled "strong" must not contradict a concrete musical warning.
    if warnings:
        score = min(score, 74)
    if harmony < 0.50 or (energy < 0.50 and bass < 0.40):
        score = min(score, 59)
    verdict = "Strong placement" if score >= 75 else "Needs a listen" if score >= 60 else "Risky placement"
    return TransitionAssessment(
        score, verdict, round(grid * 100), round(harmony * 100),
        round(energy * 100), round(bass * 100), round(rhythm * 100),
        round(vocal_score * 100) if vocal_score is not None else None,
        tuple(warnings),
    )
