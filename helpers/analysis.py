"""Beat, bar, phrase-grid, and frame-feature analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import gcd

import librosa
import numpy as np
from scipy.signal import resample_poly

from helpers.audio_loader import AudioData
from helpers.config import EditConfig


ANALYSIS_SAMPLE_RATE = 22_050


@dataclass
class TrackAnalysis:
    bpm: float
    tempo_drift_percent: float
    beat_grid_confidence: float
    key_label: str
    key_confidence: float
    key_root: int
    key_mode: str
    groove_label: str
    swing_ratio: float
    timing_label: str
    downbeat_continuity: float
    bar_grid_confidence: np.ndarray
    bar_section_labels: np.ndarray
    bar_section_confidence: np.ndarray
    beat_times: np.ndarray
    downbeat_indices: np.ndarray
    bar_boundaries: np.ndarray
    frame_times: np.ndarray
    rms: np.ndarray
    onset: np.ndarray
    percussion_rms: np.ndarray
    harmonic_rms: np.ndarray
    bass_rms: np.ndarray
    spectral_centroid: np.ndarray
    spectral_flux: np.ndarray
    chroma: np.ndarray
    spectral_profile: np.ndarray
    key_candidates: tuple[dict[str, float | str], ...] = ()


@dataclass(frozen=True)
class KeyAnalysis:
    """The independently computed tonal result for one audio file."""

    key_label: str
    confidence: float
    candidates: tuple[dict[str, float | str], ...]


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.nan_to_num(np.asarray(values, dtype=float))
    high = np.percentile(values, 95) if values.size else 0.0
    return np.clip(values / high, 0.0, 1.5) if high > 1e-10 else np.zeros_like(values)


def _infer_downbeat_offset(onset: np.ndarray, beat_frames: np.ndarray) -> tuple[int, float]:
    """Choose the phase with strong, recurring four-beat accent patterns."""
    if len(beat_frames) < 8:
        return 0, 0.0
    accents = onset[np.clip(beat_frames, 0, len(onset) - 1)]
    scores = []
    for offset in range(4):
        usable = accents[offset:]
        usable = usable[:len(usable) // 4 * 4]
        if not len(usable):
            scores.append(0.0)
            continue
        bars = usable.reshape(-1, 4)
        downbeat_strength = float(np.mean(bars[:, 0]))
        other_strength = float(np.mean(bars[:, 1:]))
        contrast = max(0.0, downbeat_strength - other_strength)
        patterns = bars / np.maximum(np.linalg.norm(bars, axis=1, keepdims=True), 1e-8)
        template = np.median(patterns, axis=0)
        recurrence = float(np.mean(patterns @ template / max(np.linalg.norm(template), 1e-8)))
        scores.append(0.60 * downbeat_strength + 0.25 * contrast + 0.15 * recurrence)
    ordered = sorted(scores, reverse=True)
    accent_confidence = (ordered[0] - ordered[1]) / max(ordered[0], 1e-8)
    return int(np.argmax(scores)), float(np.clip(accent_confidence, 0.0, 1.0))


def _beat_grid_confidence(
    beat_times: np.ndarray,
    beat_frames: np.ndarray,
    onset: np.ndarray,
    downbeat_confidence: float,
) -> float:
    """Return a 0–100 confidence estimate for the inferred rhythmic grid."""
    intervals = np.diff(beat_times)
    if len(intervals) < 7:
        return 0.0
    interval_mean = max(float(np.mean(intervals)), 1e-8)
    interval_cv = float(np.std(intervals) / interval_mean)
    timing_consistency = float(np.exp(-10.0 * interval_cv))

    normalized_onset = _normalize(onset)
    beat_strength = normalized_onset[np.clip(beat_frames, 0, len(normalized_onset) - 1)]
    onset_support = float(np.clip(np.mean(beat_strength), 0.0, 1.0))
    confidence = 100.0 * (
        0.65 * timing_consistency + 0.25 * onset_support + 0.10 * downbeat_confidence
    )
    return float(np.clip(confidence, 0.0, 100.0))


def _estimate_key(chroma: np.ndarray) -> tuple[str, float, int, str]:
    """Estimate a global major/minor key with Krumhansl-style profiles."""
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    major = np.asarray([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.asarray([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    tonal = np.mean(np.maximum(chroma, 0.0), axis=1)
    tonal /= max(float(np.linalg.norm(tonal)), 1e-8)
    scored: list[tuple[float, int, str]] = []
    for root in range(12):
        for mode, profile in (("major", major), ("minor", minor)):
            rotated = np.roll(profile, root)
            score = float(tonal @ (rotated / np.linalg.norm(rotated)))
            scored.append((score, root, mode))
    scored.sort(reverse=True)
    best, second = scored[0], scored[1]
    separation = max(0.0, best[0] - second[0])
    confidence = 100.0 * np.clip(0.65 * best[0] + 0.35 * separation / 0.08, 0.0, 1.0)
    label = f"{names[best[1]]} {best[2]}"
    return label, float(confidence), best[1], best[2]


def _ensemble_key_estimate(
    primary_chroma: np.ndarray,
    harmonic_chroma: np.ndarray,
    cqt_chroma: np.ndarray | None = None,
) -> tuple[str, float, int, str, tuple[dict[str, float | str], ...]]:
    """Keep the proven estimate unless two independent detectors agree otherwise."""
    primary = _estimate_key(primary_chroma)
    harmonic = _estimate_key(harmonic_chroma)
    cqt = _estimate_key(cqt_chroma) if cqt_chroma is not None else None
    selected = primary
    reason = "primary"
    if harmonic[0] != primary[0] and cqt is not None and harmonic[0] == cqt[0]:
        selected = harmonic
        reason = "harmonic+CQT consensus"

    available = tuple(result for result in (primary, harmonic, cqt) if result is not None)
    supporters = tuple(result for result in available if result[0] == selected[0])
    confidence = float(np.mean([result[1] for result in supporters]))
    distinct = len({result[0] for result in available})
    if len(supporters) == 1 and distinct > 1:
        confidence *= 0.88
    elif len(supporters) == 2 and distinct > 1:
        confidence *= 0.95

    named_results = tuple(
        (name, result) for name, result in (
            ("primary", primary), ("harmonic", harmonic), ("CQT", cqt)
        ) if result is not None
    )
    by_label: dict[str, float] = {}
    for _name, result in named_results:
        by_label[result[0]] = max(by_label.get(result[0], 0.0), result[1])
    ordered = [selected[0]] + [
        label for label, _score in sorted(
            by_label.items(), key=lambda item: item[1], reverse=True
        ) if label != selected[0]
    ]
    candidates = tuple(
        {
            "key": label,
            "confidence": float(confidence if label == selected[0] else by_label[label]),
            "selected": 1.0 if label == selected[0] else 0.0,
            "reason": reason if label == selected[0] else "alternate detector",
            "detectors": ", ".join(
                name for name, result in named_results if result[0] == label
            ),
        }
        for label in ordered[:3]
    )
    return selected[0], float(np.clip(confidence, 0.0, 100.0)), selected[2], selected[3], candidates


def analyze_key(audio: AudioData, hop_length: int = 512) -> KeyAnalysis:
    """Analyze only musical key, leaving every other saved track metric untouched."""
    mono = librosa.to_mono(audio.samples.T)
    sample_rate = audio.sample_rate
    if sample_rate > ANALYSIS_SAMPLE_RATE:
        divisor = gcd(sample_rate, ANALYSIS_SAMPLE_RATE)
        mono = resample_poly(
            mono, ANALYSIS_SAMPLE_RATE // divisor, sample_rate // divisor
        ).astype(np.float32, copy=False)
        sample_rate = ANALYSIS_SAMPLE_RATE
    magnitude = np.abs(librosa.stft(mono, hop_length=hop_length))
    harmonic_spectrum, _ = librosa.decompose.hpss(magnitude)
    primary_chroma = librosa.feature.chroma_stft(
        S=magnitude ** 2, sr=sample_rate
    )
    harmonic_chroma = librosa.feature.chroma_stft(
        S=harmonic_spectrum ** 2, sr=sample_rate
    )
    primary = _estimate_key(primary_chroma)
    harmonic = _estimate_key(harmonic_chroma)
    cqt_chroma = None
    if primary[0] != harmonic[0]:
        cqt_chroma = librosa.feature.chroma_cqt(
            y=mono, sr=sample_rate, hop_length=hop_length
        )
    label, confidence, _root, _mode, candidates = _ensemble_key_estimate(
        primary_chroma, harmonic_chroma, cqt_chroma
    )
    return KeyAnalysis(label, confidence, candidates)


def _classify_bar_sections(
    boundaries: np.ndarray,
    frame_times: np.ndarray,
    rms: np.ndarray,
    percussion: np.ndarray,
    harmonic: np.ndarray,
    onset: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Assign conservative arrangement labels from energy and track position."""
    count = max(0, len(boundaries) - 1)
    if count == 0:
        return np.asarray([], dtype="U16"), np.asarray([], dtype=float)
    features = np.zeros((count, 4), dtype=float)
    for index in range(count):
        mask = (frame_times >= boundaries[index]) & (frame_times < boundaries[index + 1])
        if np.any(mask):
            features[index] = (
                np.mean(rms[mask]), np.mean(percussion[mask]),
                np.mean(harmonic[mask]), np.mean(onset[mask]),
            )
    energy, drums, harmony, activity = features.T
    energy_high = float(np.percentile(energy, 72))
    energy_low = float(np.percentile(energy, 28))
    drum_high = float(np.percentile(drums, 68))
    drum_low = float(np.percentile(drums, 28))
    labels: list[str] = []
    confidence: list[float] = []
    for index in range(count):
        position = (index + 0.5) / count
        recent = energy[max(0, index - 3):index + 1]
        slope = float(np.polyfit(np.arange(len(recent)), recent, 1)[0]) if len(recent) > 1 else 0.0
        relative_slope = slope / max(float(np.mean(recent)), 0.08)
        previous_rising = index > 0 and any(
            labels[j] == "buildup" for j in range(max(0, index - 2), index)
        )
        if position >= 0.84 and relative_slope < -0.06:
            label, certainty = "fade", 0.72
        elif position >= 0.78 and energy[index] < energy_high:
            label, certainty = "closing", 0.70
        elif position <= 0.15:
            label, certainty = "intro", 0.72
        elif relative_slope > 0.10 and activity[index] >= np.median(activity):
            label, certainty = "buildup", 0.68
        elif previous_rising and energy[index] >= energy_high and drums[index] >= drum_high:
            label, certainty = "drop", 0.75
        elif drums[index] <= drum_low and energy[index] <= energy_low:
            label, certainty = "breakdown", 0.70
        elif energy[index] >= energy_high and drums[index] >= drum_high:
            label, certainty = "chorus", 0.66
        else:
            label, certainty = "verse", 0.55
        # Ambiguous bars near thresholds should influence ranking only gently.
        margin = abs(energy[index] - np.median(energy)) + abs(drums[index] - np.median(drums))
        labels.append(label)
        confidence.append(float(np.clip(certainty + 0.15 * margin, 0.45, 0.90)))
    return np.asarray(labels, dtype="U16"), np.asarray(confidence, dtype=float)


