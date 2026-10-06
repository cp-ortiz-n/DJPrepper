"""Fast, explainable audio-file quality measurements for library tracks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class AudioQuality:
    score: int
    label: str
    sample_rate: int
    bit_depth: int
    channels: int
    codec: str
    container_bitrate_kbps: int
    spectral_cutoff_hz: int
    clipping_percent: float
    digital_silence_percent: float
    confidence: str
    target_status: str
    target_reason: str
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _bit_depth(subtype: str) -> int:
    digits = "".join(character for character in subtype if character.isdigit())
    return int(digits) if digits else 0


def analyze_audio_quality(
    path: Path, *, window_seconds: float = 2.0, source_is_transcoded_lossy: bool = False
) -> AudioQuality:
    """Inspect representative windows without loading the entire track into memory."""
    info = sf.info(path)
    sample_rate = int(info.samplerate)
    channels = int(info.channels)
    bit_depth = _bit_depth(str(info.subtype or ""))
    frame_count = int(info.frames)
    window_frames = max(2048, min(frame_count, round(sample_rate * window_seconds)))
    starts = sorted(
        {
            max(0, min(frame_count - window_frames, round((frame_count - window_frames) * point)))
            for point in (0.08, 0.27, 0.50, 0.73, 0.92)
        }
    )
    windows: list[np.ndarray] = []
    with sf.SoundFile(path) as audio:
        for start in starts:
            audio.seek(start)
            samples = audio.read(window_frames, dtype="float32", always_2d=True)
            if len(samples):
                windows.append(samples)
    if not windows:
        raise ValueError("Audio file contains no readable samples")
    samples = np.concatenate(windows, axis=0)
    mono = np.mean(samples, axis=1)
    clipping = float(np.mean(np.abs(samples) >= 0.999)) * 100.0
    block = max(1, round(sample_rate * 0.05))
    usable = len(mono) // block * block
    block_rms = np.sqrt(np.mean(mono[:usable].reshape(-1, block) ** 2, axis=1)) if usable else np.array([])
    digital_silence = float(np.mean(block_rms < 1e-5)) * 100.0 if len(block_rms) else 0.0

    cutoff_values: list[float] = []
    for window in windows:
        signal = np.mean(window, axis=1)
        signal = signal - np.mean(signal)
        spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal)))) ** 2
        total = float(np.sum(spectrum))
        if total <= 1e-12:
            continue
        cumulative = np.cumsum(spectrum) / total
        frequency = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
        cutoff_values.append(float(frequency[min(len(frequency) - 1, int(np.searchsorted(cumulative, 0.999)))]))
    cutoff = int(round(float(np.median(cutoff_values)))) if cutoff_values else 0

    score = 100.0
    notes: list[str] = []
    if sample_rate < 44100:
        score -= 25
        notes.append(f"{sample_rate / 1000:g} kHz sample rate")
    if bit_depth and bit_depth < 16:
        score -= 15
        notes.append(f"{bit_depth}-bit source")
    nyquist = sample_rate / 2.0
    if cutoff and nyquist >= 20000:
        if cutoff < 15000:
            score -= 45
            notes.append("strong high-frequency cutoff; low-bitrate transcode possible")
        elif cutoff < 17000:
            score -= 32
            notes.append("high-frequency cutoff; lossy source likely")
        elif cutoff < 19000:
            score -= 20
            notes.append("limited high-frequency content; lossy source likely")
        elif cutoff < 20750:
            # A decoded WAV can report a large PCM container bitrate even when
            # its source was lossy.  Do not award an Excellent rating when the
            # sampled signal has the bandwidth ceiling commonly left by a
            # compressed source.  This is an estimate, not a claimed bitrate.
            score -= 12
            notes.append("high-quality lossy source possible; 320 kbps is not verifiable from this WAV")
    if clipping >= 0.1:
        score -= 25
        notes.append("audible clipping risk")
    elif clipping >= 0.01:
        score -= 12
        notes.append("some clipped samples")
    if digital_silence >= 5:
        score -= 12
        notes.append("possible silence or dropout sections")
    score_value = int(round(max(0.0, min(100.0, score))))
    label = (
        "excellent" if score_value >= 90 else "good" if score_value >= 75 else "review" if score_value >= 55 else "poor"
    )
    if not notes:
        notes.append("no obvious technical defects in sampled audio")
    bitrate = int(round(path.stat().st_size * 8 / max(float(info.duration), 0.001) / 1000))
    extension = path.suffix.lower()
    lossy_extensions = {".mp3", ".aac", ".m4a", ".ogg", ".opus", ".wma"}
    lossless_extensions = {".wav", ".wave", ".flac", ".aif", ".aiff", ".alac"}
    if source_is_transcoded_lossy:
        target_status = "unverified"
        target_reason = "Saved as WAV after a lossy download; the original encoded bitrate was not retained"
    elif extension in lossy_extensions:
        target_status = "meets_target" if bitrate >= 320 else "below_target"
        target_reason = f"Encoded stream is approximately {bitrate} kbps; target is 320 kbps"
    elif extension in lossless_extensions:
        meets_lossless = sample_rate >= 44100 and bit_depth >= 16
        target_status = "meets_target" if meets_lossless else "below_target"
        target_reason = f"{sample_rate / 1000:g} kHz / {bit_depth}-bit; lossless target is 44.1 kHz / 16-bit"
    else:
        target_status = "unverified"
        target_reason = "The original encoding quality could not be verified"
    return AudioQuality(
        score=score_value,
        label=label,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        channels=channels,
        codec=str(info.subtype or info.format or "unknown"),
        container_bitrate_kbps=bitrate,
        spectral_cutoff_hz=cutoff,
        clipping_percent=round(clipping, 4),
        digital_silence_percent=round(digital_silence, 2),
        confidence="estimated",
        target_status=target_status,
        target_reason=target_reason,
        notes=notes,
    )
