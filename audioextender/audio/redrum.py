"""Automatic percussion-only intros for songs whose melody cannot be looped."""

from __future__ import annotations

import librosa
import numpy as np
from scipy.signal import butter, sosfiltfilt

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_selector import SectionCandidate
from audioextender.audio.loading import AudioData
from settings import (
    REDRUM_BASS_CUTOFF_HZ,
    REDRUM_BASS_GAIN,
    REDRUM_DRUM_GAIN,
    REDRUM_KICK_CUTOFF_HZ,
    REDRUM_KICK_GAIN,
    REDRUM_ORIGINAL_FADE_IN_BARS,
)


def select_redrum_candidate(
    analysis: TrackAnalysis,
    extension_bars: int,
    duration: float,
) -> SectionCandidate | None:
    """Find a stable two/four-bar percussion bed near the front of the song."""
    boundaries = analysis.bar_boundaries
    unit_bars = 4 if extension_bars >= 4 else 2
    if len(boundaries) <= unit_bars:
        return None
    best: tuple[float, int, float, float] | None = None
    latest = min(duration * 0.45, 90.0)
    for index in range(0, len(boundaries) - unit_bars, 2):
        start = float(boundaries[index])
        end = float(boundaries[index + unit_bars])
        if end > latest:
            break
        mask = (analysis.frame_times >= start) & (analysis.frame_times < end)
        if np.count_nonzero(mask) < 8:
            continue
        percussion = analysis.percussion_rms[mask]
        flux = analysis.spectral_flux[mask]
        strength = float(np.mean(percussion))
        stability = float(np.exp(-2.0 * np.std(percussion) / max(strength, 0.08)))
        transition = float(np.clip(np.percentile(flux, 90), 0.0, 1.0))
        score = 0.70 * strength + 0.30 * stability - 0.20 * transition
        if best is None or score > best[0]:
            best = (score, index, strength, stability)
    if best is None or best[2] < 0.10:
        return None
    score, index, strength, stability = best
    start = float(boundaries[index])
    end = float(boundaries[index + unit_bars])
    return SectionCandidate(
        start=start,
        end=end,
        score=score,
        rhythmic_strength=strength,
        stability=stability,
        transition_penalty=0.0,
        instrumentalness=1.0,
        seam_compatibility=0.8,
        harmonic_compatibility=1.0,
        bass_compatibility=0.8,
        timbre_compatibility=0.8,
        structure_consistency=stability,
        context_compatibility=0.8,
        tail_release_compatibility=0.8,
        chord_return_compatibility=1.0,
        energy_context_match=0.8,
        boundary_grid_confidence=float(
            np.mean(analysis.bar_grid_confidence[index:index + unit_bars])
        ),
        local_grid_confidence=float(
            np.mean(analysis.bar_grid_confidence[index:index + unit_bars])
        ),
        arrangement_fit=1.0,
        energy_shape="stable",
        section_label="percussion bed",
        section_confidence=0.8,
        unit_bars=unit_bars,
        repetitions=max(1, extension_bars // unit_bars),
        splice_mode="redrum",
    )


def _percussion_phrase(
    audio: AudioData,
    candidate: SectionCandidate,
    drums_audio: AudioData | None = None,
) -> np.ndarray:
    first = max(0, round(candidate.start * audio.sample_rate))
    last = min(len(audio.samples), round(candidate.end * audio.sample_rate))
    if drums_audio is not None and drums_audio.sample_rate == audio.sample_rate:
        return drums_audio.samples[first:last].copy()
    phrase = audio.samples[first:last]
    channels = []
    for channel in range(phrase.shape[1]):
        _harmonic, percussive = librosa.effects.hpss(phrase[:, channel])
        channels.append(percussive)
    return np.column_stack(channels).astype(np.float32, copy=False)


def create_redrum_intro(
    edited_original: AudioData,
    source_audio: AudioData,
    candidate: SectionCandidate,
    drums_audio: AudioData | None = None,
    instrumental_audio: AudioData | None = None,
) -> AudioData:
    """Build a progressive beat intro, then fade in the untouched opening."""
    phrase = _percussion_phrase(source_audio, candidate, drums_audio)
    if not len(phrase):
        return edited_original

    def low_pass(samples: np.ndarray, cutoff_hz: float) -> np.ndarray:
        nyquist = source_audio.sample_rate / 2.0
        cutoff = min(cutoff_hz, nyquist * 0.90)
        if cutoff <= 0 or len(samples) < 32:
            return np.zeros_like(samples)
        sos = butter(4, cutoff / nyquist, btype="lowpass", output="sos")
        return np.asarray(sosfiltfilt(sos, samples, axis=0), dtype=np.float32)

    kick_phrase = low_pass(phrase, REDRUM_KICK_CUTOFF_HZ)
    bass_phrase = np.zeros_like(phrase)
    if (
        instrumental_audio is not None
        and instrumental_audio.sample_rate == source_audio.sample_rate
    ):
        first = max(0, round(candidate.start * source_audio.sample_rate))
        last = min(len(instrumental_audio.samples), first + len(phrase))
        support = instrumental_audio.samples[first:last] - phrase[:last - first]
        bass_phrase[:len(support)] = low_pass(support, REDRUM_BASS_CUTOFF_HZ)

    drums = np.concatenate(
        [phrase.copy() for _ in range(candidate.repetitions)], axis=0
    )
    kicks = np.concatenate(
        [kick_phrase.copy() for _ in range(candidate.repetitions)], axis=0
    )
    bass = np.concatenate(
        [bass_phrase.copy() for _ in range(candidate.repetitions)], axis=0
    )
    pre_roll = np.zeros_like(drums)
    total_bars = max(1, candidate.unit_bars * candidate.repetitions)
    bar_frames = max(1, round(len(pre_roll) / total_bars))
    kick_end = max(1, total_bars // 4)
    drums_end = max(kick_end + 1, total_bars // 2)
    for bar in range(total_bars):
        first = bar * bar_frames
        last = len(pre_roll) if bar == total_bars - 1 else min(
            len(pre_roll), (bar + 1) * bar_frames
        )
        if bar < kick_end:
            pre_roll[first:last] = kicks[first:last] * np.float32(REDRUM_KICK_GAIN)
        elif bar < drums_end:
            pre_roll[first:last] = drums[first:last] * np.float32(REDRUM_DRUM_GAIN)
        else:
            pre_roll[first:last] = (
                drums[first:last] * np.float32(REDRUM_DRUM_GAIN)
                + bass[first:last] * np.float32(REDRUM_BASS_GAIN)
            )
    pre_roll_peak = float(np.max(np.abs(pre_roll)))
    if pre_roll_peak > 0.98:
        pre_roll *= np.float32(0.98 / pre_roll_peak)

    overlay_length = min(len(phrase), len(edited_original.samples))
    overlay = (
        phrase[:overlay_length] * np.float32(0.50)
        + bass_phrase[:overlay_length] * np.float32(0.30)
    )
    fade = np.linspace(1.0, 0.0, overlay_length, dtype=np.float32)[:, None]
    opening = edited_original.samples.copy()
    source_bar_frames = max(1, round(len(phrase) / max(candidate.unit_bars, 1)))
    source_fade_frames = min(
        overlay_length,
        len(opening),
        round(source_bar_frames * REDRUM_ORIGINAL_FADE_IN_BARS),
    )
    source_gain = np.ones((overlay_length, 1), dtype=np.float32)
    if source_fade_frames > 1:
        phase = np.linspace(
            0.0, np.pi / 2.0, source_fade_frames, dtype=np.float32
        )[:, None]
        source_gain[:source_fade_frames] = np.sin(phase) ** 2
    opening[:overlay_length] = (
        edited_original.samples[:overlay_length] * source_gain + overlay * fade
    )

    # Protect the source's peak without globally changing its loudness. Reduce
    # only the added overlay when necessary; the untouched original stays intact.
    source_peak = max(float(np.max(np.abs(edited_original.samples))), 1e-6)
    allowed_peak = min(0.999, max(source_peak, 0.95))
    mixed_peak = float(np.max(np.abs(opening[:overlay_length])))
    if mixed_peak > allowed_peak:
        reduction = allowed_peak / mixed_peak
        opening[:overlay_length] = (
            edited_original.samples[:overlay_length] * source_gain
            + overlay * fade * reduction
        )
    return AudioData(
        np.concatenate((pre_roll, opening), axis=0).astype(np.float32, copy=False),
        edited_original.sample_rate,
    )


def redrum_added_seconds(candidate: SectionCandidate) -> float:
    return candidate.repetitions * (candidate.end - candidate.start)
