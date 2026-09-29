"""Assemble selected sections and source audio into an extended edit."""

from __future__ import annotations

from dataclasses import replace

import librosa
import numpy as np

from helpers.audio_loader import AudioData
from helpers.section_selector import SectionCandidate
from helpers.splice_policy import (
    choose_splice_mode,
    crossfade_duration_ms,
    tail_duration_ms,
)


def _slice(audio: AudioData, start: float, end: float) -> np.ndarray:
    first = max(0, round(start * audio.sample_rate))
    last = min(len(audio.samples), round(end * audio.sample_rate))
    return audio.samples[first:last].copy()


def _smooth_join(left: np.ndarray, right: np.ndarray, fade_frames: int) -> np.ndarray:
    """Use complementary raised-cosine fades to avoid clicks and gain bumps."""
    length = min(fade_frames, len(left), len(right))
    if length <= 0:
        return np.concatenate((left, right), axis=0)
    phase = np.linspace(0.0, np.pi / 2.0, length, dtype=np.float32)[:, None]
    # cos² + sin² = 1. Correlated repeated material therefore stays near unity
    # rather than receiving the +3 dB bump of a conventional equal-power fade.
    mixed = left[-length:] * np.cos(phase) ** 2 + right[:length] * np.sin(phase) ** 2
    return np.concatenate((left[:-length], mixed, right[length:]), axis=0)


def insert_audio_region(
    edited: AudioData,
    source: AudioData,
    source_start: float,
    source_end: float,
    destination: float,
    copies: int = 1,
    crossfade_ms: float = 15.0,
) -> AudioData:
    """Insert source material into an assembled edit using click-safe joins."""
    if source_end <= source_start or copies < 1:
        raise ValueError("Inserted region must have positive duration and copies")
    if destination < 0 or destination > edited.duration:
        raise ValueError("Insertion destination is outside the extended edit")
    region = _slice(source, source_start, source_end)
    if len(region) == 0:
        raise ValueError("Inserted source region is empty")
    fade_frames = max(1, round(crossfade_ms * edited.sample_rate / 1000.0))
    inserted = region
    for _ in range(1, copies):
        inserted = _smooth_join(inserted, region, fade_frames)
    at = min(len(edited.samples), round(destination * edited.sample_rate))
    assembled = _smooth_join(edited.samples[:at], inserted, fade_frames)
    assembled = _smooth_join(assembled, edited.samples[at:], fade_frames)
    return AudioData(np.asarray(assembled, dtype=np.float32), edited.sample_rate)


def optimize_candidate_boundaries(
    audio: AudioData, candidate: SectionCandidate, search_ms: float = 40.0
) -> SectionCandidate:
    """Micro-adjust both boundaries to find a cleaner waveform loop point.

    Confident grids keep the phrase duration exact.  On uncertain grids the end
    may move independently by at most 8 ms: small enough to be inaudible as a
    tempo change, but enough to avoid cutting a loose performance between its
    true pulses.  The search favors matching waveform value and slope, near-zero
    crossings, and minimal deviation from the analyzed grid.
    """
    candidate = replace(candidate, splice_mode=choose_splice_mode(candidate))
    sample_rate = audio.sample_rate
    nominal_start = round(candidate.start * sample_rate)
    nominal_end = round(candidate.end * sample_rate)
    radius = max(1, round(search_ms * sample_rate / 1000.0))
    low = max(-radius, -nominal_start + 2)
    high = min(radius, len(audio.samples) - nominal_end - 2)
    if low >= high:
        return candidate

    mono = np.mean(audio.samples, axis=1)
    # Evaluate roughly 0.25 ms increments rather than every sample.  The final
    # crossfade handles sub-sample-scale differences and this keeps batch work
    # inexpensive even at 96 kHz.
    step = max(1, round(sample_rate * 0.00025))
    offsets = np.arange(low, high + 1, step, dtype=int)
    duration_radius = (
        round(sample_rate * 0.008)
        if candidate.boundary_grid_confidence < 0.60
        else 0
    )
    duration_offsets = np.arange(-duration_radius, duration_radius + 1, step, dtype=int)
    best_score = float("inf")
    best_start_offset = 0
    best_duration_offset = 0
    amplitude_scale = max(float(np.percentile(np.abs(mono), 75)), 1e-3)
    for duration_offset in duration_offsets:
        starts = nominal_start + offsets
        ends = nominal_end + offsets + duration_offset
        valid = (starts >= 2) & (ends < len(mono) - 2)
        if not np.any(valid):
            continue
        valid_offsets = offsets[valid]
        starts = starts[valid]
        ends = ends[valid]
        value_jump = np.abs(mono[ends - 1] - mono[starts])
        left_slope = mono[ends - 1] - mono[ends - 2]
        right_slope = mono[starts + 1] - mono[starts]
        slope_jump = np.abs(left_slope - right_slope)
        zero_proximity = np.abs(mono[ends - 1]) + np.abs(mono[starts])
        grid_cost = 0.025 * np.abs(valid_offsets) / max(radius, 1)
        duration_cost = 0.04 * abs(duration_offset) / max(duration_radius, 1)
        score = (
            value_jump / amplitude_scale
            + 0.45 * slope_jump / amplitude_scale
            + 0.15 * zero_proximity / amplitude_scale
            + grid_cost
            + duration_cost
        )
        index = int(np.argmin(score))
        if float(score[index]) < best_score:
            best_score = float(score[index])
            best_start_offset = int(valid_offsets[index])
            best_duration_offset = int(duration_offset)
    start_seconds = best_start_offset / sample_rate
    duration_seconds = best_duration_offset / sample_rate
    return replace(
        candidate,
        start=candidate.start + start_seconds,
        end=candidate.end + start_seconds + duration_seconds,
        boundary_adjustment_ms=1000.0 * start_seconds,
        duration_adjustment_ms=1000.0 * duration_seconds,
    )


