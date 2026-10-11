"""Optional Demucs execution and vocal-energy extraction."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import certifi
import librosa
import numpy as np
from scipy.signal import correlate, correlation_lags

from audioextender.audio.loading import AudioData, load_audio
from audioextender.core.exceptions import StemSeparationError


@dataclass
class StemResult:
    vocal_energy: np.ndarray
    instrumental_audio: AudioData
    drums_audio: AudioData
    separation_reliability: float
    temporary_directory: tempfile.TemporaryDirectory[str]

    def close(self) -> None:
        self.temporary_directory.cleanup()


def detect_sustained_vocal_boundaries(
    vocal_energy: np.ndarray, frame_times: np.ndarray, duration: float
) -> tuple[float | None, float | None]:
    """Estimate first sustained vocal entrance and final vocal release.

    A smoothed, adaptive threshold ignores isolated breaths, stem leakage, and
    short ad-libs. The result is deliberately used only when Demucs is enabled.
    """
    if len(vocal_energy) < 3 or len(frame_times) != len(vocal_energy):
        return None, None
    frame_seconds = max(float(np.median(np.diff(frame_times))), 1e-3)
    window = max(1, round(0.75 / frame_seconds))
    kernel = np.ones(window, dtype=float) / window
    smooth = np.convolve(np.clip(vocal_energy, 0.0, 1.5), kernel, mode="same")
    threshold = float(np.clip(np.percentile(smooth, 60) * 1.35, 0.16, 0.45))
    active = smooth >= threshold

    minimum_frames = max(1, round(0.80 / frame_seconds))
    gap_frames = max(1, round(0.35 / frame_seconds))
    # Close tiny gaps inside a sung line before extracting sustained regions.
    active = np.convolve(active.astype(int), np.ones(gap_frames, dtype=int), mode="same") > 0
    changes = np.diff(np.pad(active.astype(int), (1, 1)))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    regions = [(start, end) for start, end in zip(starts, ends, strict=True) if end - start >= minimum_frames]
    if not regions:
        return None, None

    opening_limit = min(90.0, duration * 0.40)
    opening = [region for region in regions if frame_times[region[0]] <= opening_limit]
    intro_before = float(frame_times[opening[0][0]]) if opening else None

    closing_start = duration * 0.55
    closing = [
        region for region in regions if frame_times[min(int(region[1]) - 1, len(frame_times) - 1)] >= closing_start
    ]
    outro_after = float(frame_times[min(int(closing[-1][1]) - 1, len(frame_times) - 1)]) if closing else None
    return intro_before, outro_after


def demucs_available() -> bool:
    return shutil.which("demucs") is not None or _module_available("demucs")


def _module_available(name: str) -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def analyze_vocal_stem(
    input_path: Path,
    source_sample_rate: int,
    frame_times: np.ndarray,
    hop_length: int,
    progress: Callable[[float, str], None] | None = None,
) -> StemResult:
    """Run four-stem Demucs and map vocal RMS onto the main feature timeline."""
    report = progress or (lambda _fraction, _label: None)
    if not demucs_available():
        raise StemSeparationError("Demucs is not installed. Install it with: pip install demucs")
    # Import lazily so the core, non-Demucs application does not require PyTorch.
    import torch

    temporary = tempfile.TemporaryDirectory(prefix="extended-edit-demucs-")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    report(0.0, f"Starting Demucs on {device.upper()}")
    command = [
        sys.executable,
        "-m",
        "demucs",
        "--device",
        device,
        "--out",
        temporary.name,
        "--filename",
        "{stem}.{ext}",
        str(input_path),
    ]
    # Python.org macOS installations sometimes have no configured OpenSSL CA
    # file even though the virtual environment has certifi. Demucs downloads its
    # model with urllib, which honors SSL_CERT_FILE. Point it at a maintained CA
    # bundle while keeping certificate verification fully enabled.
    environment = os.environ.copy()
    environment["SSL_CERT_FILE"] = certifi.where()
    environment["REQUESTS_CA_BUNDLE"] = certifi.where()
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        env=environment,
    )
    # Demucs/tqdm redraws progress with carriage returns instead of newlines.
    # Read one character at a time so those redraws can drive the parent bar.
    recent_output: list[str] = []
    current = ""
    assert process.stdout is not None
    while True:
        character = process.stdout.read(1)
        if character == "" and process.poll() is not None:
            break
        if character not in ("\r", "\n"):
            current += character
            continue
        line = current.strip()
        current = ""
        if not line:
            continue
        recent_output.append(line)
        recent_output = recent_output[-20:]
        percentages = re.findall(r"(?<!\d)(\d{1,3})%", line)
        if percentages:
            percent = min(100, int(percentages[-1]))
            report(percent / 100.0, f"Demucs {device.upper()} separation {percent}%")
        elif "Downloading" in line:
            report(0.02, "Downloading Demucs model")

    return_code = process.wait()
    if return_code != 0:
        temporary.cleanup()
        detail = recent_output[-1] if recent_output else "unknown error"
        joined_output = "\n".join(recent_output)
        if "CERTIFICATE_VERIFY_FAILED" in joined_output:
            detail = (
                "secure model download failed certificate verification even with "
                f"the certifi bundle at {certifi.where()}"
            )
        raise StemSeparationError(f"Demucs failed: {detail}")

    report(1.0, f"Demucs {device.upper()} separation complete")
    stem_paths = {
        name: next(iter(Path(temporary.name).rglob(f"{name}.wav")), None)
        for name in ("vocals", "drums", "bass", "other")
    }
    if any(path is None for path in stem_paths.values()):
        temporary.cleanup()
        missing = ", ".join(name for name, path in stem_paths.items() if path is None)
        raise StemSeparationError(f"Demucs completed but did not produce: {missing}")
    assert all(path is not None for path in stem_paths.values())

    def aligned_stem(path: Path) -> AudioData:
        stem = load_audio(path)
        samples = stem.samples
        if stem.sample_rate != source_sample_rate:
            samples = np.column_stack(
                [
                    librosa.resample(
                        samples[:, channel],
                        orig_sr=stem.sample_rate,
                        target_sr=source_sample_rate,
                    )
                    for channel in range(samples.shape[1])
                ]
            )
        return AudioData(np.asarray(samples, dtype=np.float32), source_sample_rate)

    vocals_path = stem_paths["vocals"]
    assert vocals_path is not None
    vocals = aligned_stem(vocals_path)
    instrumental_stems: dict[str, AudioData] = {}
    for name in ("drums", "bass", "other"):
        path = stem_paths[name]
        assert path is not None
        instrumental_stems[name] = aligned_stem(path)
    common_length = min(len(stem.samples) for stem in (vocals, *instrumental_stems.values()))
    instrumental_samples = np.sum(
        [stem.samples[:common_length] for stem in instrumental_stems.values()], axis=0
    ).astype(np.float32)
    # Demucs stems should approximately reconstruct the source. Measure this
    # before trusting them for audible construction rather than analysis alone.
    # MP3 decoders can disagree by a small encoder-delay offset, so align the
    # reconstruction first and apply that correction to every audible stem.
    source = load_audio(input_path)
    compare_length = min(common_length, len(source.samples))
    raw_vocals = vocals.samples[:compare_length]
    raw_instrumental = instrumental_samples[:compare_length]
    raw_reconstructed = raw_instrumental + raw_vocals
    stride = max(1, compare_length // 120_000)
    reference_mono = np.mean(source.samples[:compare_length:stride], axis=1)
    reconstructed_mono = np.mean(raw_reconstructed[::stride], axis=1)
    reference_mono -= np.mean(reference_mono)
    reconstructed_mono -= np.mean(reconstructed_mono)
    full_correlation = correlate(reference_mono, reconstructed_mono, mode="full", method="fft")
    lags = correlation_lags(len(reference_mono), len(reconstructed_mono), mode="full")
    maximum_lag = max(1, round(0.5 * source_sample_rate / stride))
    allowed = np.abs(lags) <= maximum_lag
    lag_frames = int(lags[allowed][np.argmax(full_correlation[allowed])]) * stride

    def align_samples(samples: np.ndarray) -> np.ndarray:
        target = np.zeros((len(source.samples), samples.shape[1]), dtype=np.float32)
        if lag_frames < 0:
            source_start = -lag_frames
            length = min(len(target), len(samples) - source_start)
            if length > 0:
                target[:length] = samples[source_start : source_start + length]
        else:
            length = min(len(target) - lag_frames, len(samples))
            if length > 0:
                target[lag_frames : lag_frames + length] = samples[:length]
        return target

    aligned_vocals = align_samples(raw_vocals)
    aligned_instrumental = align_samples(raw_instrumental)
    raw_drums = instrumental_stems["drums"].samples[:compare_length]
    aligned_drums = align_samples(raw_drums)
    vocals = AudioData(aligned_vocals, source_sample_rate)
    instrumental = AudioData(aligned_instrumental, source_sample_rate)

    mono = librosa.to_mono(vocals.samples.T)
    rms = librosa.feature.rms(y=mono, hop_length=hop_length)[0]
    stem_times = librosa.frames_to_time(np.arange(len(rms)), sr=source_sample_rate, hop_length=hop_length)
    normalized = rms / max(float(np.percentile(rms, 95)), 1e-8)
    aligned = np.interp(frame_times, stem_times, normalized, left=0.0, right=0.0)

    reconstructed = (aligned_instrumental + aligned_vocals)[::stride]
    reference = source.samples[::stride]
    error_ratio = float(
        np.sqrt(np.mean((reconstructed - reference) ** 2)) / max(float(np.sqrt(np.mean(reference**2))), 1e-8)
    )
    correlation = float(np.corrcoef(reference.reshape(-1), reconstructed.reshape(-1))[0, 1])
    if not np.isfinite(correlation):
        correlation = 0.0
    reconstruction_rms = max(float(np.sqrt(np.mean(reconstructed**2))), 1e-8)
    reference_rms = max(float(np.sqrt(np.mean(reference**2))), 1e-8)
    gain_match = float(np.exp(-abs(np.log(reconstruction_rms / reference_rms))))
    reliability = float(
        np.clip(
            0.55 * max(0.0, correlation) + 0.25 * gain_match + 0.20 * np.exp(-2.0 * error_ratio),
            0.0,
            1.0,
        )
    )
    return StemResult(
        np.clip(aligned, 0.0, 1.5), instrumental, AudioData(aligned_drums, source_sample_rate), reliability, temporary
    )