def _analyze_groove(
    beat_times: np.ndarray,
    boundaries: np.ndarray,
    frame_times: np.ndarray,
    onset: np.ndarray,
    tempo_drift_percent: float,
) -> tuple[str, float, str, float, np.ndarray]:
    """Describe subdivisions and confidence in each non-rigid local bar."""
    subdivision_ratios: list[float] = []
    for left, right in zip(beat_times[:-1], beat_times[1:], strict=True):
        period = right - left
        mask = (frame_times >= left + 0.34 * period) & (
            frame_times <= left + 0.80 * period
        )
        if not np.any(mask):
            continue
        local_times = frame_times[mask]
        local_onset = onset[mask]
        peak = int(np.argmax(local_onset))
        if local_onset[peak] >= 0.22:
            subdivision_ratios.append(float((local_times[peak] - left) / period))
    if len(subdivision_ratios) >= 8:
        ratio = float(np.median(subdivision_ratios))
        spread = float(np.percentile(subdivision_ratios, 75) - np.percentile(subdivision_ratios, 25))
        if spread > 0.15:
            groove = "loose/syncopated"
        elif 0.58 <= ratio <= 0.70:
            groove = "swing"
        elif 0.44 <= ratio <= 0.57:
            groove = "straight"
        else:
            groove = "syncopated"
    else:
        ratio, groove = 0.5, "undetermined"

    bar_confidence: list[float] = []
    bar_patterns: list[np.ndarray] = []
    for start, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        beat_period = (end - start) / 4.0
        if beat_period <= 0:
            bar_confidence.append(0.0)
            continue
        timing_support: list[float] = []
        onset_support: list[float] = []
        for beat in range(4):
            target = start + beat * beat_period
            nearest = float(np.min(np.abs(beat_times - target))) if len(beat_times) else beat_period
            timing_support.append(float(np.exp(-nearest / max(0.18 * beat_period, 1e-4))))
            window = np.abs(frame_times - target) <= 0.12 * beat_period
            onset_support.append(float(np.max(onset[window])) if np.any(window) else 0.0)
        bar_patterns.append(np.asarray(onset_support, dtype=float))
        interval_mask = (beat_times >= start) & (beat_times <= end)
        local_intervals = np.diff(beat_times[interval_mask])
        if len(local_intervals) >= 2:
            regularity = float(np.exp(-6.0 * np.std(local_intervals) / max(np.mean(local_intervals), 1e-6)))
        else:
            regularity = 0.35
        bar_confidence.append(float(np.clip(
            0.45 * np.mean(timing_support)
            + 0.35 * np.clip(np.mean(onset_support), 0.0, 1.0)
            + 0.20 * regularity,
            0.0,
            1.0,
        )))
    if bar_patterns:
        patterns = np.vstack(bar_patterns)
        normalized = patterns / np.maximum(
            np.linalg.norm(patterns, axis=1, keepdims=True), 1e-8
        )
        template = np.median(normalized, axis=0)
        template /= max(float(np.linalg.norm(template)), 1e-8)
        recurrence = np.clip(normalized @ template, 0.0, 1.0)
        # Recurring four-beat accent shape is the evidence that the inferred
        # first beat remains the same musical phase across successive bars.
        bar_confidence = [
            0.75 * confidence + 0.25 * float(recurrence[index])
            for index, confidence in enumerate(bar_confidence)
        ]
    confidence_array = np.asarray(bar_confidence, dtype=float)
    continuity = 100.0 * float(np.mean(confidence_array)) if len(confidence_array) else 0.0
    if continuity < 45.0:
        timing = "uncertain grid"
    elif tempo_drift_percent < 3.0:
        timing = "steady"
    elif tempo_drift_percent < 8.0:
        timing = "mildly variable"
    else:
        timing = "variable/live"
    return groove, ratio, timing, continuity, confidence_array