def _choose_splice_mode(candidate: SectionCandidate) -> str:
    """Backward-compatible wrapper for callers of the original private API."""
    return choose_splice_mode(candidate)


def adaptive_crossfade_ms(candidate: SectionCandidate, minimum_ms: float) -> float:
    return crossfade_duration_ms(candidate, minimum_ms)


def _adaptive_fade_frames(
    candidate: SectionCandidate, sample_rate: int, minimum_ms: float
) -> int:
    fade_ms = adaptive_crossfade_ms(candidate, minimum_ms)
    return max(1, round(sample_rate * fade_ms / 1000.0))


def _harmonic_component(samples: np.ndarray) -> np.ndarray:
    """Extract sustained stereo content while rejecting most drum transients."""
    if len(samples) < 32:
        return samples.copy()
    channels = []
    for channel in range(samples.shape[1]):
        harmonic, _percussive = librosa.effects.hpss(samples[:, channel])
        channels.append(harmonic)
    return np.column_stack(channels).astype(np.float32, copy=False)


def _tail_duration_frames(candidate: SectionCandidate, sample_rate: int) -> int:
    """Carry 250–750 ms of ambience, using more when timbre changes strongly."""
    return max(1, round(sample_rate * tail_duration_ms(candidate) / 1000.0))


def _preserve_harmonic_tail(
    incoming: np.ndarray,
    natural_continuation: np.ndarray,
    tail_frames: int,
) -> np.ndarray:
    """Carry the real synth/reverb release over the repeated phrase start.

    Only harmonic material is blended for hundreds of milliseconds. Incoming
    percussion stays at full strength, avoiding the doubled kicks and softened
    transients caused by a long full-mix crossfade.
    """
    length = min(tail_frames, len(incoming), len(natural_continuation))
    if length < 32:
        return incoming

    # Include a little extra context so HPSS median filters behave well at the
    # end of the portion that will actually be used.
    context = min(len(incoming), len(natural_continuation), length + 2048)
    incoming_segment = incoming[:context]
    continuation_segment = natural_continuation[:context]
    incoming_harmonic = _harmonic_component(incoming_segment)[:length]
    continuation_harmonic = _harmonic_component(continuation_segment)[:length]
    incoming_percussive = incoming[:length] - incoming_harmonic

    phase = np.linspace(0.0, np.pi / 2.0, length, dtype=np.float32)[:, None]
    harmonic_blend = (
        continuation_harmonic * np.cos(phase) ** 2
        + incoming_harmonic * np.sin(phase) ** 2
    )
    prepared = incoming.copy()
    prepared[:length] = incoming_percussive + harmonic_blend
    return prepared


