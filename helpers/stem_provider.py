"""Stem acquisition service with cache, Demucs, and vocal-boundary policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from helpers.analysis import TrackAnalysis
from helpers.audio_loader import AudioData
from helpers.cache import AnalysisCache
from helpers.config import EditConfig
from helpers.interfaces import ProgressReporter
from helpers.stems import (
    StemResult,
    analyze_vocal_stem,
    detect_sustained_vocal_boundaries,
)

StemSeparator = Callable[..., StemResult]
BoundaryDetector = Callable[
    [np.ndarray, np.ndarray, float], tuple[float | None, float | None]
]


@dataclass(frozen=True)
class StemAnalysis:
    """Stem-derived data consumed by selection and rendering."""

    vocal_energy: np.ndarray | None = None
    instrumental_audio: AudioData | None = None
    drums_audio: AudioData | None = None
    reliability: float = 0.0
    cache_hit: bool = False
    intro_boundary: float | None = None
    outro_boundary: float | None = None


class StemProvider:
    """Provide optional stems without exposing Demucs or cache mechanics."""

    def __init__(
        self,
        separator: StemSeparator = analyze_vocal_stem,
        boundary_detector: BoundaryDetector = detect_sustained_vocal_boundaries,
    ) -> None:
        self._separator = separator
        self._boundary_detector = boundary_detector

    def analyze(
        self,
        source: Path,
        audio: AudioData,
        track: TrackAnalysis,
        config: EditConfig,
        cache: AnalysisCache,
        progress: ProgressReporter,
    ) -> StemAnalysis:
        if not config.use_stems:
            return StemAnalysis()

        vocal_energy = cache.load_vocals(source, config)
        cached_instrumental = cache.load_instrumental(source, config)
        cached_drums = cache.load_drums(source, config)
        vocals_valid = vocal_energy is not None and len(vocal_energy) == len(
            track.frame_times
        )
        cache_hit = (
            vocals_valid and cached_instrumental is not None
            and cached_drums is not None
        )

        if cache_hit:
            assert vocal_energy is not None and cached_instrumental is not None
            instrumental_audio, reliability = cached_instrumental
            assert cached_drums is not None
            drums_audio = cached_drums
            progress.update(80, "Loaded cached vocal analysis")
            progress.log("Loaded Demucs vocal and instrumental analysis from cache")
        else:
            progress.update(72, "Separating stems with Demucs")
            separated = self._separator(
                source,
                audio.sample_rate,
                track.frame_times,
                config.analysis_hop_length,
                lambda fraction, label: progress.update(70 + 10 * fraction, label),
            )
            try:
                vocal_energy = separated.vocal_energy
                instrumental_audio = separated.instrumental_audio
                drums_audio = separated.drums_audio
                reliability = separated.separation_reliability
                cache.save_vocals(source, config, vocal_energy)
                cache.save_instrumental(
                    source, config, instrumental_audio, reliability
                )
                cache.save_drums(source, config, drums_audio)
            finally:
                # Returned arrays are in memory, so Demucs' temporary directory
                # can be reclaimed before candidate selection begins.
                separated.close()
            if config.cache_enabled:
                progress.log("Saved Demucs vocal and instrumental analysis to cache")

        assert vocal_energy is not None
        progress.log("Using vocal-stem energy for phrase selection")
        progress.log(f"Stem construction reliability: {reliability:.0%}")
        intro_boundary, outro_boundary = self._boundary_detector(
            vocal_energy, track.frame_times, audio.duration
        )
        return StemAnalysis(
            vocal_energy=vocal_energy,
            instrumental_audio=instrumental_audio,
            drums_audio=drums_audio,
            reliability=reliability,
            cache_hit=cache_hit,
            intro_boundary=intro_boundary,
            outro_boundary=outro_boundary,
        )
