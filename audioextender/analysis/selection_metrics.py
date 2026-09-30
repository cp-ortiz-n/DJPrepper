"""Reusable numerical and musical-boundary metrics for selection."""

from __future__ import annotations

import numpy as np


def _coefficient_of_variation(values: np.ndarray) -> float:
    mean = float(np.mean(values)) if values.size else 0.0
    return float(np.std(values) / mean) if mean > 1e-6 else 2.0


def _chord_identity(chroma: np.ndarray) -> tuple[int, str, float]:
    """Return the strongest major/minor triad and its normalized confidence."""
    vector = np.maximum(np.asarray(chroma, dtype=float), 0.0)
    vector /= max(float(np.linalg.norm(vector)), 1e-8)
    options: list[tuple[float, int, str]] = []
    for root in range(12):
        for mode, intervals in (("major", (0, 4, 7)), ("minor", (0, 3, 7))):
            template = np.zeros(12)
            template[[(root + interval) % 12 for interval in intervals]] = 1.0
            template /= np.linalg.norm(template)
            options.append((float(vector @ template), root, mode))
    options.sort(reverse=True)
    best = options[0]
    confidence = np.clip((best[0] - options[1][0]) / 0.18, 0.0, 1.0)
    return best[1], best[2], float(confidence)


def _chord_transition_score(
    source: np.ndarray, target: np.ndarray, key_root: int
) -> float:
    """Score a loop chord transition, rewarding shared tones and V→I motion."""
    similarity = _cosine_similarity(source, target)
    source_root, _source_mode, source_conf = _chord_identity(source)
    target_root, _target_mode, target_conf = _chord_identity(target)
    cadence = 1.0 if (
        source_root == (key_root + 7) % 12 and target_root == key_root
    ) else 0.0
    fourth_motion = 1.0 if target_root == (source_root + 5) % 12 else 0.0
    tonal_confidence = min(source_conf, target_conf)
    return float(np.clip(
        0.72 * similarity
        + tonal_confidence * (0.20 * cadence + 0.08 * fourth_motion),
        0.0,
        1.0,
    ))


def _normalized_slope(values: np.ndarray) -> float:
    """Return signed total linear change relative to the sequence mean."""
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    slope = float(np.polyfit(x, values, 1)[0])
    return float(slope * (len(values) - 1) / max(float(np.mean(values)), 0.08))


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator < 1e-8:
        return 0.5
    return float(np.clip(np.dot(left, right) / denominator, 0.0, 1.0))


def _means_by_bar(
    values: np.ndarray, frame_times: np.ndarray, boundaries: np.ndarray
) -> np.ndarray:
    """Reduce fast drum-level movement to musically meaningful bar averages."""
    means = []
    for start, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        mask = (frame_times >= start) & (frame_times < end)
        if np.any(mask):
            means.append(float(np.mean(values[mask])))
    return np.asarray(means)


def _vocal_phrase_metrics(
    vocal_energy: np.ndarray,
    frame_times: np.ndarray,
    start: float,
    end: float,
    beat_duration: float,
) -> tuple[float, float, float]:
    """Measure sustained vocals, edge crossings, and pickups at a loop seam."""
    frame_seconds = max(float(np.median(np.diff(frame_times))), 1e-3)
    smooth_frames = max(1, round(0.35 / frame_seconds))
    smooth = np.convolve(
        np.clip(vocal_energy, 0.0, 1.5),
        np.ones(smooth_frames) / smooth_frames,
        mode="same",
    )
    threshold = float(np.clip(np.percentile(smooth, 60) * 1.35, 0.16, 0.45))
    active = smooth >= threshold
    region = (frame_times >= start) & (frame_times < end)
    coverage = float(np.mean(active[region])) if np.any(region) else 0.0

    edge_seconds = max(0.30, min(beat_duration * 0.75, 1.0))
    start_edge = (frame_times >= start - edge_seconds) & (
        frame_times < start + edge_seconds
    )
    end_edge = (frame_times >= end - edge_seconds) & (
        frame_times < end + edge_seconds
    )
    start_risk = float(np.mean(active[start_edge])) if np.any(start_edge) else 0.0
    end_risk = float(np.mean(active[end_edge])) if np.any(end_edge) else 0.0
    boundary_risk = max(start_risk, end_risk)

    ending = (frame_times >= end - 2.0 * beat_duration) & (frame_times < end)
    before_ending = (frame_times >= end - 4.0 * beat_duration) & (
        frame_times < end - 2.0 * beat_duration
    )
    ending_level = float(np.mean(smooth[ending])) if np.any(ending) else 0.0
    previous_level = float(np.mean(smooth[before_ending])) if np.any(before_ending) else 0.0
    pickup = float(
        np.clip((ending_level - previous_level) / max(threshold, 1e-6), 0.0, 1.0)
    )
    phrase_penalty = float(np.clip(0.65 * coverage + 0.35 * pickup, 0.0, 1.0))
    return coverage, boundary_risk, phrase_penalty