def create_extended_edit(
    audio: AudioData,
    intro: SectionCandidate | None,
    outro: SectionCandidate | None,
    crossfade_ms: float,
    instrumental_audio: AudioData | None = None,
    stem_reliability: float = 0.0,
    minimum_stem_reliability: float = 1.0,
    minimum_vocal_coverage: float = 1.0,
) -> AudioData:
    """Repeat phrases in context while retaining the natural opening and ending.

    The intro phrase is inserted immediately before its original occurrence. The
    outro phrase is inserted immediately after its original occurrence but before
    the remaining natural tail. Thus only phrase-end-to-phrase-start loop seams
    are artificial; the song is never forced to jump from its ending to a peak or
    from a peak back to its quiet opening.
    """
    if intro is None and outro is None:
        return AudioData(audio.samples.copy(), audio.sample_rate)

    intro_start = max(0, round(intro.start * audio.sample_rate)) if intro else 0
    outro_end = (
        min(len(audio.samples), round(outro.end * audio.sample_rate))
        if outro else len(audio.samples)
    )
    if intro is not None and outro is not None and intro_start >= outro_end:
        raise ValueError("Selected intro must occur before the selected outro")

    def loop_source(candidate: SectionCandidate) -> AudioData:
        if should_use_instrumental(
            candidate, instrumental_audio, stem_reliability,
            minimum_stem_reliability, minimum_vocal_coverage,
        ):
            assert instrumental_audio is not None
            return instrumental_audio
        return audio

    if intro is not None:
        intro_source = loop_source(intro)
        intro_audio = _slice(intro_source, intro.start, intro.end)
        intro_fade_frames = _adaptive_fade_frames(intro, audio.sample_rate, crossfade_ms)
        intro_tail_frames = _tail_duration_frames(intro, audio.sample_rate)
        intro_continuation = _slice(
            intro_source, intro.end,
            intro.end + intro_tail_frames / audio.sample_rate + 0.1
        )
        before_intro_loop = np.concatenate((audio.samples[:intro_start], intro_audio), axis=0)
        for _repeat in range(1, intro.repetitions):
            prepared_copy = _preserve_harmonic_tail(
                intro_audio, intro_continuation, intro_tail_frames
            )
            before_intro_loop = _smooth_join(
                before_intro_loop, prepared_copy, intro_fade_frames
            )
        through_original_outro = _preserve_harmonic_tail(
            audio.samples[intro_start:outro_end], intro_continuation, intro_tail_frames
        )
        assembled = _smooth_join(
            before_intro_loop, through_original_outro, intro_fade_frames
        )
    else:
        assembled = audio.samples[:outro_end].copy()

    if outro is not None:
        outro_source = loop_source(outro)
        outro_audio = _slice(outro_source, outro.start, outro.end)
        outro_fade_frames = _adaptive_fade_frames(outro, audio.sample_rate, crossfade_ms)
        outro_tail_frames = _tail_duration_frames(outro, audio.sample_rate)
        outro_continuation = _slice(
            outro_source, outro.end,
            outro.end + outro_tail_frames / audio.sample_rate + 0.1
        )
        for _repeat in range(outro.repetitions):
            prepared_outro = _preserve_harmonic_tail(
                outro_audio, outro_continuation, outro_tail_frames
            )
            assembled = _smooth_join(assembled, prepared_outro, outro_fade_frames)
    completed = np.concatenate((assembled, audio.samples[outro_end:]), axis=0)
    return AudioData(np.asarray(completed, dtype=np.float32), audio.sample_rate)


def should_use_instrumental(
    candidate: SectionCandidate | None,
    instrumental_audio: AudioData | None,
    reliability: float,
    minimum_reliability: float,
    minimum_vocal_coverage: float,
) -> bool:
    """Return whether stem construction is safer than repeating the full mix."""
    return bool(
        candidate is not None
        and instrumental_audio is not None
        and instrumental_audio.sample_rate > 0
        and reliability >= minimum_reliability
        and candidate.vocal_coverage >= minimum_vocal_coverage
    )


def create_splice_previews(
    edited: AudioData,
    intro: SectionCandidate | None,
    outro: SectionCandidate | None,
    crossfade_ms: float,
    context_seconds: float,
) -> tuple[AudioData | None, AudioData | None]:
    """Extract short auditions centered on the actual edited splice positions."""
    intro_added = 0.0
    intro_preview = None
    if intro is not None:
        if intro.splice_mode == "redrum":
            added = intro.repetitions * (intro.end - intro.start)
            intro_preview = AudioData(
                _slice(edited, 0.0, added + context_seconds), edited.sample_rate
            )
            intro_added = added
        else:
            fade = adaptive_crossfade_ms(intro, crossfade_ms) / 1000.0
            unit = intro.end - intro.start
            intro_added = intro.repetitions * max(0.0, unit - fade)
            # Audition the complete edit in context: original lead-in (when the
            # insertion is not at zero), every added intro copy, then the original
            # song continuing after the loop returns to its source phrase.
            seam = intro.start + intro_added
            intro_preview = AudioData(
                _slice(
                    edited,
                    intro.start - context_seconds,
                    seam + context_seconds,
                ),
                edited.sample_rate,
            )

    outro_preview = None
    if outro is not None:
        # Include both handoffs: original song -> added outro, then the complete
        # added outro -> untouched natural closing section. Centering only the
        # first splice hid whether the repeated material returned gracefully.
        seam = outro.end + intro_added
        fade = adaptive_crossfade_ms(outro, crossfade_ms) / 1000.0
        unit = outro.end - outro.start
        outro_added = outro.repetitions * max(0.0, unit - fade)
        outro_preview = AudioData(
            _slice(
                edited,
                seam - context_seconds,
                seam + outro_added + context_seconds,
            ),
            edited.sample_rate,
        )
    return intro_preview, outro_preview
