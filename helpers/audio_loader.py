"""Stereo-safe audio loading and WAV export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".aif", ".aiff"}


@dataclass
class AudioData:
    """Audio samples in frames-by-channels layout."""

    samples: np.ndarray
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate


def load_audio(path: Path) -> AudioData:
    """Load without resampling and retain all source channels.

    SoundFile handles WAV/FLAC/AIFF directly. Librosa supplies an FFmpeg/audioread
    fallback for MP3 builds where libsndfile lacks MP3 support.
    """
    path = path.expanduser().resolve()
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported input format: {path.suffix}")
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        samples, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    except (RuntimeError, sf.LibsndfileError):
        decoded, sample_rate = librosa.load(path, sr=None, mono=False, dtype=np.float32)
        if decoded.ndim == 1:
            samples = decoded[:, np.newaxis]
        else:
            samples = decoded.T

    if samples.shape[1] == 1:
        # The requested output is stereo; duplicate mono without changing gain.
        samples = np.repeat(samples, 2, axis=1)
    elif samples.shape[1] > 2:
        # DJ software is most predictable with stereo. Use a conservative downmix.
        left = samples[:, 0] + 0.5 * np.sum(samples[:, 2::2], axis=1)
        right = samples[:, 1] + 0.5 * np.sum(samples[:, 3::2], axis=1)
        samples = np.column_stack((left, right)) / max(1.0, samples.shape[1] / 2)

    return AudioData(np.ascontiguousarray(samples, dtype=np.float32), int(sample_rate))


def export_wav(audio: AudioData, path: Path, pcm_bits: int = 24) -> None:
    """Write PCM WAV, applying only the gain needed to prevent clipping."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.asarray(audio.samples, dtype=np.float32)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 0.999:
        samples = samples * (0.999 / peak)
    subtype = "PCM_24" if pcm_bits == 24 else "PCM_16"
    sf.write(path, samples, audio.sample_rate, format="WAV", subtype=subtype)

