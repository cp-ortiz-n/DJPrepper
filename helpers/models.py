"""Application-level immutable result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from helpers.cue_export import CuePoint
from helpers.section_selector import SectionCandidate


@dataclass(frozen=True)
class FileResult:
    """Complete processing outcome consumed by reports and CLI presenters."""

    source_name: str
    output: Path
    elapsed: float
    bpm: float
    tempo_drift_percent: float
    beat_grid_confidence: float
    key_label: str
    key_confidence: float
    groove_label: str
    swing_ratio: float
    timing_label: str
    downbeat_continuity: float
    beats: int
    bars: int
    intro: SectionCandidate | None
    outro: SectionCandidate | None
    mix_in: float | None
    mix_out: float | None
    intro_output_start: float | None = None
    intro_output_end: float | None = None
    outro_output_start: float | None = None
    outro_output_end: float | None = None
    intro_before: float | None = None
    outro_after: float | None = None
    outro_before: float | None = None
    automatic_intro_boundary: bool = False
    automatic_outro_boundary: bool = False
    preset_name: str | None = None
    detected_style: str | None = None
    preset_reason: str | None = None
    intro_existing_mix_bars: int = 0
    outro_existing_mix_bars: int = 0
    intro_already_dj_ready: bool = False
    outro_already_dj_ready: bool = False
    analysis_cache_hit: bool = False
    vocal_cache_hit: bool = False
    intro_preview: Path | None = None
    outro_preview: Path | None = None
    full_exported: bool = True
    intro_candidate_rank: int | None = None
    outro_candidate_rank: int | None = None
    automatic_intro_length: bool = False
    automatic_outro_length: bool = False
    intro_rejection_reason: str | None = None
    outro_rejection_reason: str | None = None
    intro_fallback: str | None = None
    outro_fallback: str | None = None
    stem_reliability: float | None = None
    intro_construction: str = "full mix"
    outro_construction: str = "full mix"
    output_duration: float = 0.0
    cue_points: tuple[CuePoint, ...] = ()
    cue_sheet: Path | None = None
    wav_output: Path | None = None