def analyze_track(
    audio: AudioData,
    config: EditConfig,
    progress: Callable[[float, str], None] | None = None,
) -> TrackAnalysis:
    """Analyze a track and optionally report progress from zero to one."""
    report = progress or (lambda _fraction, _label: None)
    # Analysis is mono only; the untouched stereo samples are used for editing.
    report(0.02, "Preparing analysis audio")
    mono = librosa.to_mono(audio.samples.T)
    sample_rate = audio.sample_rate
    if sample_rate > ANALYSIS_SAMPLE_RATE:
        report(0.05, "Preparing efficient analysis signal")
        divisor = gcd(sample_rate, ANALYSIS_SAMPLE_RATE)
        mono = resample_poly(
            mono,
            ANALYSIS_SAMPLE_RATE // divisor,
            sample_rate // divisor,
        ).astype(np.float32, copy=False)
        sample_rate = ANALYSIS_SAMPLE_RATE
    hop = config.analysis_hop_length
    report(0.10, "Separating percussion")
    magnitude = np.abs(librosa.stft(mono, hop_length=hop))
    harmonic_spectrum, percussive_spectrum = librosa.decompose.hpss(magnitude)
    report(0.36, "Measuring onset activity")
    percussion_db = librosa.amplitude_to_db(
        percussive_spectrum, ref=np.max
    )
    onset = librosa.onset.onset_strength(
        S=percussion_db, sr=sample_rate, hop_length=hop
    )
    report(0.45, "Detecting beats and BPM")
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset, sr=sample_rate, hop_length=hop, units="frames"
    )
    bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 0.0
    beat_frames = np.asarray(beat_frames, dtype=int)
    beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate, hop_length=hop)
    if len(beat_times) < 8 or bpm <= 0:
        raise RuntimeError("Could not find a reliable beat grid (fewer than 8 beats detected)")
    intervals = np.diff(beat_times)
    instantaneous_bpm = 60.0 / np.maximum(intervals, 1e-6)
    tempo_drift_percent = float(
        100.0
        * (np.percentile(instantaneous_bpm, 90) - np.percentile(instantaneous_bpm, 10))
        / max(float(np.median(instantaneous_bpm)), 1e-6)
    )

    report(0.57, "Building the 4/4 bar grid")
    offset, downbeat_confidence = _infer_downbeat_offset(onset, beat_frames)
    grid_confidence = _beat_grid_confidence(
        beat_times, beat_frames, onset, downbeat_confidence
    )
    downbeat_indices = np.arange(offset, len(beat_times), config.beats_per_bar, dtype=int)
    bar_boundaries = beat_times[downbeat_indices]
    # Beat trackers often acquire confidence only after a sparse or atmospheric
    # opening. Project the established bar period backwards so a protected
    # pre-vocal opening can still supply properly sized musical loops.
    if len(bar_boundaries):
        opening_period = float(np.median(intervals[:min(12, len(intervals))]))
        bar_period = config.beats_per_bar * opening_period
        earlier: list[float] = []
        projected = float(bar_boundaries[0]) - bar_period
        while projected >= 0.0:
            earlier.append(projected)
            projected -= bar_period
        if earlier:
            bar_boundaries = np.concatenate((np.asarray(earlier[::-1]), bar_boundaries))
    # Include the projected end of the final complete bar for slicing candidates.
    if len(bar_boundaries):
        beat_period = float(np.median(intervals[-min(12, len(intervals)):]))
        projected = bar_boundaries[-1] + config.beats_per_bar * beat_period
        if projected <= audio.duration + beat_period:
            bar_boundaries = np.append(bar_boundaries, min(projected, audio.duration))

    report(0.64, "Measuring loudness")
    rms = librosa.feature.rms(S=magnitude)[0]
    report(0.70, "Measuring drum strength")
    percussion_rms = librosa.feature.rms(S=percussive_spectrum)[0]
    harmonic_rms = librosa.feature.rms(S=harmonic_spectrum)[0]
    report(0.77, "Measuring spectral stability")
    centroid = librosa.feature.spectral_centroid(
        S=magnitude, sr=sample_rate
    )[0]
    report(0.86, "Finding transitions and fills")
    flux = np.concatenate(([0.0], np.mean(np.maximum(np.diff(magnitude, axis=1), 0), axis=0)))
    frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=(magnitude.shape[0] - 1) * 2)
    bass_bins = (frequencies >= 35.0) & (frequencies <= 220.0)
    bass_rms = np.sqrt(np.mean(magnitude[bass_bins] ** 2, axis=0))
    report(0.93, "Comparing harmonic content")
    chroma = librosa.feature.chroma_stft(S=magnitude ** 2, sr=sample_rate)
    harmonic_chroma = librosa.feature.chroma_stft(
        S=harmonic_spectrum ** 2, sr=sample_rate
    )
    primary_key = _estimate_key(chroma)
    harmonic_key = _estimate_key(harmonic_chroma)
    cqt_chroma = None
    if primary_key[0] != harmonic_key[0]:
        cqt_chroma = librosa.feature.chroma_cqt(
            y=mono, sr=sample_rate, hop_length=hop
        )
    key_label, key_confidence, key_root, key_mode, key_candidates = (
        _ensemble_key_estimate(chroma, harmonic_chroma, cqt_chroma)
    )
    mel_energy = librosa.feature.melspectrogram(
        S=magnitude ** 2,
        sr=sample_rate,
        n_mels=32,
        fmin=30.0,
        fmax=min(16000.0, sample_rate / 2.0),
    )
    spectral_profile = librosa.power_to_db(mel_energy, ref=np.max)
    spectral_profile = np.clip((spectral_profile + 80.0) / 80.0, 0.0, 1.0)
    feature_length = min(
        len(rms), len(onset), len(percussion_rms), len(harmonic_rms), len(bass_rms),
        len(centroid), len(flux), chroma.shape[1], spectral_profile.shape[1],
    )
    frame_times = librosa.frames_to_time(np.arange(feature_length), sr=sample_rate, hop_length=hop)
    normalized_rms = _normalize(rms[:feature_length])
    normalized_onset = _normalize(onset[:feature_length])
    normalized_percussion = _normalize(percussion_rms[:feature_length])
    normalized_harmonic = _normalize(harmonic_rms[:feature_length])
    (
        groove_label,
        swing_ratio,
        timing_label,
        downbeat_continuity,
        bar_grid_confidence,
    ) = _analyze_groove(
        beat_times, bar_boundaries, frame_times, normalized_onset,
        tempo_drift_percent,
    )
    bar_section_labels, bar_section_confidence = _classify_bar_sections(
        bar_boundaries, frame_times, normalized_rms, normalized_percussion,
        normalized_harmonic, normalized_onset,
    )

    result = TrackAnalysis(
        bpm=bpm,
        tempo_drift_percent=tempo_drift_percent,
        beat_grid_confidence=grid_confidence,
        key_label=key_label,
        key_confidence=key_confidence,
        key_root=key_root,
        key_mode=key_mode,
        groove_label=groove_label,
        swing_ratio=swing_ratio,
        timing_label=timing_label,
        downbeat_continuity=downbeat_continuity,
        bar_grid_confidence=bar_grid_confidence,
        bar_section_labels=bar_section_labels,
        bar_section_confidence=bar_section_confidence,
        beat_times=beat_times,
        downbeat_indices=downbeat_indices,
        bar_boundaries=bar_boundaries,
        frame_times=frame_times,
        rms=normalized_rms,
        onset=normalized_onset,
        percussion_rms=normalized_percussion,
        harmonic_rms=normalized_harmonic,
        bass_rms=_normalize(bass_rms[:feature_length]),
        spectral_centroid=_normalize(centroid[:feature_length]),
        spectral_flux=_normalize(flux[:feature_length]),
        chroma=np.nan_to_num(chroma[:, :feature_length]),
        spectral_profile=np.nan_to_num(spectral_profile[:, :feature_length]),
        key_candidates=key_candidates,
    )
    report(1.0, "Audio analysis complete")
    return result
