"""Versioned on-disk cache for expensive track and vocal analysis."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from helpers.analysis import TrackAnalysis
from helpers.audio_loader import AudioData
from helpers.config import EditConfig

# Increment this whenever cached feature meanings or algorithms change.
CACHE_VERSION = 5
_ARRAY_FIELDS = (
    "beat_times", "downbeat_indices", "bar_boundaries", "frame_times", "rms",
    "onset", "percussion_rms", "harmonic_rms", "bass_rms",
    "spectral_centroid", "spectral_flux", "chroma", "spectral_profile",
    "bar_section_labels", "bar_section_confidence",
    "bar_grid_confidence",
)


class AnalysisCache:
    def __init__(self, directory: Path, enabled: bool = True, refresh: bool = False) -> None:
        self.directory = directory.expanduser().resolve()
        self.enabled = enabled
        self.refresh = refresh
        if enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _key(self, source: Path, config: EditConfig) -> str:
        stat = source.stat()
        identity = {
            "version": CACHE_VERSION,
            "path": str(source.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "beats_per_bar": config.beats_per_bar,
            "hop_length": config.analysis_hop_length,
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _path(self, source: Path, config: EditConfig, suffix: str) -> Path:
        return self.directory / f"{self._key(source, config)}.{suffix}.npz"

    @staticmethod
    def _atomic_save(path: Path, **values: Any) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                np.savez_compressed(handle, **values)
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def load_analysis(self, source: Path, config: EditConfig) -> TrackAnalysis | None:
        if not self.enabled or self.refresh:
            return None
        path = self._path(source, config, "analysis")
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                values = {field: np.asarray(data[field]) for field in _ARRAY_FIELDS}
                return TrackAnalysis(
                    bpm=float(data["bpm"]),
                    tempo_drift_percent=float(data["tempo_drift_percent"]),
                    beat_grid_confidence=float(data["beat_grid_confidence"]),
                    key_label=str(data["key_label"]),
                    key_confidence=float(data["key_confidence"]),
                    key_root=int(data["key_root"]),
                    key_mode=str(data["key_mode"]),
                    groove_label=str(data["groove_label"]),
                    swing_ratio=float(data["swing_ratio"]),
                    timing_label=str(data["timing_label"]),
                    downbeat_continuity=float(data["downbeat_continuity"]),
                    **values,
                )
        except (OSError, ValueError, KeyError, EOFError):
            return None

    def save_analysis(
        self, source: Path, config: EditConfig, analysis: TrackAnalysis
    ) -> None:
        if not self.enabled:
            return
        path = self._path(source, config, "analysis")
        values = {field: np.asarray(getattr(analysis, field)) for field in _ARRAY_FIELDS}
        self._atomic_save(
            path,
            bpm=np.asarray(analysis.bpm),
            tempo_drift_percent=np.asarray(analysis.tempo_drift_percent),
            beat_grid_confidence=np.asarray(analysis.beat_grid_confidence),
            key_label=np.asarray(analysis.key_label),
            key_confidence=np.asarray(analysis.key_confidence),
            key_root=np.asarray(analysis.key_root),
            key_mode=np.asarray(analysis.key_mode),
            groove_label=np.asarray(analysis.groove_label),
            swing_ratio=np.asarray(analysis.swing_ratio),
            timing_label=np.asarray(analysis.timing_label),
            downbeat_continuity=np.asarray(analysis.downbeat_continuity),
            **values,
        )

    def load_vocals(self, source: Path, config: EditConfig) -> np.ndarray | None:
        if not self.enabled or self.refresh:
            return None
        path = self._path(source, config, "vocals")
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                vocals = np.asarray(data["vocal_energy"], dtype=float)
            return vocals
        except (OSError, ValueError, KeyError, EOFError):
            return None

    def save_vocals(
        self, source: Path, config: EditConfig, vocal_energy: np.ndarray
    ) -> None:
        if self.enabled:
            self._atomic_save(
                self._path(source, config, "vocals"),
                vocal_energy=np.asarray(vocal_energy, dtype=np.float32),
            )

    def load_instrumental(
        self, source: Path, config: EditConfig
    ) -> tuple[AudioData, float] | None:
        if not self.enabled or self.refresh:
            return None
        audio_path = self._path(source, config, "instrumental").with_suffix(".instrumental.wav")
        meta_path = self._path(source, config, "stemmeta")
        if not audio_path.exists() or not meta_path.exists():
            return None
        try:
            samples, sample_rate = sf.read(audio_path, always_2d=True, dtype="float32")
            with np.load(meta_path, allow_pickle=False) as data:
                reliability = float(data["reliability"])
            return AudioData(np.ascontiguousarray(samples), int(sample_rate)), reliability
        except (OSError, ValueError, KeyError, EOFError, sf.LibsndfileError):
            return None

    def save_instrumental(
        self,
        source: Path,
        config: EditConfig,
        instrumental: AudioData,
        reliability: float,
    ) -> None:
        if not self.enabled:
            return
        audio_path = self._path(source, config, "instrumental").with_suffix(".instrumental.wav")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{audio_path.stem}-", suffix=".wav", dir=audio_path.parent
        )
        os.close(descriptor)
        try:
            sf.write(
                temporary_name, instrumental.samples, instrumental.sample_rate,
                format="WAV", subtype="FLOAT",
            )
            os.replace(temporary_name, audio_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        self._atomic_save(
            self._path(source, config, "stemmeta"),
            reliability=np.asarray(reliability),
        )

    def load_drums(self, source: Path, config: EditConfig) -> AudioData | None:
        if not self.enabled or self.refresh:
            return None
        path = self._path(source, config, "drums").with_suffix(".drums.wav")
        if not path.exists():
            return None
        try:
            samples, sample_rate = sf.read(path, always_2d=True, dtype="float32")
            return AudioData(np.ascontiguousarray(samples), int(sample_rate))
        except (OSError, ValueError, EOFError, sf.LibsndfileError):
            return None

    def save_drums(
        self, source: Path, config: EditConfig, drums: AudioData
    ) -> None:
        if not self.enabled:
            return
        path = self._path(source, config, "drums").with_suffix(".drums.wav")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".wav", dir=path.parent
        )
        os.close(descriptor)
        try:
            sf.write(
                temporary_name, drums.samples, drums.sample_rate,
                format="WAV", subtype="FLOAT",
            )
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)


def clear_cache(directory: Path) -> int:
    """Delete only AudioExtender analysis/stem cache entries and return their count."""
    directory = directory.expanduser().resolve()
    if not directory.exists():
        return 0
    removed = 0
    for pattern in ("*.npz", "*.instrumental.wav", "*.drums.wav"):
        for path in directory.glob(pattern):
            if path.is_file():
                path.unlink()
                removed += 1
    return removed
